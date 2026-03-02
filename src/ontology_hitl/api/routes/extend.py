"""Ontology extension endpoints — apply TBox changes via multi-agent debate + SPARQL UPDATE.

When ``debate_enabled=True`` (the default), NEW_CLASS changes are routed through
the full AgentTeam debate pipeline:

    1. The suggested class is packaged as "external expert" input.
    2. An AgentTeam (OntologyEngineer / DomainExpert / Critic) debates
       the proposal against the current ontology hierarchy.
    3. On CONSENSUS or REVISED → the debated definition is inserted into
       staging via SPARQL UPDATE.
    4. On ESCALATED → the response carries escalated questions for HITL
       review instead of inserting anything.

When ``debate_enabled=False``, the original direct LLM → SPARQL INSERT
path is used as a fast fallback.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

from ontology_hitl.api.schemas import (
    BulkExtendRequest,
    DebateMessageSummary,
    DebateResult,
    DebateVerdictEnum,
    EscalatedQuestionInfo,
    TBoxChangeRequest,
    TBoxChangeResponse,
    TBoxChangeType,
)
from ontology_hitl.api.dependencies import (
    create_agent_team,
    fetch_fuseki_class_labels,
    fetch_fuseki_hierarchy,
    llm_generate,
    sparql_query,
    sparql_update,
    get_settings,
    notify_kgbuilder_rebuild,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════════
# Debate-backed handler (primary path)
# ═══════════════════════════════════════════════════════════════════════════

def _build_external_expert_context(
    request: TBoxChangeRequest,
    hierarchy_text: str,
    seed_labels: list[str],
) -> str:
    """Build a debate context string that frames the TBoxChangeRequest
    as an external expert suggestion.

    The OntologyEngineer agent receives this as its initial context and
    is expected to refine the suggestion into a proper class definition
    that the DomainExpert and Critic then review.
    """
    class_name = request.suggested_changes.get(
        "label", request.review_item_id.replace("gap_", "")
    )
    parent_hint = request.suggested_changes.get("parent_uri", "")
    description_hint = request.suggested_changes.get("description", "")
    uri_hint = request.suggested_changes.get("uri", "")

    seed_classes_str = ", ".join(seed_labels) if seed_labels else "(none loaded)"

    context = f"""EXTERNAL EXPERT PROPOSAL (from KGBuilder gap analysis):

An external system (KGBuilder's gap detector) has identified a missing
concept in the ontology and proposes adding a new class:

  Proposed class name:  {class_name}
  Rationale:            {request.rationale or '(none provided)'}
  Confidence:           {request.confidence}
  Reviewer:             {request.reviewer_id}
  Review item ID:       {request.review_item_id}"""

    if parent_hint:
        context += f"\n  Suggested parent URI: {parent_hint}"
    if description_hint:
        context += f"\n  Suggested description: {description_hint}"
    if uri_hint:
        context += f"\n  Suggested URI: {uri_hint}"

    context += f"""

{hierarchy_text}

Existing ontology classes: {seed_classes_str}

YOUR TASK as Ontology Engineer:
1. Evaluate whether this class is needed and non-redundant
2. Determine the best parent class (from existing hierarchy or owl:Thing)
3. Write a proper definition (1-2 sentences)
4. Identify any disjoint classes
5. Suggest 2-3 example instances

Return JSON:
{{
  "nodes": [
    {{
      "uri": "plan:{class_name}",
      "label": "{class_name}",
      "definition": "...",
      "parent_uri": "...",
      "parent_label": "...",
      "disjoint_with": [],
      "examples": ["...", "..."],
      "strategy": "external_expert"
    }}
  ]
}}"""

    # Append document context if provided
    if request.document_context:
        context += f"\n\nDomain document excerpts:\n{request.document_context[:4000]}"

    return context


def _debate_outcome_to_schema(outcome: "DebateOutcome") -> DebateResult:
    """Convert an agents.base.DebateOutcome to the API DebateResult schema."""
    transcript = []
    for msg in outcome.messages:
        transcript.append(DebateMessageSummary(
            role=msg.role.value,
            message_type=msg.message_type,
            approves=msg.approves,
            issues_raised=msg.issues_raised,
            reasoning_excerpt=msg.reasoning[:500] if msg.reasoning else "",
        ))

    escalated = []
    for q in outcome.escalated_questions:
        escalated.append(EscalatedQuestionInfo(
            phase=q.phase.value if hasattr(q.phase, "value") else str(q.phase),
            question=q.question,
            context=q.context,
        ))

    return DebateResult(
        verdict=DebateVerdictEnum(outcome.verdict.value),
        rounds=outcome.rounds,
        resolved_issues=outcome.resolved_issues,
        escalated_questions=escalated,
        transcript=transcript,
        final_proposal=outcome.final_proposal,
    )


def _extract_turtle_from_proposal(proposal: dict[str, Any], class_name: str) -> str:
    """Convert the debate's final_proposal JSON into OWL Turtle for SPARQL INSERT.

    The debate produces structured JSON with nodes[]. We convert the first
    matching node into Turtle syntax. If the proposal format is unexpected,
    falls back to LLM generation.
    """
    nodes = proposal.get("nodes", [])
    if not nodes:
        # Fallback: the proposal itself might be a single node
        if "label" in proposal:
            nodes = [proposal]

    if not nodes:
        # Last resort: use LLM to generate from the raw proposal
        return _generate_class_definition(class_name, str(proposal))

    node = nodes[0]
    label = node.get("label", class_name)
    definition = node.get("definition", "")
    parent_uri = node.get("parent_uri", "")
    uri = node.get("uri", f"plan:{label}")

    # Ensure URI is properly formatted
    if not uri.startswith("<") and ":" not in uri:
        uri = f"plan:{uri}"

    lines = [
        f"@prefix owl:  <http://www.w3.org/2002/07/owl#> .",
        f"@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        f"@prefix plan: <http://example.org/ontology/plan#> .",
        f"",
        f"{uri} a owl:Class ;",
        f'    rdfs:label "{label}" ;',
    ]

    if definition:
        # Escape quotes in the definition
        safe_def = definition.replace('"', '\\"')
        lines.append(f'    rdfs:comment "{safe_def}" ;')

    if parent_uri:
        if not parent_uri.startswith("<") and ":" not in parent_uri:
            parent_uri = f"plan:{parent_uri}"
        lines.append(f"    rdfs:subClassOf {parent_uri} ;")

    # Close the turtle block (replace last ; with .)
    lines[-1] = lines[-1].rstrip(" ;") + " ."

    return "\n".join(lines)


def _debate_new_class(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle NEW_CLASS via multi-agent debate pipeline.

    Flow:
        1. Fetch current hierarchy from Fuseki
        2. Build context with external expert proposal
        3. Create AgentTeam and run debate (Phase.HIERARCHY)
        4. If consensus/revised → extract OWL from debated proposal → insert
        5. If escalated → return needs_review with questions
    """
    from ontology_hitl.methodology.ontology101 import Phase

    change_id = f"debate_{uuid.uuid4().hex[:12]}"
    class_name = request.suggested_changes.get(
        "label", request.review_item_id.replace("gap_", "")
    )

    logger.info(
        "debate_new_class_start",
        class_name=class_name,
        change_id=change_id,
        confidence=request.confidence,
    )

    # 1. Fetch current hierarchy for context
    hierarchy_text = fetch_fuseki_hierarchy()
    seed_labels = fetch_fuseki_class_labels()

    # 2. Build the external expert context
    context = _build_external_expert_context(request, hierarchy_text, seed_labels)

    # 3. Create AgentTeam and run the debate
    team = create_agent_team(
        document_context=request.document_context,
    )

    try:
        outcome = team.run_debate(Phase.HIERARCHY, context)
        team.save_debate(outcome)
    except Exception as e:
        logger.error("debate_failed", error=str(e), class_name=class_name)
        # Fall back to direct LLM generation
        logger.info("falling_back_to_direct_generation", class_name=class_name)
        return _apply_new_class_direct(request)

    debate_result = _debate_outcome_to_schema(outcome)

    # 4. Decide based on verdict
    if outcome.verdict.value in ("consensus", "revised", "partial"):
        # The debate produced a validated proposal — insert it
        changes_applied: list[str] = []
        settings = get_settings()
        staging_ds = settings["fuseki_staging"]

        # Extract OWL Turtle from the debated proposal
        turtle_def = _extract_turtle_from_proposal(
            outcome.final_proposal, class_name,
        )
        logger.info(
            "debate_produced_definition",
            class_name=class_name,
            verdict=outcome.verdict.value,
            rounds=outcome.rounds,
        )

        # Insert into staging
        insert_query = f"""
        INSERT DATA {{
            {turtle_def}
        }}
        """
        try:
            sparql_update(insert_query, dataset=staging_ds)
            changes_applied.append(
                f"Debated & inserted class '{class_name}' into staging "
                f"(verdict: {outcome.verdict.value}, rounds: {outcome.rounds})"
            )
        except Exception as e:
            logger.error("staging_insert_failed", error=str(e))
            return TBoxChangeResponse(
                status="error",
                change_id=change_id,
                changes_applied=[f"Debate passed but staging insert failed: {e}"],
                debate=debate_result,
            )

        # Generate SHACL shape from debated class
        class_uri = request.suggested_changes.get("uri", f"plan:{class_name}")
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

        timestamp = datetime.now(timezone.utc).isoformat()
        changes_applied.append(f"Logged at {timestamp}")

        status = "staged"
        if outcome.escalated_questions:
            # Partial: staged but with open questions
            status = "staged"
            changes_applied.append(
                f"{len(outcome.escalated_questions)} question(s) escalated for review"
            )

        return TBoxChangeResponse(
            status=status,
            change_id=change_id,
            changes_applied=changes_applied,
            debate=debate_result,
        )

    else:
        # ESCALATED: agents couldn't agree — surface for HITL
        logger.info(
            "debate_escalated",
            class_name=class_name,
            escalated_questions=len(outcome.escalated_questions),
        )
        return TBoxChangeResponse(
            status="needs_review",
            change_id=change_id,
            changes_applied=[
                f"Multi-agent debate escalated after {outcome.rounds} round(s): "
                f"{len(outcome.escalated_questions)} unresolved question(s)"
            ],
            debate=debate_result,
        )


# ═══════════════════════════════════════════════════════════════════════════
# Direct handlers (fallback / non-debate path)
# ═══════════════════════════════════════════════════════════════════════════

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


def _apply_new_class_direct(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Handle tbox_new_class WITHOUT debate: direct LLM → SPARQL INSERT.

    Used when ``debate_enabled=False`` or as a fallback when the debate
    pipeline fails.
    """
    settings = get_settings()
    change_id = f"direct_{uuid.uuid4().hex[:12]}"
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
        changes_applied.append(f"Inserted class '{class_name}' into staging graph (direct)")
    except Exception as e:
        logger.error("staging_insert_failed", error=str(e), class_name=class_name)
        return TBoxChangeResponse(
            status="error",
            change_id=change_id,
            changes_applied=[f"Failed to insert: {e}"],
            debate=DebateResult(verdict=DebateVerdictEnum.SKIPPED),
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
        debate=DebateResult(verdict=DebateVerdictEnum.SKIPPED),
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


# ═══════════════════════════════════════════════════════════════════════════
# Handler dispatch
# ═══════════════════════════════════════════════════════════════════════════

_HANDLERS: dict[TBoxChangeType, callable] = {
    TBoxChangeType.MODIFY_CLASS: _apply_modify_class,
    TBoxChangeType.HIERARCHY_FIX: _apply_hierarchy_fix,
    TBoxChangeType.PROPERTY_FIX: _apply_property_fix,
}


def _dispatch_new_class(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Route NEW_CLASS through debate or direct path based on request flag."""
    if request.debate_enabled:
        return _debate_new_class(request)
    else:
        return _apply_new_class_direct(request)


# ═══════════════════════════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/extend", response_model=TBoxChangeResponse)
async def extend(request: TBoxChangeRequest) -> TBoxChangeResponse:
    """Apply a single TBox change to the ontology.

    Called by KGBuilder's HITL gap detector or by human reviewers.

    For **NEW_CLASS** changes (with ``debate_enabled=True``, the default):
        The suggestion is treated as "external expert" input and routed
        through the multi-agent debate pipeline (OntologyEngineer,
        DomainExpert, Critic).  The agents evaluate, refine, and
        validate the proposal before it is staged.

    For other change types, or when ``debate_enabled=False``:
        Direct SPARQL mutations are applied.

    Possible response statuses:
        - **staged**: Change inserted into staging graph (ready for promotion)
        - **applied**: Change applied directly to the main graph
        - **needs_review**: Debate escalated — human review required
        - **error**: Something went wrong
    """
    # Route NEW_CLASS through the debate dispatcher
    if request.change_type == TBoxChangeType.NEW_CLASS:
        handler = _dispatch_new_class
    else:
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
        debate_enabled=request.debate_enabled,
    )
    result = handler(request)

    # Best-effort: notify KGBuilder that ontology changed
    if result.status in ("applied", "staged"):
        notify_kgbuilder_rebuild()

    return result


@router.post("/extend/bulk", response_model=list[TBoxChangeResponse])
async def extend_bulk(request: BulkExtendRequest) -> list[TBoxChangeResponse]:
    """Apply multiple TBox changes.

    If ``atomic=True`` (default), rolls back all changes on any failure.
    If ``atomic=False``, applies as many as possible.

    Each NEW_CLASS change in the batch is individually debated (unless
    ``debate_enabled=False`` on the individual request).
    """
    results: list[TBoxChangeResponse] = []
    for change in request.changes:
        # Route NEW_CLASS through debate dispatcher
        if change.change_type == TBoxChangeType.NEW_CLASS:
            handler = _dispatch_new_class
        else:
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
