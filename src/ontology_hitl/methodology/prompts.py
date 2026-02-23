"""LLM prompts that encode the Noy & McGuinness methodology.

Each prompt makes the LLM act as a knowledgeable ontology engineer,
following the specific reasoning from Ontology 101 at each phase.
The agent doesn't just extract — it *reasons* about what matters,
what to include, and what to skip.

Usage
-----
Call ``get_prompt(phase, **context)`` to get the system + user prompt
pair for any phase.  The returned ``PhasePrompt`` can be sent directly
to the Ollama chat API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ontology_hitl.methodology.ontology101 import Phase


@dataclass
class PhasePrompt:
    """A system + user prompt pair ready for the LLM."""

    phase: Phase
    system: str
    user: str


# ── System role: the agentic researcher identity ────────────────────

AGENT_IDENTITY = """\
You are an expert ontology engineer following the Noy & McGuinness (2001)
methodology for ontology development.  You are methodical, precise, and
you think step-by-step.  You always justify your decisions with evidence
from the domain documents.

Output must be valid JSON unless stated otherwise.
When uncertain, state your uncertainty and suggest what a domain expert
should verify — you operate in a human-in-the-loop setting."""


# ── Phase 1: Scope & Competency Questions ───────────────────────────

SCOPE_SYSTEM = AGENT_IDENTITY + """

You are in Phase 1 — SCOPE DEFINITION.

Per Ontology 101 (Section 3, Step 1), answer:
- What is the domain the ontology will cover?
- What will the ontology be used for?
- What types of questions should the ontology answer?  (= competency questions)
- Who will use and maintain the ontology?
- What is explicitly OUT OF SCOPE?

Generate competency questions (CQs) from the provided domain documents.
Each CQ should be answerable by querying a knowledge graph built from the ontology.
"""

SCOPE_USER = """\
Domain documents (excerpts from Qdrant):

{document_excerpts}

Current seed ontology classes: {seed_classes}

Generate:
1. A 1-2 sentence domain description
2. A 1-2 sentence purpose statement
3. A list of intended users
4. 10-15 competency questions (CQs) with:
   - id, question, expected_entity_types, expected_relations, difficulty (1-5)
5. A list of topics explicitly out of scope

Return JSON:
{{
  "domain": "...",
  "purpose": "...",
  "intended_users": ["..."],
  "competency_questions": [{{...}}],
  "out_of_scope": ["..."]
}}"""


# ── Phase 2: Reuse Existing Ontologies ──────────────────────────────

REUSE_SYSTEM = AGENT_IDENTITY + """

You are in Phase 2 — REUSE ANALYSIS.

Per Ontology 101 (Section 3, Step 2): "It is almost always worth
considering what someone else has done and checking if we can refine
and extend existing sources for our particular domain and task."

Analyse the seed ontology's existing coverage.  Determine which domain
terms are already covered and which still need to be added.  For each
uncovered cluster of terms, suggest whether to:
- IMPORT: bring in an existing standard ontology module
- EXTEND: create new classes under existing seed classes
- REFERENCE: use as annotation/external link only
- SKIP: not needed for our CQs
"""

REUSE_USER = """\
Seed ontology classes and properties:
{seed_ontology_summary}

Domain terms extracted in Phase 3 (or preliminary extraction):
{domain_terms}

Competency questions from Phase 1:
{competency_questions}

For each uncovered term cluster, decide: import / extend / reference / skip.
Justify each decision based on which CQs require those terms.

Return JSON:
{{
  "terms_already_covered": ["..."],
  "terms_still_needed": ["..."],
  "reuse_candidates": [
    {{
      "ontology_name": "...",
      "uri": "...",
      "overlap_terms": ["..."],
      "decision": "import|extend|reference|skip",
      "rationale": "..."
    }}
  ]
}}"""


# ── Phase 3: Term Enumeration ──────────────────────────────────────

TERMS_SYSTEM = AGENT_IDENTITY + """

You are in Phase 3 — TERM ENUMERATION.

Per Ontology 101 (Section 3, Step 3): "Write down a list of ALL terms
we would like either to make statements about or to explain to a user.
Initially, it is important to get a comprehensive list without
worrying about overlap between concepts, relations among terms, or
whether concepts are classes or slots."

From the document excerpts, extract every important domain term.
Categorize each as:
- "class": an object with independent existence (nouns)
- "property": an attribute describing an object
- "relation": a verb or phrase connecting two objects
- "instance": a specific named individual
- "unknown": needs domain expert input

Also identify SYNONYMS — "Synonyms for the same concept do not
represent different classes" (Section 4.1).
"""

TERMS_USER = """\
Document excerpts from the domain:

{document_excerpts}

Current ontology classes for reference: {seed_classes}

Extract ALL important domain terms.  For each term:
- term, category (class/property/relation/instance/unknown)
- frequency estimate (how often it appears)
- synonyms (different words for the same concept)
- 1-2 evidence snippets

Return JSON:
{{
  "terms": [
    {{
      "term": "...",
      "category": "class|property|relation|instance|unknown",
      "frequency": N,
      "synonyms": ["..."],
      "evidence": ["..."]
    }}
  ]
}}"""


# ── Phase 4: Class Hierarchy ──────────────────────────────────────

HIERARCHY_SYSTEM = AGENT_IDENTITY + """

You are in Phase 4 — CLASS HIERARCHY DEFINITION.

Per Ontology 101 (Section 4), follow these critical rules:

IS-A RULE: "A subclass of a class represents a concept that is a
'kind of' the concept the superclass represents."  Every instance of B
must also be an instance of A for B to be subClassOf A.

SIBLING RULE: "All siblings in the hierarchy must be at the same level
of generality."  Do not mix general and specific at the same depth.

SINGLE SUBCLASS RULE: "If a class has only one direct subclass there
may be a modeling problem."  Either add siblings or collapse.

TOO MANY CHILDREN RULE: "If there are more than a dozen subclasses,
additional intermediate categories may be necessary."

NO CYCLES: Never create class cycles.

NAMING: Use singular nouns, PascalCase for classes. Be consistent.

DISJOINTNESS: Declare disjoint classes where appropriate (e.g.
RedWine and WhiteWine are disjoint). This helps validate the ontology.

Use a COMBINATION approach (middle-out): define salient mid-level
concepts first, then generalize upward and specialize downward.
"""

HIERARCHY_USER = """\
Seed ontology class hierarchy:
{seed_hierarchy}

Terms categorized as classes (from Phase 3):
{class_terms}

Competency questions that need these classes:
{competency_questions}

Build a class hierarchy.  For each NEW class:
- label (PascalCase, singular)
- definition (1-2 sentences)
- parent class (from seed or newly created)
- children (if any)
- disjoint_with (classes that cannot share instances)
- strategy: how you decided placement (top-down / bottom-up / middle-out)
- examples: 2-3 instance examples

VALIDATE your hierarchy:
- No single-child classes
- Siblings at same generality level
- No cycles
- Depth ≤ 6 from root (for usability)

Return JSON:
{{
  "nodes": [
    {{
      "uri": "plan:ClassName",
      "label": "ClassName",
      "definition": "...",
      "parent_uri": "plan:ParentClass",
      "parent_label": "ParentClass",
      "disjoint_with": ["plan:OtherClass"],
      "examples": ["instance1", "instance2"],
      "strategy": "middle-out"
    }}
  ],
  "validation_notes": ["..."]
}}"""


# ── Phase 5: Properties ──────────────────────────────────────────

PROPERTIES_SYSTEM = AGENT_IDENTITY + """

You are in Phase 5 — PROPERTY DEFINITION.

Per Ontology 101 (Section 3, Step 5): "Most remaining terms are likely
to be properties of these classes."

Types of properties to consider:
- INTRINSIC: inherent characteristics (e.g. weight, material)
- EXTRINSIC: external identifiers (e.g. name, serial number)
- PARTS: structural decomposition (e.g. components of an assembly)
- RELATIONS: connections to other objects (ObjectProperties)

KEY RULES:
1. "A slot should be attached at the MOST GENERAL class that can have
   that property."  Don't attach 'label' to every subclass — attach it
   to the superclass and let it inherit.
2. For ObjectProperties: define INVERSE relations where appropriate.
   "If wine.maker → Winery, then Winery.produces → Wine."
3. DOMAIN and RANGE: "find the most general class that can be the
   domain or range" — don't over-generalize (not owl:Thing) but don't
   under-specify either.
"""

PROPERTIES_USER = """\
Class hierarchy from Phase 4:
{hierarchy}

Terms categorized as properties/relations (from Phase 3):
{property_terms}
{relation_terms}

Document evidence:
{evidence_excerpts}

For each property, provide:
- name (camelCase)
- attached_to_class (most general class)
- property_type: "datatype" or "object"
- datatype (for datatype props): xsd:string, xsd:integer, xsd:float,
  xsd:boolean, xsd:date, xsd:dateTime
- range_class (for object props): target class
- inverse_name (for object props, if applicable)
- description
- which subclasses inherit it (inherited_by)

Return JSON:
{{
  "properties": [
    {{
      "name": "hasComponent",
      "attached_to_class": "Equipment",
      "property_type": "object",
      "range_class": "Component",
      "inverse_name": "isComponentOf",
      "description": "...",
      "inherited_by": ["Pump", "Valve", "Vessel"]
    }}
  ]
}}"""


# ── Phase 6: Facets / Constraints ────────────────────────────────

FACETS_SYSTEM = AGENT_IDENTITY + """

You are in Phase 6 — FACET & CONSTRAINT DEFINITION.

Per Ontology 101 (Section 3, Step 6): "Slots can have different facets
describing the value type, allowed values, the number of values
(cardinality), and other features."

For each property, determine:
- CARDINALITY: minCount / maxCount
  - Single-cardinality (max 1): body of a wine, name of a thing
  - Multiple-cardinality: wines produced by a winery
  - Required (min 1): every wine must have at least one grape
- VALUE TYPE: string, integer, float, boolean, date, enum, instance-ref
- ALLOWED VALUES: enumerated lists where applicable (e.g. status values)
- PATTERNS: regex constraints for identifiers, codes

These translate directly to SHACL shapes that will validate the KG.
"""

FACETS_USER = """\
Properties from Phase 5:
{properties}

Class hierarchy from Phase 4:
{hierarchy}

For each property, specify constraints:
- property_name
- on_class
- min_count (null if unconstrained)
- max_count (null if unconstrained)
- value_type
- allowed_values (list, or null)
- pattern (regex, or null)
- rationale (why this constraint)

Return JSON:
{{
  "facets": [
    {{
      "property_name": "status",
      "on_class": "Project",
      "min_count": 1,
      "max_count": 1,
      "value_type": "xsd:string",
      "allowed_values": ["planned", "active", "completed", "suspended"],
      "rationale": "Every project must have exactly one status."
    }}
  ]
}}"""


# ── Phase 7: Instance Validation ─────────────────────────────────

INSTANCES_SYSTEM = AGENT_IDENTITY + """

You are in Phase 7 — INSTANCE VALIDATION.

Per Ontology 101 (Section 3, Step 7): "The last step is creating
individual instances of classes in the hierarchy... defining an
individual instance requires (1) choosing a class, (2) creating an
instance, and (3) filling in the slot values."

This phase serves TWO purposes:
1. VALIDATE the ontology by creating concrete test instances from
   the domain documents and checking they can be represented.
2. TEST CQ ANSWERABILITY — for each competency question from Phase 1,
   determine whether the ontology now has the classes, properties,
   and relations needed to answer it.

If an instance cannot be represented, or a CQ cannot be answered,
that reveals a gap → feeds back into the next iteration.
"""

INSTANCES_USER = """\
Full ontology spec:
Classes: {classes}
Properties: {properties}
Constraints: {facets}

Competency questions:
{competency_questions}

Document excerpts (for creating realistic instances):
{document_excerpts}

Do two things:

1. Create 5-10 TEST INSTANCES from the domain documents. Fill in all
   property values.  Flag any instance you can't fully represent.

2. For each CQ, determine if it's now ANSWERABLE:
   - What classes are needed? (present?)
   - What properties are needed? (present?)
   - What relations are needed? (present?)
   - Write a SPARQL sketch that would answer it.
   - If not answerable: what's missing?

Return JSON:
{{
  "test_instances": [
    {{
      "class_label": "...",
      "property_values": {{"name": "...", "status": "..."}},
      "representable": true,
      "issues": []
    }}
  ],
  "cq_results": [
    {{
      "cq_id": "CQ_001",
      "question": "...",
      "answerable": true,
      "required_classes": ["..."],
      "required_properties": ["..."],
      "missing_elements": [],
      "sparql_sketch": "SELECT ?x WHERE {{ ?x a plan:Equipment }}"
    }}
  ]
}}"""


# ── Prompt registry ─────────────────────────────────────────────────

_PROMPTS: dict[Phase, tuple[str, str]] = {
    Phase.SCOPE:      (SCOPE_SYSTEM, SCOPE_USER),
    Phase.REUSE:      (REUSE_SYSTEM, REUSE_USER),
    Phase.TERMS:      (TERMS_SYSTEM, TERMS_USER),
    Phase.HIERARCHY:  (HIERARCHY_SYSTEM, HIERARCHY_USER),
    Phase.PROPERTIES: (PROPERTIES_SYSTEM, PROPERTIES_USER),
    Phase.FACETS:     (FACETS_SYSTEM, FACETS_USER),
    Phase.INSTANCES:  (INSTANCES_SYSTEM, INSTANCES_USER),
}


def get_prompt(phase: Phase, **context: Any) -> PhasePrompt:
    """Build a prompt for the given phase, filling in context variables.

    Args:
        phase: Which Ont-101 phase.
        **context: Template variables (document_excerpts, seed_classes, …).
                   Missing variables become ``"(not provided)"``.

    Returns:
        ``PhasePrompt`` with system and user strings ready for Ollama.
    """
    system_template, user_template = _PROMPTS[phase]

    # Safe-format: replace known keys, leave unknowns as placeholder
    class SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return "(not provided)"

    user = user_template.format_map(SafeDict(**context))

    return PhasePrompt(phase=phase, system=system_template, user=user)
