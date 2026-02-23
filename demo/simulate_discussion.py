#!/usr/bin/env python3
"""Simulate and visualize multi-agent discussions for presentations.

Two modes:
  cogagent — Our system: uses the REAL AgentTeam pipeline from src/
  hcome    — LC3 baseline: single-prompt sock puppet (KE/DE/KW)

Usage:
    .venv/bin/python demo/simulate_discussion.py --mode cogagent --topic "Pizza"
    .venv/bin/python demo/simulate_discussion.py --mode hcome    --topic "Pizza"
    .venv/bin/python demo/simulate_discussion.py --mode both     --topic "Pizza"
"""
from __future__ import annotations

import json
import sys
import time
import re
import argparse
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx

from ontology_hitl.core.config import Settings
from ontology_hitl.agents.team import AgentTeam
from ontology_hitl.agents.base import AgentRole, DebateVerdict
from ontology_hitl.methodology.ontology101 import Phase

# ── Transcript logging ───────────────────────────────────────────────

_transcript_lines: list[str] = []


def _log(text: str):
    """Append a line to the in-memory transcript."""
    _transcript_lines.append(text)


# ── ANSI styling ─────────────────────────────────────────────────────

C = {
    "engineer":   "\033[94m",
    "expert":     "\033[92m",
    "critic":     "\033[91m",
    "moderator":  "\033[90m",
    "ke":         "\033[96m",
    "de":         "\033[93m",
    "kw":         "\033[95m",
    "consensus":  "\033[97m",
    "reset":      "\033[0m",
    "bold":       "\033[1m",
    "dim":        "\033[2m",
}

_ROLE_COLORS = {
    AgentRole.ONTOLOGY_ENGINEER: "engineer",
    AgentRole.DOMAIN_EXPERT:     "expert",
    AgentRole.CRITIC:            "critic",
}

_ROLE_LABELS = {
    AgentRole.ONTOLOGY_ENGINEER: "Ontology Engineer",
    AgentRole.DOMAIN_EXPERT:     "Domain Expert",
    AgentRole.CRITIC:            "Critic",
}

_ROLE_STANCES = {
    AgentRole.ONTOLOGY_ENGINEER: "Constructive Abduction",
    AgentRole.DOMAIN_EXPERT:     "Hermeneutic Grounding",
    AgentRole.CRITIC:            "Critical Falsification",
}


def styled(text: str, *styles: str) -> str:
    prefix = "".join(C.get(s, "") for s in styles)
    return f"{prefix}{text}{C['reset']}"


def banner(text: str, char: str = "─", width: int = 72):
    print(f"\n{C['bold']}{char * width}")
    print(f"  {text}")
    print(f"{char * width}{C['reset']}\n")
    _log(f"\n{char * width}")
    _log(f"  {text}")
    _log(f"{char * width}\n")


def type_write(text: str, color: str = "reset", delay: float = 0.008):
    """Simulate typing with color."""
    col = C.get(color, C["reset"])
    for char in text:
        sys.stdout.write(f"{col}{char}{C['reset']}")
        sys.stdout.flush()
        time.sleep(delay)
    print()


def pause(label: str = "", seconds: float = 1.0):
    if label:
        print(styled(f"  ⏳ {label}", "dim"))
    time.sleep(seconds)


# ── Ollama helper (only used for HCOME baseline) ────────────────────

def llm_call(
    prompt: str,
    model: str = "llama3.2:3b",
    system: str | None = None,
    url: str = "http://localhost:18135",
    temperature: float = 0.7,
) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = httpx.post(
        f"{url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 1024},
        },
        timeout=600.0,
    )
    resp.raise_for_status()
    text = resp.json()["message"]["content"]
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    return text


# ── Phase ↔ human label mapping ─────────────────────────────────────

_PHASE_LABELS = {
    Phase.SCOPE:      "Scope & CQs",
    Phase.REUSE:      "Reuse",
    Phase.TERMS:      "Terms",
    Phase.HIERARCHY:  "Hierarchy",
    Phase.PROPERTIES: "Properties",
    Phase.FACETS:     "Facets",
    Phase.INSTANCES:  "Validation",
}


# ── Build context for a phase (uses AgentTeam helpers) ───────────────

def _build_context_for_phase(
    team: AgentTeam,
    phase: Phase,
    topic: str,
    accumulated: dict,
) -> str:
    """Build the context string for a phase using AgentTeam builders.

    For phases that depend on earlier results we pass accumulated data.
    For a lightweight demo without a Qdrant corpus, we synthesize
    minimal document text from the topic name.
    """
    docs_text = accumulated.get("docs_text", "")
    seed_cls = accumulated.get("seed_cls", "(none)")
    seed_props = accumulated.get("seed_props", "(none)")

    if phase == Phase.SCOPE:
        return team.build_scope_context(docs_text, seed_cls)

    if phase == Phase.REUSE:
        cqs_text = json.dumps(accumulated.get("cqs", [])[:10], indent=2)
        term_preview = accumulated.get("term_preview", topic)
        return team.build_reuse_context(seed_cls, seed_props, term_preview, cqs_text)

    if phase == Phase.TERMS:
        return team.build_terms_context(docs_text, seed_cls)

    if phase == Phase.HIERARCHY:
        class_terms = accumulated.get("class_terms", [topic])
        cqs_text = json.dumps(accumulated.get("cqs", [])[:10], indent=2)
        seed_hier = accumulated.get("seed_hier", "(no hierarchy provided)")
        return team.build_hierarchy_context(seed_hier, class_terms, cqs_text)

    if phase == Phase.PROPERTIES:
        hier_text = json.dumps(accumulated.get("hierarchy_nodes", []), indent=2)
        prop_terms = accumulated.get("prop_terms", [])
        rel_terms = accumulated.get("rel_terms", [])
        return team.build_properties_context(hier_text, prop_terms, rel_terms, docs_text)

    if phase == Phase.FACETS:
        props_text = json.dumps(accumulated.get("properties", []), indent=2)
        hier_text = json.dumps(accumulated.get("hierarchy_nodes", []), indent=2)
        return team.build_facets_context(props_text, hier_text)

    if phase == Phase.INSTANCES:
        classes_text = json.dumps(accumulated.get("hierarchy_nodes", []), indent=2)
        props_text = json.dumps(accumulated.get("properties", []), indent=2)
        facets_text = json.dumps(accumulated.get("facets", []), indent=2)
        cqs_text = json.dumps(accumulated.get("cqs", [])[:15], indent=2)
        return team.build_instances_context(
            classes_text, props_text, facets_text, cqs_text, docs_text,
        )

    return f"Work on phase '{phase.value}' for the topic '{topic}'."


# ── Visualize a DebateOutcome ────────────────────────────────────────

def _format_content(content: dict | str | None) -> str:
    """Render agent content as readable text."""
    if content is None:
        return "(empty)"
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, indent=2, default=str, ensure_ascii=False)
    except Exception:
        return str(content)


def _display_debate(outcome, phase_label: str, topic: str):
    """Pretty-print a real DebateOutcome with ANSI styling."""
    banner(f"Phase: {phase_label}")
    _log(f"\n=== Phase: {phase_label} ===")

    # Moderator header
    print(styled("  ┌─ MODERATOR (deterministic) ─────────────────────┐", "bold"))
    print(styled("  │", "moderator"),
          styled(" Strategy selected: ", "moderator"),
          styled("Dialectical", "moderator", "bold"))
    print(styled("  │", "moderator"),
          styled(f" Phase: {phase_label}", "moderator"))
    print(styled("  │", "moderator"),
          styled(f" Topic: {topic}", "moderator"))
    print(styled("  │", "moderator"),
          styled(f" Rounds: {outcome.rounds}", "moderator"))
    print(styled("  │", "moderator"),
          styled(" Grounding: document evidence required", "moderator"))
    print(styled("  └──────────────────────────────────────────────────┘", "bold"))
    _log(f"  [MODERATOR] Phase: {phase_label} | Topic: {topic} | Rounds: {outcome.rounds}")

    # Show each agent message
    round_num = 0
    for msg in outcome.messages:
        color = _ROLE_COLORS.get(msg.role, "reset")
        label = _ROLE_LABELS.get(msg.role, msg.role.value)
        stance = _ROLE_STANCES.get(msg.role, "")

        if msg.message_type == "proposal":
            round_num += 1
            print(styled(f"\n  ┌─ ROUND {round_num}: THESIS (proposal) ────────────────────┐", "bold"))
            print(styled(f"  [{label}]", color, "bold"),
                  styled(f" — {stance}", "dim"))
            pause(f"{label} is thinking...", 0.4)
        elif msg.message_type == "review":
            header = "DOMAIN EXPERT REVIEW" if msg.role == AgentRole.DOMAIN_EXPERT else "ANTITHESIS (critique)"
            print(styled(f"\n  ┌─ {header} ───────────────────────────┐", "bold"))
            print(styled(f"  [{label}]", color, "bold"),
                  styled(f" — {stance}", "dim"))
            if msg.role == AgentRole.DOMAIN_EXPERT:
                pause("Domain Expert is validating against domain knowledge...", 0.4)
            else:
                pause("Critic is looking for structural weaknesses...", 0.4)
        elif msg.message_type == "revision":
            round_num += 1
            print(styled(f"\n  ┌─ ROUND {round_num}: SYNTHESIS (revision) ─────────────────┐", "bold"))
            print(styled(f"  [{label}]", color, "bold"),
                  styled(" — Addressing feedback", "dim"))
            pause(f"{label} is revising...", 0.4)

        content_text = _format_content(msg.content)
        _log(f"\n  [{label}] ({msg.message_type})")
        _log(content_text)
        type_write(textwrap.fill(content_text[:2000], width=68), color=color, delay=0.003)

        # Show issues if any
        if msg.issues_raised:
            for issue in msg.issues_raised[:5]:
                print(styled(f"    ⚠ {issue[:120]}", color))

        # Show approval status for reviews
        if msg.message_type == "review" and msg.approves is not None:
            status = "✓ APPROVED" if msg.approves else "✗ REJECTED"
            print(styled(f"    {status}", color, "bold"))

    # Verdict
    verdict_text = {
        DebateVerdict.CONSENSUS: "Consensus reached",
        DebateVerdict.REVISED:   "Proposal revised and accepted",
        DebateVerdict.PARTIAL:   "Partial agreement (some issues escalated)",
        DebateVerdict.ESCALATED: "Escalated — needs human review",
    }.get(outcome.verdict, outcome.verdict.value)

    llm_calls = len(outcome.messages)
    print(styled("\n  ┌─ VERDICT ────────────────────────────────────────┐", "bold"))
    print(styled("  [Moderator]", "moderator", "bold"),
          styled(f" {verdict_text} after {outcome.rounds} round(s) ({llm_calls} LLM calls).", "moderator"))
    if outcome.resolved_issues:
        print(styled(f"  [Moderator]", "moderator", "bold"),
              styled(f" Resolved {len(outcome.resolved_issues)} issue(s).", "moderator"))
    if outcome.escalated_questions:
        print(styled(f"  [Moderator]", "moderator", "bold"),
              styled(f" Escalated {len(outcome.escalated_questions)} question(s) for HITL:", "moderator"))
        for q in outcome.escalated_questions[:10]:
            q_text = q.question if hasattr(q, "question") else str(q)
            print(styled(f"    → {q_text[:100]}", "moderator"))
            _log(f"    → {q_text}")
        if len(outcome.escalated_questions) > 10:
            remaining = len(outcome.escalated_questions) - 10
            print(styled(f"    ... and {remaining} more", "dim"))
    print(styled("  └──────────────────────────────────────────────────┘", "bold"))
    _log(f"  [Moderator] {verdict_text} — {llm_calls} LLM calls")


# ── Accumulate results between phases ────────────────────────────────

def _accumulate(accumulated: dict, phase: Phase, proposal: dict):
    """Extract structured data from a phase outcome for downstream phases."""
    if phase == Phase.SCOPE:
        accumulated["cqs"] = proposal.get("competency_questions", [])

    elif phase == Phase.TERMS:
        terms = proposal.get("terms", [])
        accumulated["class_terms"] = [
            t["term"] for t in terms
            if isinstance(t, dict) and t.get("category") == "class"
        ]
        accumulated["prop_terms"] = [
            t["term"] for t in terms
            if isinstance(t, dict) and t.get("category") == "property"
        ]
        accumulated["rel_terms"] = [
            t["term"] for t in terms
            if isinstance(t, dict) and t.get("category") == "relation"
        ]

    elif phase == Phase.HIERARCHY:
        nodes = proposal.get("nodes", [])
        accumulated["hierarchy_nodes"] = [
            {"label": n.get("label", ""), "parent": n.get("parent_label", "")}
            for n in nodes if isinstance(n, dict)
        ]

    elif phase == Phase.PROPERTIES:
        props = proposal.get("properties", [])
        accumulated["properties"] = [
            {"name": p.get("name", ""), "on": p.get("attached_to_class", ""),
             "type": p.get("property_type", "datatype")}
            for p in props if isinstance(p, dict)
        ]

    elif phase == Phase.FACETS:
        facets = proposal.get("facets", [])
        accumulated["facets"] = [
            {"prop": f.get("property_name", ""), "on": f.get("on_class", ""),
             "min": f.get("min_count"), "max": f.get("max_count")}
            for f in facets if isinstance(f, dict)
        ]


# ── Domain presets ───────────────────────────────────────────────────

_DOMAIN_PRESETS: dict[str, dict] = {
    "pizza": {
        "topic": "Pizza",
        "document_context": (
            "Pizza is a popular baked dish originating from Italy consisting of a round, flattened dough base "
            "topped with tomato sauce, cheese, and a variety of toppings (e.g. pepperoni, mushrooms, vegetables). "
            "Key concepts include crust type (thin, thick, stuffed), sauce variants, cheese varieties, regional styles "
            "(Neapolitan, New York, Sicilian), cooking methods (wood-fired, oven-baked), and serving/portioning. "
            "Relevant metadata: allergens (gluten, dairy), dietary variants (vegetarian, vegan, gluten-free), "
            "and common commercial attributes (size, slice count, SKU)."
        ),
        "legal_enrichment": False,
        "description": "General demo — lightweight pizza document context (prevents hallucination)",
    },
    "sar": {
        "topic": "Search and Rescue Operations",
        "document_context": (
            "Search and rescue (SAR) operations involve the search for and provision "
            "of aid to people who are in distress or imminent danger. SAR operations "
            "include mountain rescue, ground search, urban search and rescue (USAR), "
            "maritime rescue, and combat search and rescue (CSAR). Key concepts include "
            "incident command systems, resource management, casualty triage, evacuation "
            "procedures, and inter-agency coordination."
        ),
        "legal_enrichment": True,
        "description": "SAR domain — with legal enrichment (LC3 comparison)",
    },
    "nuclear": {
        "topic": "Nuclear Decommissioning",
        "document_context": (
            "Nuclear decommissioning involves the administrative and technical actions "
            "taken to safely shut down, dismantle, and manage the radioactive waste "
            "from nuclear facilities. Key regulatory frameworks include the German "
            "Atomgesetz (AtG), Strahlenschutzverordnung (StrlSchV), and European "
            "nuclear safety directives. Concepts include Stilllegung, Rückbau, "
            "Freigabe, Zwischen- und Endlagerung, and Umweltverträglichkeitsprüfung."
        ),
        "legal_enrichment": True,
        "description": "Nuclear decommissioning — full legal+regulatory framework",
    },
}


# ── Demo 1: CogAgent — uses the REAL pipeline ───────────────────────

def _create_settings(
    model: str, url: str, legal_enrichment: bool = False,
) -> Settings:
    """Create Settings configured for demo mode (no Qdrant/Fuseki required)."""
    return Settings(
        ollama_url=url,
        ollama_model=model,
        entity_linking_enabled=False,
        embedding_advisor_enabled=False,
        ensemble_enabled=False,
        feedback_learning_enabled=False,
        provenance_enabled=False,
        wandb_enabled=False,
        legal_enrichment_enabled=legal_enrichment,
    )


def run_cogagent_demo(
    topic: str,
    model: str,
    url: str,
    document_context: str = "",
    legal_enrichment: bool = False,
):
    """Run a single Hierarchy-phase debate using the real AgentTeam."""
    banner(f"CogAgent Multi-Agent Debate: \"{topic}\"")
    _log(f"\n=== CogAgent Multi-Agent Debate: \"{topic}\" ===")

    settings = _create_settings(model, url, legal_enrichment)
    team = AgentTeam(
        settings=settings,
        document_context=document_context,
        max_debate_rounds=2,
        output_dir=Path("demo/owl"),
    )

    context = team.build_hierarchy_context(
        seed_hierarchy="(no seed hierarchy)",
        class_terms=[topic],
        cqs_text="[]",
    )
    outcome = team.run_debate(Phase.HIERARCHY, context)

    _display_debate(outcome, "Hierarchy", topic)

    return outcome


def run_full_pipeline_demo(
    topic: str,
    model: str,
    url: str,
    rounds_per_phase: int = 2,
    document_context: str = "",
    legal_enrichment: bool = False,
):
    """Run all 7 Ont-101 phases using the real AgentTeam pipeline."""
    banner(f"CogAgent Full Pipeline: \"{topic}\"")
    _log(f"\n=== CogAgent Full Pipeline: \"{topic}\" ===")

    settings = _create_settings(model, url, legal_enrichment)
    output_dir = Path("demo/owl")
    output_dir.mkdir(parents=True, exist_ok=True)

    team = AgentTeam(
        settings=settings,
        document_context=document_context,
        max_debate_rounds=rounds_per_phase,
        output_dir=output_dir,
    )

    accumulated: dict = {
        "docs_text": document_context,
        "seed_cls": "(none)",
        "seed_props": "(none)",
        "seed_hier": "(no hierarchy provided)",
        "term_preview": topic,
    }

    results: dict[str, dict] = {}

    for phase in Phase:
        phase_label = _PHASE_LABELS.get(phase, phase.value)
        context = _build_context_for_phase(team, phase, topic, accumulated)

        outcome = team.run_debate(phase, context)
        team.save_debate(outcome)

        _display_debate(outcome, phase_label, topic)

        proposal = outcome.final_proposal
        _accumulate(accumulated, phase, proposal)
        results[phase_label] = proposal

        if phase == Phase.SCOPE:
            cqs = proposal.get("competency_questions", [])
            team.set_competency_questions(cqs)

        pause("Moving to next phase...", 0.6)

    banner("Full pipeline complete")
    _log("\n=== Full pipeline complete ===")
    return results


# ── OWL export helpers ───────────────────────────────────────────────

def _format_ttl_prefixes() -> str:
    return (
        "@prefix ex: <http://example.org/> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
    )


def _synthesize_ttl_from_proposal(topic: str, results: dict) -> str:
    """Synthesize TTL from the structured JSON proposals."""
    prefixes = _format_ttl_prefixes()
    ttl_lines = [prefixes]

    hierarchy = results.get("Hierarchy", {})
    nodes = hierarchy.get("nodes", []) if isinstance(hierarchy, dict) else []
    for n in nodes:
        if isinstance(n, dict):
            label = n.get("label", "")
            parent = n.get("parent_label", "")
            if label:
                ttl_lines.append(f"ex:{label} a owl:Class .")
                if parent:
                    ttl_lines.append(f"ex:{label} rdfs:subClassOf ex:{parent} .")

    props_phase = results.get("Properties", {})
    props = props_phase.get("properties", []) if isinstance(props_phase, dict) else []
    for p in props:
        if isinstance(p, dict):
            name = p.get("name", "")
            domain = p.get("attached_to_class", "")
            ptype = p.get("property_type", "datatype")
            if name:
                owl_type = "owl:ObjectProperty" if ptype == "object" else "owl:DatatypeProperty"
                line = f"ex:{name} a {owl_type}"
                if domain:
                    line += f" ; rdfs:domain ex:{domain}"
                ttl_lines.append(line + " .")

    if len(ttl_lines) <= 1:
        ttl_lines.append(f"ex:{topic} a owl:Class .")

    return "\n".join(ttl_lines)


def _extract_owl_from_hcome_raw(topic: str, raw: str) -> str:
    m = re.search(r'\[CONSENSUS\]\s*:\s*(.*)', raw, re.S)
    consensus = m.group(1).strip() if m else raw
    m2 = re.search(r'```(?:owl|xml|turtle|ttl)?\n(.*?)```', consensus, re.S | re.I)
    if m2:
        return m2.group(1).strip()
    return f"{_format_ttl_prefixes()}ex:{topic} a owl:Class .\n"


def _write_owl_file(path: str, content: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content + '\n', encoding='utf-8')
    _log(f"\n[OWL fragment written] {p}")


# ── Demo 2: HCOME sock puppet (LC3 baseline) ────────────────────────

def run_hcome_demo(topic: str, model: str, url: str):
    """Simulate the HCOME/LC3 single-prompt approach."""
    banner(f"HCOME / LC3 Sock Puppet: \"{topic}\"")

    task = (
        f"Define the class '{topic}' in the context of an ontology. "
        f"Propose its superclasses, key properties, and constraints."
    )

    hcome_prompt = (
        "You are an AI assistant simulating a Collaborative Ontology "
        "Engineering (COE) team. Create three instances of yourself "
        "playing three different roles in the team based on the HCOME "
        "collaborative ontology engineering methodology: "
        "1. Knowledge Engineer (KE): Responsible for formalization and "
        "logical consistency. "
        "2. Domain Expert (DE): Provides deep subject matter expertise. "
        "3. Knowledge Worker (KW): Focuses on practical application. "
        "\n\nTask: Discuss the problem among the three roles. Each role "
        "must provide their perspective, critique others, and agree on "
        "a single consensus answer. "
        "\n\nFormat your response EXACTLY as:\n"
        "[KE]: <text>\n[DE]: <text>\n[KW]: <text>\n...\n"
        "[CONSENSUS]: <The final answer>\n"
        f"\n\nProblem:\n{task}"
    )

    print(styled("  Single LLM call — one prompt, three simulated roles", "dim"))
    print(styled("  No external grounding, no moderator, no drift detection", "dim"))
    pause("Generating entire dialogue in one call...", 1.0)

    raw = llm_call(hcome_prompt, model=model, url=url)
    _log("\n  [HCOME — single LLM call, simulated roles]")
    _log(raw)

    parts = re.split(r'(\[(?:KE|DE|KW|CONSENSUS)\]:)', raw)

    role_map = {
        "[KE]:": ("Knowledge Engineer (KE)", "ke"),
        "[DE]:": ("Domain Expert (DE)", "de"),
        "[KW]:": ("Knowledge Worker (KW)", "kw"),
        "[CONSENSUS]:": ("CONSENSUS", "consensus"),
    }

    current_color = "reset"
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in role_map:
            label, current_color = role_map[part]
            print(styled(f"\n  [{label}]", current_color, "bold"))
            time.sleep(0.4)
        else:
            type_write(textwrap.fill(part, width=68), color=current_color, delay=0.006)
            time.sleep(0.3)

    print(styled("\n  Done — 1 LLM call total.", "dim"))
    return raw


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Simulate multi-agent ontology discussions for presentations",
    )
    parser.add_argument(
        "--mode", choices=["cogagent", "hcome", "both"], default="both",
        help="Which system to demonstrate (default: both)",
    )
    parser.add_argument(
        "--domain", choices=list(_DOMAIN_PRESETS.keys()),
        default=None,
        help="Domain preset (overrides --topic; sets document context & legal enrichment)",
    )
    parser.add_argument(
        "--topic", default="Pizza",
        help="Ontology concept to define (e.g. 'Pizza', 'Alzheimer Disease')",
    )
    parser.add_argument(
        "--model", default="llama3.2:3b",
        help="Ollama model name",
    )
    parser.add_argument(
        "--ollama-url", default="http://localhost:18135",
        help="Ollama server URL",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write transcript to file (plain text, no ANSI codes)",
    )
    parser.add_argument(
        "--full-pipeline", action="store_true",
        help="Run full 7-phase Ont-101 pipeline (cogagent mode)",
    )
    parser.add_argument(
        "--rounds-per-phase", type=int, default=2,
        help="Number of debate rounds per phase (default: 2)",
    )
    args = parser.parse_args()

    # Resolve domain preset
    domain_preset = _DOMAIN_PRESETS.get(args.domain or "", {})
    topic = domain_preset.get("topic", args.topic) if args.domain else args.topic
    document_context = domain_preset.get("document_context", "")
    legal_enrichment = domain_preset.get("legal_enrichment", False)
    domain_desc = domain_preset.get("description", "custom")

    banner("CogAgent — Live Discussion Demo", char="═")
    print(f"  Model:   {args.model}")
    print(f"  Topic:   {topic}")
    print(f"  Mode:    {args.mode}")
    if args.domain:
        print(f"  Domain:  {args.domain} ({domain_desc})")
        print(f"  Legal:   {'enabled' if legal_enrichment else 'disabled'}")
    print(f"  Source:  ontology_hitl.agents.team.AgentTeam (real pipeline)\n")

    try:
        cog_results = None
        hcome_raw = None

        if args.mode in ("cogagent", "both"):
            if getattr(args, "full_pipeline", False):
                cog_results = run_full_pipeline_demo(
                    topic, args.model, args.ollama_url,
                    rounds_per_phase=args.rounds_per_phase,
                    document_context=document_context,
                    legal_enrichment=legal_enrichment,
                )
            else:
                outcome = run_cogagent_demo(
                    topic, args.model, args.ollama_url,
                    document_context=document_context,
                    legal_enrichment=legal_enrichment,
                )
                cog_results = {"Hierarchy": outcome.final_proposal}

        if args.mode == "both":
            banner("Side-by-Side Comparison", char="═")
            print(styled("  ABOVE: CogAgent — real AgentTeam pipeline", "bold"))
            print(styled("         3 separate agents + deterministic moderator", "dim"))
            print(styled("         Each agent has a distinct epistemic stance", "dim"))
            print(styled("         System prompts from src/ontology_hitl/agents/", "dim"))
            print()
            print(styled("  BELOW: HCOME/LC3 — 1 prompt, 1 LLM call, simulated roles", "bold"))
            print(styled("         Same model pretending to be 3 people", "dim"))
            print(styled("         No external grounding, no quality control\n", "dim"))
            time.sleep(2)

        if args.mode in ("hcome", "both"):
            hcome_raw = run_hcome_demo(topic, args.model, args.ollama_url)

        if getattr(args, "full_pipeline", False) and (cog_results or hcome_raw):
            print(styled("\n  Exporting OWL fragments...", "dim"))
            if cog_results:
                cog_owl = _synthesize_ttl_from_proposal(topic, cog_results)
                _write_owl_file("demo/owl/cogagent_fragment.ttl", cog_owl)
                print(styled("  Wrote CogAgent OWL fragment to demo/owl/cogagent_fragment.ttl", "engineer"))
            if hcome_raw:
                hcome_owl = _extract_owl_from_hcome_raw(topic, hcome_raw)
                _write_owl_file("demo/owl/hcome_fragment.ttl", hcome_owl)
                print(styled("  Wrote HCOME OWL fragment to demo/owl/hcome_fragment.ttl", "de"))

        banner("Demo Complete", char="═")
        if args.mode == "both":
            print(styled("  Key difference:", "bold"))
            print(styled("  • CogAgent: genuine perspectival separation, grounded review, iterative", "engineer"))
            print(styled("  • HCOME:    single model role-playing, no external checks, one-shot\n", "de"))

    except httpx.ConnectError:
        print(styled("\n  ERROR: Cannot connect to Ollama. Is it running?", "critic", "bold"))
        print(f"  Tried: {args.ollama_url}")
        sys.exit(1)
    except KeyboardInterrupt:
        print(styled("\n  Demo interrupted.", "dim"))

    if args.output and _transcript_lines:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(_transcript_lines) + "\n", encoding="utf-8")
        print(styled(f"\n  Transcript saved to {out_path}", "dim"))


if __name__ == "__main__":
    main()
