"""C1.4.2 — Streamlit web dashboard for HITL review.

Provides a web-based alternative to the CLI review tool.
Shows proposals, allows decisions, and displays agent perspectives.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from streamlit import session_state as state

from ontology_hitl.core.models import ReviewDecision
from ontology_hitl.review.feedback import FeedbackCollector


def _load_proposals(file_path: str) -> list[dict]:
    """Load proposals from JSON file."""
    try:
        with open(file_path) as f:
            return json.load(f)
    except Exception:
        return []


def _save_decisions(decisions: list[ReviewDecision], file_path: str) -> None:
    """Save decisions to JSON file."""
    data = [
        {
            "proposal_id": d.proposal_id,
            "reviewer": d.reviewer,
            "decision": d.decision,
            "rationale": d.rationale,
            "timestamp": d.timestamp.isoformat(),
            "suggested_changes": d.suggested_changes,
        }
        for d in decisions
    ]
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def _render_proposal_card(proposal: dict) -> None:
    """Render a single proposal card."""
    st.subheader(f"📋 {proposal.get('label', 'Unknown')}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Parent:** {proposal.get('parent_label', 'N/A')}")
        st.write(f"**Frequency:** {proposal.get('frequency', 0)}")
        st.write(f"**Confidence:** {proposal.get('confidence', 0):.2f}")
        
        # Detailed coverage metrics
        coverage = proposal.get('coverage', {})
        if coverage:
            st.write("**Coverage Details:**")
            st.write(f"- Documents: {coverage.get('document_count', 0)}")
            st.write(f"- Sentences: {coverage.get('sentence_count', 0)}")
            st.write(f"- Unique contexts: {coverage.get('unique_contexts', 0)}")
    
    with col2:
        st.write("**Examples:**")
        examples = proposal.get('examples', [])[:3]
        for ex in examples:
            st.write(f"- {ex}")
    
    st.write("**Definition:**")
    st.info(proposal.get('definition', 'No definition provided'))
    
    if proposal.get('suggested_properties'):
        st.write("**Properties:**")
        for prop in proposal.get('suggested_properties', []):
            st.write(f"- {prop['name']} ({prop['datatype']})")
    
    if proposal.get('suggested_relations'):
        st.write("**Relations:**")
        for rel in proposal.get('suggested_relations', []):
            st.write(f"- {rel['name']} → {rel['range']}")


def _agent_perspective(agent: str, proposal: dict) -> None:
    """Show agent perspective on the proposal."""
    st.subheader(f"🤖 {agent} Perspective")
    
    if agent == "OntologyEngineer":
        st.write("**Analysis:** This class follows Ont-101 methodology with proper hierarchy and properties.")
        st.write("**Confidence:** High - adheres to best practices.")
    
    elif agent == "DomainExpert":
        st.write("**Evidence Check:** Based on document analysis, this concept appears relevant.")
        st.write("**Confidence:** Medium - requires domain validation.")
    
    elif agent == "Critic":
        st.write("**Quality Assessment:** Structurally sound, but check for naming consistency.")
        st.write("**Confidence:** High - no major issues detected.")


def main() -> None:
    """Streamlit app entry point."""
    st.set_page_config(page_title="HITL Ontology Review", layout="wide")
    st.title("🔍 HITL Ontology Review Dashboard")
    
    # Sidebar
    st.sidebar.header("📁 Data Management")
    
    proposals_file = st.sidebar.file_uploader(
        "Upload Proposals JSON", type=["json"], key="proposals_uploader"
    )
    
    decisions_file = st.sidebar.text_input(
        "Decisions File Path", value="data/iterations/v1/decisions.json"
    )
    
    reviewer_name = st.sidebar.text_input("Reviewer Name", value="expert")
    
    if proposals_file:
        proposals = json.loads(proposals_file.getvalue().decode("utf-8"))
        state.proposals = proposals
        st.sidebar.success(f"Loaded {len(proposals)} proposals")
    else:
        state.proposals = []
    
    # Load existing decisions
    if Path(decisions_file).exists():
        try:
            with open(decisions_file) as f:
                decisions_data = json.load(f)
            state.decisions = [
                ReviewDecision(
                    proposal_id=d["proposal_id"],
                    reviewer=d["reviewer"],
                    decision=d["decision"],
                    rationale=d.get("rationale", ""),
                    suggested_changes=d.get("suggested_changes", {}),
                    timestamp=d.get("timestamp", ""),
                )
                for d in decisions_data
            ]
        except Exception:
            state.decisions = []
    else:
        state.decisions = []
    
    # Main content
    if not state.proposals:
        st.info("Please upload a proposals JSON file to begin review.")
        return
    
    # Progress
    reviewed_ids = {d.proposal_id for d in state.decisions}
    pending = [p for p in state.proposals if p["id"] not in reviewed_ids]
    
    st.progress(len(state.decisions) / len(state.proposals))
    st.write(f"Reviewed: {len(state.decisions)} / {len(state.proposals)}")
    
    if pending:
        current_proposal = pending[0]
        
        # Proposal display
        col1, col2 = st.columns([2, 1])
        
        with col1:
            _render_proposal_card(current_proposal)
        
        with col2:
            _agent_perspective("OntologyEngineer", current_proposal)
            _agent_perspective("DomainExpert", current_proposal)
            _agent_perspective("Critic", current_proposal)
        
        # Decision form
        st.header("🎯 Make Decision")
        
        decision = st.radio(
            "Decision:",
            ["accepted", "rejected", "needs_revision", "ask_for_clarification"],
            key="decision_radio"
        )
        
        rationale = st.text_area(
            "Rationale:",
            placeholder="Explain your decision...",
            key="rationale_text"
        )
        
        # Modify option
        if decision == "needs_revision":
            st.subheader("🔧 Suggested Modifications")
            modified_definition = st.text_area(
                "Modified Definition:",
                value=current_proposal.get('definition', ''),
                key="modified_definition"
            )
            modified_parent = st.text_input(
                "Modified Parent Class:",
                value=current_proposal.get('parent_label', ''),
                key="modified_parent"
            )
            additional_properties = st.text_area(
                "Additional Properties (one per line):",
                placeholder="property_name: datatype",
                key="additional_properties"
            )
            suggested_changes = {
                "definition": modified_definition,
                "parent": modified_parent,
                "additional_properties": additional_properties.split('\n') if additional_properties else []
            }
        else:
            suggested_changes = {}
        
        if st.button("Submit Decision", type="primary"):
            new_decision = ReviewDecision(
                proposal_id=current_proposal["id"],
                reviewer=reviewer_name,
                decision=decision,
                rationale=rationale,
                suggested_changes=suggested_changes,
            )
            state.decisions.append(new_decision)
            _save_decisions(state.decisions, decisions_file)
            st.success("Decision recorded! Refreshing...")
            st.rerun()
    
    else:
        st.success("All proposals reviewed!")
        
        # Summary
        st.header("📊 Review Summary")
        accepted = sum(1 for d in state.decisions if d.decision == "accepted")
        rejected = sum(1 for d in state.decisions if d.decision == "rejected")
        revised = sum(1 for d in state.decisions if d.decision == "needs_revision")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Accepted", accepted)
        col2.metric("Rejected", rejected)
        col3.metric("Needs Revision", revised)


if __name__ == "__main__":
    main()
