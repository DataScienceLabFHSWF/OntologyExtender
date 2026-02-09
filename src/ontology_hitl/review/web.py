"""C1.4.2 — Optional Streamlit web dashboard for review.

Implementation Guide
--------------------
This module provides a web-based alternative to the CLI review tool.
Requires the [web] optional dependency: ``pip install -e ".[web]"``

Usage:  ``streamlit run src/ontology_hitl/review/web.py``

Page layout plan:
  ┌──────────────────────────────────────────────────────┐
  │  HITL Ontology Review Dashboard              🔄 ↻   │
  ├──────────┬───────────────────────────────────────────┤
  │ Sidebar  │  Main Area                               │
  │          │                                           │
  │ • Load   │  ┌─ Proposal Card ─────────────────────┐ │
  │   file   │  │ Label: BuildingPermit               │ │
  │ • Filter │  │ Parent: AdministrativeProcess        │ │
  │   status │  │ Definition: ...                      │ │
  │ • Stats  │  │ Properties: ...                      │ │
  │   chart  │  │ Relations: ...                       │ │
  │          │  │                                       │ │
  │          │  │ [Accept] [Reject] [Revise]           │ │
  │          │  │ Rationale: [______________]          │ │
  │          │  └─────────────────────────────────────┘ │
  │          │                                           │
  │          │  Progress: 5/12 reviewed                 │
  └──────────┴───────────────────────────────────────────┘

Dependencies:
  - ``streamlit``  for the web UI
  - ``json``       for loading/saving proposals and decisions

Five sections need implementation (all marked with TODO):
  1. ``_sidebar()``        — File picker + filter + stats
  2. ``_proposal_card()``  — Display single proposal
  3. ``_decision_form()``  — Accept/reject/revise buttons + rationale
  4. ``_save_decisions()`` — Write decisions to JSON
  5. ``main()``            — Page config + layout orchestration
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    """Streamlit app entry point.

    TODO: Implement the full Streamlit dashboard.

    Steps:
        1. Import streamlit: ``import streamlit as st``
        2. ``st.set_page_config(page_title="HITL Ontology Review", layout="wide")``
        3. ``st.title("HITL Ontology Review Dashboard")``
        4. Sidebar — file upload:
           ``uploaded = st.sidebar.file_uploader("Load proposals JSON", type=["json"])``
           If uploaded: ``proposals = json.loads(uploaded.read())``
           Store in ``st.session_state["proposals"]``
        5. Sidebar — filter:
           ``status_filter = st.sidebar.multiselect("Filter status",
               ["pending", "accepted", "rejected", "needs_revision"], default=["pending"])``
        6. If no proposals loaded, show ``st.info("Upload a proposals JSON file.")`` and return.
        7. Initialize ``st.session_state.setdefault("decisions", {})``
        8. Filter proposals by status (check against decisions dict).
        9. Show progress: ``st.progress(len(decisions) / len(proposals))``
        10. For each visible proposal, call ``_proposal_card(proposal)`` and
            ``_decision_form(proposal)``  (use ``st.expander`` or ``st.columns``).
        11. Save button: ``if st.sidebar.button("Save decisions"):``
            ``_save_decisions(st.session_state["decisions"])``
    """
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit not installed. Run: pip install -e '.[web]'")
        return

    st.set_page_config(page_title="HITL Ontology Review", layout="wide")
    st.title("HITL Ontology Review Dashboard")
    st.info("Dashboard not yet implemented. See module docstring for implementation plan.")


if __name__ == "__main__":
    main()
