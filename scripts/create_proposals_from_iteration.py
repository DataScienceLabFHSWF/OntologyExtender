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
                # Use property_type field to determine classification
                prop_type = prop.get("property_type", "datatype")
                prop_entry = {
                    "name": prop.get("name", ""),
                    "description": prop.get("description", ""),
                    "required": False,
                }
                
                # Handle both datatype and object properties
                if prop_type == "object":
                    # Object property: set datatype=None, use range_class or infer from property name
                    prop_entry["datatype"] = None
                    # Try to infer range_class from property name or use explicit range_class
                    range_class = prop.get("range_class")
                    if not range_class and prop.get("name"):
                        # Try to infer: hasGrapeVariety -> GrapeVariety
                        name = prop.get("name", "")
                        if name.startswith("has"):
                            range_class = name[3:]  # Remove "has" prefix
                        elif name.startswith("is"):
                            range_class = name[2:]  # Remove "is" prefix
                    prop_entry["range_class"] = range_class or ""
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
        processed_labels = set()
        for i, node in enumerate(hierarchy.get("nodes", [])):
            label = node["label"]
            processed_labels.add(label)
            proposal = {
                "id": f"class_{i}",
                "type": "class",
                "uri": node["uri"],
                "label": label,
                "definition": node.get("definition", ""),
                "parent_uri": node.get("parent_uri", ""),
                "parent_label": node.get("parent_label", ""),
                "examples": node.get("examples", []),
                "strategy": node.get("strategy", "unknown"),
                "confidence": 0.8,
                "source_evidence": [],
                "is_from_seed": node.get("is_from_seed", False),
                # ✅ NEW: Attach properties discovered in Phase 5
                "suggested_properties": properties_by_class.get(label, []),
                "suggested_relations": [],
            }
            proposals.append(proposal)
        
        # ✅ NEW: Also add seed classes that have properties (e.g., Wine with hasGrapeVariety)
        i = len(proposals)  # Continue numbering from existing proposals
        for class_label, props in properties_by_class.items():
            if class_label not in processed_labels and props:
                proposal = {
                    "id": f"class_{i}",
                    "type": "class",
                    "uri": f"plan:{class_label}",  # Generate URI for seed class
                    "label": class_label,
                    "definition": "",  # Seed class, no new definition
                    "parent_uri": "",
                    "parent_label": "",
                    "examples": [],
                    "strategy": "seed_extension",
                    "confidence": 0.8,
                    "source_evidence": [],
                    "is_from_seed": True,  # Mark as seed class
                    "suggested_properties": props,
                    "suggested_relations": [],
                }
                proposals.append(proposal)
                i += 1
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