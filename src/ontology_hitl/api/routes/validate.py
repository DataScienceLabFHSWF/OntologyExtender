"""SHACL validation endpoint."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException

from ontology_hitl.api.schemas import (
    SHACLValidationRequest,
    SHACLValidationResponse,
    SHACLViolation,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post("/validate/shacl", response_model=SHACLValidationResponse)
async def validate_shacl(request: SHACLValidationRequest) -> SHACLValidationResponse:
    """Validate RDF data graph against SHACL shapes.

    If paths are not provided, loads the default dataset and shapes
    from Fuseki.
    """
    try:
        import rdflib
        from pyshacl import validate as shacl_validate
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Missing dependency: {e}. Install rdflib and pyshacl.",
        )

    # Load data graph
    data_graph = rdflib.Graph()
    if request.data_graph_path:
        p = Path(request.data_graph_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Data graph not found: {p}")
        data_graph.parse(str(p))
    else:
        # Load from Fuseki default dataset
        from ontology_hitl.api.dependencies import get_settings, get_fuseki_client

        settings = get_settings()
        ds = settings["fuseki_dataset"]
        client = get_fuseki_client()
        resp = client.get(
            f"/{ds}",
            headers={"Accept": "text/turtle"},
        )
        resp.raise_for_status()
        data_graph.parse(data=resp.text, format="turtle")

    # Load shapes graph
    shapes_graph = rdflib.Graph()
    if request.shapes_path:
        p = Path(request.shapes_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail=f"Shapes file not found: {p}")
        shapes_graph.parse(str(p))
    else:
        # Auto-detect: look for shapes in data graph or a shapes dataset
        # For now, try loading from a "shapes" named graph in Fuseki
        from ontology_hitl.api.dependencies import get_settings, get_fuseki_client

        settings = get_settings()
        client = get_fuseki_client()
        try:
            resp = client.get(
                f"/{settings['fuseki_dataset']}/data",
                params={"graph": "urn:shapes"},
                headers={"Accept": "text/turtle"},
            )
            if resp.status_code == 200:
                shapes_graph.parse(data=resp.text, format="turtle")
        except Exception:
            logger.warning("shapes_graph_load_fallback")

    if len(shapes_graph) == 0:
        return SHACLValidationResponse(
            conforms=True,
            violations=[],
            total_shapes=0,
        )

    # Run validation
    conforms, _, results_text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        inference="rdfs",
        abort_on_first=False,
    )

    # Parse violations from results graph
    violations: list[SHACLViolation] = []
    results_graph = rdflib.Graph()
    try:
        results_graph.parse(data=results_text, format="turtle")
        SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
        for result in results_graph.subjects(rdflib.RDF.type, SH.ValidationResult):
            focus = str(results_graph.value(result, SH.focusNode) or "")
            path = str(results_graph.value(result, SH.resultPath) or "")
            msg = str(results_graph.value(result, SH.resultMessage) or "")
            sev = str(results_graph.value(result, SH.resultSeverity) or "")
            violations.append(SHACLViolation(
                focus_node=focus,
                path=path,
                message=msg,
                severity=sev.rsplit("#", 1)[-1] if "#" in sev else sev,
            ))
    except Exception:
        logger.warning("shacl_results_parse_failed")

    # Count shapes
    total_shapes = len(list(shapes_graph.subjects(
        rdflib.RDF.type,
        rdflib.Namespace("http://www.w3.org/ns/shacl#").NodeShape,
    )))

    return SHACLValidationResponse(
        conforms=conforms,
        violations=violations,
        total_shapes=total_shapes,
    )
