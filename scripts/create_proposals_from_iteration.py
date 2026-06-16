#!/usr/bin/env python3
"""Create proposals and decisions from iteration phase outputs."""

import argparse
import json
import os
from pathlib import Path

def create_proposals_from_iteration(iteration_dir="data/iterations/v1"):
    """Extract proposals from iteration phase outputs (Phases 4-6)."""

    proposals = []
    properties_by_class = {}  # { class_label: [PropertyDef, ...] }

    # Load properties (Phase 5) for later attachment to classes
    try:
        properties_path = Path(iteration_dir) / "5_properties.json"
        with open(properties_path) as f:
            properties_data = json.load(f)
            for prop in properties_data.get("properties", []):
                class_name = prop.get("attached_to_class", "")
                if class_name not in properties_by_class:
                    properties_by_class[class_name] = []
                
                # Preserve full property details including object vs datatype distinction
                prop_entry = {
                    "name": prop.get("name", ""),
                    "description": prop.get("description", ""),
                    "required": False,
                }
                
                # Handle both datatype and object properties
                if prop.get("property_type") == "object":
                    # Object property: use range_class instead of datatype
                    prop_entry["datatype"] = None
                    prop_entry["range_class"] = prop.get("range_class", "")
                    prop_entry["inverse_name"] = prop.get("inverse_name")
                else:
                    # Datatype property: use datatype (default to xsd:string if missing/None)
                    prop_entry["datatype"] = prop.get("datatype") or "xsd:string"
                    prop_entry["range_class"] = None
                    prop_entry["inverse_name"] = None
                
                properties_by_class[class_name].append(prop_entry)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Info: Could not load Phase 5 properties: {e}")

    # Load hierarchy (classes) - this is what the export system expects
    try:
        hierarchy_path = Path(iteration_dir) / "4_hierarchy.json"
        with open(hierarchy_path) as f:
            hierarchy = json.load(f)

        # Create class proposals from hierarchy
        for i, node in enumerate(hierarchy.get("nodes", [])):
            label = node["label"]
            # Include both new and seed classes if they have properties
            has_properties = label in properties_by_class and properties_by_class[label]
            is_new = not node.get("is_from_seed", True)
            
            if is_new or has_properties:
                proposal = {
                    "id": f"class_{i}",
                    "type": "class",
                    "uri": node["uri"],
                    "label": label,
                    "definition": node.get("definition", "") if is_new else "",
                    "parent_uri": node.get("parent_uri", "") if is_new else "",
                    "parent_label": node.get("parent_label", "") if is_new else "",
                    "examples": node.get("examples", []) if is_new else [],
                    "strategy": node.get("strategy", "unknown") if is_new else "seed_extension",
                    "confidence": 0.8,
                    "source_evidence": [],
                    "is_from_seed": node.get("is_from_seed", False),  # Track origin
                    # ✅ NEW: Attach properties discovered in Phase 5
                    "suggested_properties": properties_by_class.get(label, []),
                    "suggested_relations": [],  # Phase 5 also generates relations
                }
                proposals.append(proposal)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load hierarchy data from {iteration_dir}: {e}")

    print(f"Found {len(proposals)} class proposals from hierarchy")
    print(f"Attached properties from Phase 5 to {sum(1 for p in proposals if p.get('suggested_properties'))} classes")
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