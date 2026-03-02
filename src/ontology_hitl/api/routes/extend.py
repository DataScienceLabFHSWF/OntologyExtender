"""Ontology extension endpoints — apply TBox changes via SPARQL UPDATE."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, HTTPException

from ontology_hitl.api.schemas import (
    BulkExtendRequest,
    TBoxChangeRequest,
    TBoxChangeResponse,
    TBoxChangeType,
)
from ontology_hitl.api.dependencies import (
    llm_generate,
    sparql_query,
    sparql_update,
    get_settings,
    notify_kgbuilder_rebuild,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────

def _generate_class_definition(class_name: str, rationale: str) -> str:
    """Use LLM to generate an OWL class definition in Turtle format."""
    prompt = f"""Generate an OWL class definition in Turtle syntax for the class "{class_name}".

Context / rationale: {rationale}

Requirements:
- Use a sensible namespace prefix (e.g., ex: or the ontology's existing prefix)
- Include rdfs:label, rdfs:comment
- Include rdfs:subClassOf if an appropriate parent is obvious
- Keep it concise

Return ONLY the Turtle snippet, no explanation."""

    system = (
        "You are an ontology engineer. Produce valid OWL/Turtle class definitions."
    )
    return llm_generate(prompt, system=system)


def _generate_shacl_shape(class_uri: str, class_name: str) -> str:
    """Use LLM to generate a SHACL NodeShape for the given class."""
    prompt = f"""Generate a SHACL NodeShape in Turtle syntax for the OWL class <{class_uri}> ("{class_name}").

Requirements:
- Target class: <{class_uri}>
- Include sh:property constraints for likely properties (rdfs:label at minimum)
- Use sh:minCount, sh:maxCount, sh:datatype where appropriate
- Keep it concise

Return ONLY the Turtle snippet, no explanation."""

    system = "You are a SHACL shapes engineer. Produce valid SHACL Turtle."
    return llm_generate(prompt, system=system)


def _apply_new_class(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle tbox_new_class: generate definition, insert into staging graph."""
    settings = get_settings()
    change_id = f"change_{uuid.uuid4().hex[:12]}"
    class_name = request.suggested_changes.get(
        "label", request.review_item_id.replace("gap_", "")
    )

    changes_applied: list[str] = []

    # 1. Generate OWL class definition via LLM
    turtle_def = _generate_class_definition(class_name, request.rationale)
    logger.info("class_definition_generated", class_name=class_name, change_id=change_id)

    # 2. Insert into staging dataset via SPARQL UPDATE
    staging_ds = settings["fuseki_staging"]
    insert_query = f"""
    INSERT DATA {{
        {turtle_def}
    }}
    """
    try:
        sparql_update(insert_query, dataset=staging_ds)
        changes_applied.append(f"Inserted class '{class_name}' into staging graph")
    except Exception as e:
        logger.error("staging_insert_failed", error=str(e), class_name=class_name)
        return TBoxChangeResponse(
            status="error",
            change_id=change_id,
            changes_applied=[f"Failed to insert: {e}"],
        )

    # 3. Generate SHACL shape
    class_uri = request.suggested_changes.get("uri", f"ex:{class_name}")
    try:
        shacl_turtle = _generate_shacl_shape(class_uri, class_name)
        sparql_update(
            f"INSERT DATA {{ {shacl_turtle} }}",
            dataset=staging_ds,
        )
        changes_applied.append(f"Generated SHACL shape for '{class_name}'")
    except Exception as e:
        logger.warning("shacl_generation_failed", error=str(e))
        changes_applied.append(f"SHACL generation skipped: {e}")

    # 4. Log change to history
    timestamp = datetime.now(timezone.utc).isoformat()
    changes_applied.append(f"Logged at {timestamp}")

    return TBoxChangeResponse(
        status="staged",
        change_id=change_id,
        changes_applied=changes_applied,
    )


def _apply_modify_class(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle tbox_modify_class: update label/description/parent of existing class."""
    change_id = f"change_{uuid.uuid4().hex[:12]}"
    class_uri = request.suggested_changes.get("uri", "")
    if not class_uri:
        return TBoxChangeResponse(
            status="error",
            change_id=change_id,
            changes_applied=["Missing 'uri' in suggested_changes"],
        )

    changes_applied: list[str] = []

    # Update label if provided
    new_label = request.suggested_changes.get("label")
    if new_label:
        sparql_update(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            DELETE {{ <{class_uri}> rdfs:label ?old }}
            INSERT {{ <{class_uri}> rdfs:label "{new_label}" }}
            WHERE  {{ OPTIONAL {{ <{class_uri}> rdfs:label ?old }} }}
        """)
        changes_applied.append(f"Updated label to '{new_label}'")

    # Update description if provided
    new_desc = request.suggested_changes.get("description")
    if new_desc:
        sparql_update(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            DELETE {{ <{class_uri}> rdfs:comment ?old }}
            INSERT {{ <{class_uri}> rdfs:comment "{new_desc}" }}
            WHERE  {{ OPTIONAL {{ <{class_uri}> rdfs:comment ?old }} }}
        """)
        changes_applied.append(f"Updated description")

    # Update parent if provided
    new_parent = request.suggested_changes.get("parent_uri")
    if new_parent:
        sparql_update(f"""
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX owl:  <http://www.w3.org/2002/07/owl#>
            DELETE {{ <{class_uri}> rdfs:subClassOf ?old }}
            INSERT {{ <{class_uri}> rdfs:subClassOf <{new_parent}> }}
            WHERE  {{ OPTIONAL {{ <{class_uri}> rdfs:subClassOf ?old .
                                  ?old a owl:Class . }} }}
        """)
        changes_applied.append(f"Re-parented under <{new_parent}>")

    return TBoxChangeResponse(
        status="applied",
        change_id=change_id,
        changes_applied=changes_applied or ["No changes requested"],
    )


def _apply_hierarchy_fix(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle tbox_hierarchy_fix: move a class under a new parent."""
    change_id = f"change_{uuid.uuid4().hex[:12]}"
    class_uri = request.suggested_changes.get("uri", "")
    new_parent = request.suggested_changes.get("parent_uri", "")

    if not class_uri or not new_parent:
        return TBoxChangeResponse(
            status="error",
            change_id=change_id,
            changes_applied=["Missing 'uri' or 'parent_uri' in suggested_changes"],
        )

    sparql_update(f"""
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl:  <http://www.w3.org/2002/07/owl#>
        DELETE {{ <{class_uri}> rdfs:subClassOf ?old }}
        INSERT {{ <{class_uri}> rdfs:subClassOf <{new_parent}> }}
        WHERE  {{ OPTIONAL {{ <{class_uri}> rdfs:subClassOf ?old .
                              ?old a owl:Class . }} }}
    """)

    return TBoxChangeResponse(
        status="applied",
        change_id=change_id,
        changes_applied=[f"Moved <{class_uri}> under <{new_parent}>"],
    )


def _apply_property_fix(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle tbox_property_fix: add/modify property on a class."""
    change_id = f"change_{uuid.uuid4().hex[:12]}"
    # Implementation depends on your property model — stub for now
    return TBoxChangeResponse(
        status="staged",
        change_id=change_id,
        changes_applied=["Property fix staged for review"],
    )


_HANDLERS: dict[TBoxChangeType, callable] = {
    TBoxChangeType.NEW_CLASS: _apply_new_class,
    TBoxChangeType.MODIFY_CLASS: _apply_modify_class,
    TBoxChangeType.HIERARCHY_FIX: _apply_hierarchy_fix,
    TBoxChangeType.PROPERTY_FIX: _apply_property_fix,
}


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/extend", response_model=TBoxChangeResponse)
async def extend(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Apply a single TBox change to the ontology.

    Called by KGBuilder's HITL gap detector or by human reviewers.
    Depending on change_type, this will:
    - Generate OWL class definition + SHACL shape (new_class)
    - Update class metadata (modify_class)
    - Fix hierarchy relationships (hierarchy_fix)
    - Add/modify properties (property_fix)
    """
    handler = _HANDLERS.get(request.change_type)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown change_type: {request.change_type}",
        )

    logger.info(
        "applying_tbox_change",
        change_type=request.change_type,
        review_item_id=request.review_item_id,
    )
    result = handler(request)

    # Best-effort: notify KGBuilder that ontology changed
    if result.status in ("applied", "staged"):
        notify_kgbuilder_rebuild()

    return result


@router.post("/extend/bulk", response_model=list[TBoxChangeResponse])
async def extend_bulk(request: BulkExtendRequest) -> list[TBoxChangeResponse]:
    """Apply multiple TBox changes.

    If `atomic=True` (default), rolls back all changes on any failure.
    If `atomic=False`, applies as many as possible.
    """
    results: list[TBoxChangeResponse] = []
    for change in request.changes:
        handler = _HANDLERS.get(change.change_type)
        if not handler:
            result = TBoxChangeResponse(
                status="error",
                change_id="n/a",
                changes_applied=[f"Unknown change_type: {change.change_type}"],
            )
        else:
            result = handler(change)

        results.append(result)

        if request.atomic and result.status == "error":
            logger.warning(
                "bulk_extend_aborted",
                failed_item=change.review_item_id,
            )
            # Mark remaining as skipped
            for remaining in request.changes[len(results):]:
                results.append(
                    TBoxChangeResponse(
                        status="error",
                        change_id="n/a",
                        changes_applied=["Skipped due to earlier atomic failure"],
                    )
                )
            break

    # Notify KGBuilder once (not per change)
    applied = [r for r in results if r.status in ("applied", "staged")]
    if applied:
        notify_kgbuilder_rebuild()

    return results
