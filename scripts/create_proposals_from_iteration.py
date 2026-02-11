#!/usr/bin/env python3
"""Create proposals and decisions from iteration phase outputs."""

import argparse
import json
import os
from pathlib import Path

def create_proposals_from_iteration(iteration_dir="data/iterations/v1"):
    """Extract proposals from iteration phase outputs."""

    proposals = []

    # Load hierarchy (classes) - this is what the export system expects
    try:
        hierarchy_path = Path(iteration_dir) / "4_hierarchy.json"
        with open(hierarchy_path) as f:
            hierarchy = json.load(f)

        # Create class proposals from hierarchy
        for i, node in enumerate(hierarchy.get("nodes", [])):
            if not node.get("is_from_seed", True):  # Only new classes
                proposal = {
                    "id": f"class_{i}",
                    "type": "class",
                    "uri": node["uri"],
                    "label": node["label"],
                    "definition": node["definition"],
                    "parent_uri": node.get("parent_uri"),
                    "parent_label": node.get("parent_label"),
                    "examples": node.get("examples", []),
                    "strategy": node.get("strategy", "unknown"),
                    "confidence": 0.8,  # Default confidence
                    "source_evidence": []
                }
                proposals.append(proposal)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load hierarchy data from {iteration_dir}: {e}")

    print(f"Found {len(proposals)} class proposals from hierarchy")
    return proposals

def create_decisions(proposals):
    """Create decisions file accepting all proposals."""
    decisions = []
    for proposal in proposals:
        decision = {
            "proposal_id": proposal["id"],
            "decision": "accept",
            "confidence": proposal.get("confidence", 0.5),
            "reviewer_notes": "Auto-accepted from iteration results"
        }
        decisions.append(decision)

    return decisions

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create proposals from iteration outputs")
    parser.add_argument("--experiment-name", default="", help="Experiment name for directory selection")
    args = parser.parse_args()
    
    # Determine iteration directory
    experiment_name = args.experiment_name or os.environ.get("ONTOLOGY_EXPERIMENT_NAME", "")
    if experiment_name:
        iteration_dir = f"data/iterations/{experiment_name}"
    else:
        iteration_dir = "data/iterations/v1"
    
    print(f"Creating proposals from iteration outputs in {iteration_dir}...")

    proposals = create_proposals_from_iteration(iteration_dir)
    decisions = create_decisions(proposals)

    # Save proposals
    proposals_path = Path(iteration_dir) / "proposals.json"
    proposals_path.parent.mkdir(parents=True, exist_ok=True)
    with open(proposals_path, "w") as f:
        json.dump(proposals, f, indent=2, ensure_ascii=False)

    # Save decisions
    decisions_path = Path(iteration_dir) / "decisions.json"
    with open(decisions_path, "w") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)

    print(f"Created {len(proposals)} proposals and {len(decisions)} decisions")
    print(f"Proposals saved to: {proposals_path}")
    print(f"Decisions saved to: {decisions_path}")