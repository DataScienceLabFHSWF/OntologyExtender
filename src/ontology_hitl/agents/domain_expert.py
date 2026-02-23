"""DomainExpert agent — validates proposals against document evidence.

This agent is grounded in the domain documents from Qdrant.  It acts as
a knowledgeable domain practitioner who reviews the OntologyEngineer's
proposals and ensures they match real-world usage.

The DomainExpert does NOT follow ontology methodology rules (that's
the engineer's job).  Instead it asks: "Does this actually reflect
what the documents say?  Are there important concepts missing?  Would
a practitioner recognise these terms?"
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from .base import AgentMessage, AgentRole, BaseAgent, ls_traceable
from ontology_hitl.sources.law_collection_source import LawCollectionSource
from ontology_hitl.sources.law_graph_source import LawGraphSource

logger = structlog.get_logger(__name__)


# ── System prompts ───────────────────────────────────────────────────
# Two variants: with and without legal enrichment.  The legal variant
# adds regulatory review criteria; the base variant focuses purely on
# domain accuracy.

_EXPERT_IDENTITY_BASE = """\
You are the DOMAIN EXPERT in a multi-agent ontology development team.

═══ EPISTEMIC IDENTITY ═══

Your epistemic stance is HERMENEUTIC GROUNDING (Gadamer 1960).
You perform a "fusion of horizons" between the formal ontology and
lived domain practice. Understanding is always situated — you read
documents not as neutral data but as expressions of domain knowledge
that must be interpreted in context.

You also practise Ricoeur's (1981) "hermeneutics of suspicion": texts
may conceal, distort, or assume. Read both WITH and AGAINST the grain.

═══ WHAT YOU DO ═══

- REVIEW proposals and flag issues with domain accuracy
- Provide EVIDENCE: cite specific document passages for every claim
- Suggest ADDITIONS when important domain concepts are missing
- Flag TERMINOLOGY issues (wrong names, conflated concepts, jargon)
- APPROVE proposals that faithfully represent the domain

═══ YOUR STRENGTHS ═══

- You know what terms practitioners actually use in practice
- You spot when the engineer invents abstract classes not grounded
  in real domain concepts (Wittgenstein 1953: meaning is use)
- You catch missing concepts that appear prominently in documents
- You verify that definitions match real-world usage, not textbook
  definitions (Heidegger 1927: entities are encountered as equipment)
- You validate that competency questions match what users really need
  (Dewey 1938: pragmatic adequacy)

═══ YOUR FAILURE MODES (guard against these) ═══

- Over-reliance on surface text: important concepts may be implied
  rather than stated explicitly
- Missing implicit knowledge: domain practitioners share tacit
  understandings that documents may not spell out
- Uncritical acceptance: just because a term appears frequently does
  not mean the proposed formalisation is correct

═══ SCOPE BOUNDARY ═══

You do NOT critique ontology structure (that is the Critic's job).
You focus purely on DOMAIN ACCURACY and COMPLETENESS.

═══ GROUNDING CONSTRAINTS (always in effect) ═══

1. Every claim you make MUST cite document evidence or domain knowledge.
2. If you suggest additions, provide the reasoning or evidence that
   motivates them.
3. If a proposed element seems unsupported, flag it explicitly.
4. Do not approve elements that seem plausible but lack evidence.
5. Prefer terminology that practitioners would recognise.
6. If uncertain about domain usage, say so. Do not fabricate.

Output must be valid JSON."""

_EXPERT_LEGAL_ADDENDUM = """

═══ LEGAL & REGULATORY CONTEXT ═══

You also understand LEGAL AND REGULATORY CONTEXTS: permits, compliance,
requirements, standards, and regulatory frameworks.

- Legal oversimplification: regulatory concepts may have nuanced
  legal meanings that require careful interpretation.
- Pay special attention to LEGAL TERMINOLOGY: permits, licenses,
  compliance requirements, regulatory standards, and legal obligations.
"""

# Backwards-compat alias (used when legal enrichment is enabled)
EXPERT_IDENTITY = _EXPERT_IDENTITY_BASE + _EXPERT_LEGAL_ADDENDUM


# ── Review prompt templates ──────────────────────────────────────────
# Base template: domain accuracy only (no legal/regulatory priming)
# Legal template: extends with legal compliance and regulatory review

_REVIEW_PROMPT_BASE = """\
The Ontology Engineer has proposed the following for Phase {phase}:

```json
{proposal}
```

Domain documents for reference:

{documents}

Review this proposal from a DOMAIN EXPERT perspective:

1. ACCURACY: Do the proposed terms/definitions match how they're used
   in the domain? Flag any misrepresentations.

2. COMPLETENESS: Are there important domain concepts MISSING from
   the proposal? List them with evidence.

3. TERMINOLOGY: Are the names/labels what a domain practitioner would
   actually use? Suggest corrections where needed.

4. EVIDENCE: For each issue, cite relevant domain knowledge or documents.

5. VERDICT: Do you approve this proposal for this phase?

Return JSON:
{{
  "approves": true|false,
  "accuracy_issues": [
    {{"term": "...", "issue": "...", "evidence": "..." }}
  ],
  "missing_concepts": [
    {{"concept": "...", "evidence": "...", "importance": "high|medium|low"}}
  ],
  "terminology_fixes": [
    {{"current": "...", "suggested": "...", "reason": "..."}}
  ],
  "overall_assessment": "...",
  "confidence": 0.0-1.0
}}"""

_REVIEW_PROMPT_LEGAL = """\
The Ontology Engineer has proposed the following for Phase {phase}:

```json
{proposal}
```

Domain documents for reference:

{documents}

Legal documents and regulations:

{legal_documents}

Review this proposal from a DOMAIN EXPERT perspective:

1. ACCURACY: Do the proposed terms/definitions match how they're used
   in the documents AND legal/regulatory contexts? Flag any misrepresentations.

2. LEGAL COMPLIANCE: Are there regulatory requirements or legal constraints
   that this proposal must account for? Check compliance requirements.

3. COMPLETENESS: Are there important domain concepts MISSING from
   the proposal that appear in the documents or legal sources? List them.

4. TERMINOLOGY: Are the names/labels what a domain practitioner would
   actually use? Do they align with legal terminology? Suggest corrections.

5. REGULATORY GAPS: Does this proposal adequately address legal obligations,
   permits, licenses, or compliance requirements?

6. EVIDENCE: For each issue, cite relevant document text AND legal sources.

7. VERDICT: Do you approve this proposal for this phase?

Return JSON:
{{
  "approves": true|false,
  "accuracy_issues": [
    {{"term": "...", "issue": "...", "evidence": "...", "legal_context": "..." }}
  ],
  "legal_compliance_issues": [
    {{"requirement": "...", "impact": "...", "evidence": "..."}}
  ],
  "missing_concepts": [
    {{"concept": "...", "evidence": "...", "importance": "high|medium|low"}}
  ],
  "terminology_fixes": [
    {{"current": "...", "suggested": "...", "reason": "..."}}
  ],
  "regulatory_gaps": [
    {{"gap": "...", "requirement": "...", "severity": "high|medium|low"}}
  ],
  "overall_assessment": "...",
  "confidence": 0.0-1.0
}}"""

# Backwards-compat alias
REVIEW_PROMPT_TEMPLATE = _REVIEW_PROMPT_LEGAL


class DomainExpertAgent(BaseAgent):
    """Agent that validates proposals against domain documents.

    The DomainExpert is a *reviewer* — it checks the OntologyEngineer's
    proposals against evidence from the corpus and flags domain-accuracy
    issues.

    Parameters
    ----------
    settings:
        Application configuration.
    document_context:
        Pre-fetched document excerpts from Qdrant. This grounds the
        agent in real domain knowledge.
    """

    role = AgentRole.DOMAIN_EXPERT

    def __init__(
        self,
        settings: Settings | None = None,
        document_context: str = "",
        law_collection: LawCollectionSource | None = None,
        law_graph: LawGraphSource | None = None,
    ) -> None:
        # Select prompt variant based on whether legal sources are available
        has_legal = law_collection is not None or law_graph is not None
        identity = EXPERT_IDENTITY if has_legal else _EXPERT_IDENTITY_BASE
        super().__init__(settings=settings, system_prompt=identity)
        self.document_context = document_context
        self.law_collection = law_collection  # None when legal enrichment disabled
        self.law_graph = law_graph  # None when legal enrichment disabled
        self._has_legal = has_legal

    def set_documents(self, document_context: str) -> None:
        """Update the document context (e.g. between iterations)."""
        self.document_context = document_context

    def query_legal_relationships(self, entity: str) -> dict[str, Any]:
        """Query legal relationships using GraphRAG."""
        return self.law_graph.query_legal_relationships(entity)

    def query_compliance_requirements(self, activity: str) -> dict[str, Any]:
        """Query compliance requirements for an activity."""
        return self.law_graph.query_compliance_requirements(activity)

    def query_legal_precedents(self, concept: str) -> dict[str, Any]:
        """Query legal precedents for a concept."""
        return self.law_graph.query_legal_precedents(concept)

    def fetch_legal_documents(
        self,
        jurisdiction: str | None = None,
        document_type: str | None = None,
        limit: int = 20,
    ) -> str:
        """Fetch legal documents for context."""
        chunks = self.law_collection.fetch_legal_chunks(
            limit=limit,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )
        return "\n\n".join([f"[{chunk.document_name}]\n{chunk.text}" for chunk in chunks])

    def search_legal_precedents(self, query: str, limit: int = 10) -> str:
        """Search for legal precedents."""
        chunks = self.law_collection.search_legal_precedents(query, limit=limit)
        return "\n\n".join([f"[{chunk.document_name}]\n{chunk.text}" for chunk in chunks])

    @ls_traceable(run_type="chain", name="DomainExpert.review")
    def review(
        self,
        phase: Phase,
        proposal: dict[str, Any],
    ) -> AgentMessage:
        """Review a proposal from the OntologyEngineer.

        Args:
            phase: Current Ont-101 phase.
            proposal: The structured proposal to review.

        Returns:
            An ``AgentMessage`` with the review assessment.
        """
        # Fetch legal documents for context (only if law sources available)
        legal_docs = ""
        legal_context = ""
        if self.law_collection is not None:
            legal_docs = self.fetch_legal_documents(limit=10)

        # Query GraphRAG for legal relationships and compliance
        if self.law_graph is not None and "classes" in proposal:
            for cls in proposal["classes"]:
                class_name = cls.get("name", "")
                if class_name:
                    # Query legal relationships for this class
                    legal_rels = self.query_legal_relationships(class_name)
                    if legal_rels.get("relationships"):
                        legal_context += f"\nLegal relationships for {class_name}:\n"
                        for rel in legal_rels["relationships"][:3]:  # Limit to top 3
                            legal_context += f"- {rel.get('type', '')}: {rel.get('target', '')}\n"

                    # Query compliance requirements
                    compliance = self.query_compliance_requirements(class_name)
                    if compliance.get("requirements"):
                        legal_context += f"\nCompliance requirements for {class_name}:\n"
                        for req in compliance["requirements"][:3]:
                            legal_context += f"- {req.get('requirement', '')} (severity: {req.get('severity', 'medium')})\n"

        if self._has_legal:
            legal_enrichment = ""
            if legal_docs or legal_context:
                legal_enrichment = legal_docs[:2000] + legal_context[:1000]
            else:
                legal_enrichment = "(No legal sources found.)"

            user_prompt = _REVIEW_PROMPT_LEGAL.format(
                phase=phase.value,
                proposal=json.dumps(proposal, indent=2, default=str),
                documents=self.document_context[:4000],
                legal_documents=legal_enrichment,
            )
        else:
            user_prompt = _REVIEW_PROMPT_BASE.format(
                phase=phase.value,
                proposal=json.dumps(proposal, indent=2, default=str),
                documents=self.document_context[:4000],
            )

        response = self.call_llm(user_prompt)

        # Parse the review
        issues: list[str] = []
        approves = True
        if isinstance(response, dict):
            approves = response.get("approves", True)
            for acc in response.get("accuracy_issues", []):
                if isinstance(acc, dict):
                    issues.append(f"Accuracy: {acc.get('term', '?')} — {acc.get('issue', '')}")
                else:
                    issues.append(f"Accuracy: {str(acc)}")
            for lc in response.get("legal_compliance_issues", []):
                if isinstance(lc, dict):
                    issues.append(f"Legal: {lc.get('requirement', '?')} — {lc.get('impact', '')}")
                else:
                    issues.append(f"Legal compliance issue: {str(lc)}")
            for rg in response.get("regulatory_gaps", []):
                if isinstance(rg, dict):
                    issues.append(f"Regulatory Gap: {rg.get('gap', '?')} (severity: {rg.get('severity', '?')})")
                else:
                    issues.append(f"Regulatory Gap: {str(rg)}")
            for mc in response.get("missing_concepts", []):
                if isinstance(mc, dict):
                    issues.append(f"Missing: {mc.get('concept', '?')} (importance: {mc.get('importance', '?')})")
                else:
                    issues.append(f"Missing concept: {str(mc)}")
            for tf in response.get("terminology_fixes", []):
                if isinstance(tf, dict):
                    issues.append(f"Rename: '{tf.get('current', '?')}' → '{tf.get('suggested', '?')}'")
                else:
                    issues.append(f"Terminology fix: {str(tf)}")

        return AgentMessage(
            role=self.role,
            phase=phase,
            message_type="review",
            content=response or {},
            reasoning=response.get("overall_assessment", "") if isinstance(response, dict) else str(response),
            issues_raised=issues,
            approves=approves,
        )

    def answer_question(self, question: str) -> AgentMessage:
        """Answer a domain-specific question from the engineer.

        Used when the engineer needs domain clarification during
        proposal generation (e.g., "Is X a type of Y in this domain?").

        Args:
            question: The domain question.

        Returns:
            An ``AgentMessage`` with the answer and evidence.
        """
        user_prompt = f"""Domain question from the Ontology Engineer:

{question}

Domain documents for reference:

{self.document_context[:6000]}

Answer this question based on the domain documents.  Provide:
1. Your answer
2. Evidence from the documents
3. Confidence level (0.0-1.0)

Return JSON:
{{
  "answer": "...",
  "evidence": ["..."],
  "confidence": 0.0-1.0,
  "notes": "..."
}}"""

        response = self.call_llm(user_prompt)

        return AgentMessage(
            role=self.role,
            phase=Phase.SCOPE,  # generic
            message_type="assessment",
            content=response or {},
            reasoning=response.get("answer", "") if response else "",
        )
