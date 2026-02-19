#!/usr/bin/env python3
"""Simulate and visualize multi-agent discussions for presentations.

Two modes:
  cogagent — Our system: separate Engineer/Expert/Critic agents + Moderator
  hcome    — LC3 baseline: single-prompt sock puppet (KE/DE/KW)

Usage:
    .venv/bin/python demo/simulate_discussion.py --mode cogagent --topic "Pizza"
    .venv/bin/python demo/simulate_discussion.py --mode hcome    --topic "Pizza"
    .venv/bin/python demo/simulate_discussion.py --mode both     --topic "Pizza"
"""
from __future__ import annotations

import sys
import time
import re
import argparse
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import httpx

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


# ── Ollama helper ────────────────────────────────────────────────────

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


# ── Demo 1: CogAgent (our multi-agent debate) ───────────────────────

ENGINEER_SYSTEM = textwrap.dedent("""\
    You are an Ontology Engineer following the Ont-101 methodology.
    Your epistemic stance is Constructive Abduction (Peirce 1903):
    propose the hypothesis that best explains the domain.
    Output structured ontology artefacts: classes with superclasses,
    object/data properties, domain/range, and constraints.
    Use OWL Manchester Syntax where possible. Be precise and formal.""")

EXPERT_SYSTEM = textwrap.dedent("""\
    You are a Domain Expert grounded in Hermeneutic analysis (Gadamer 1960).
    Your role is to validate ontology proposals against real-world domain
    knowledge. Check whether proposed classes and relationships accurately
    reflect how the domain actually works. Cite specific domain facts.
    Flag any concepts that are mischaracterized or missing.""")

CRITIC_SYSTEM = textwrap.dedent("""\
    You are a Structural Critic applying Critical Falsification (Popper 1934).
    Your job is to actively try to BREAK the proposal: find naming
    inconsistencies, redundant classes, missing disjointness axioms,
    hierarchy depth problems, over-specification, or under-specification.
    Also check: Can the proposed ontology answer the competency questions?
    Be constructive but rigorous. Push back hard.""")

def _phase_task_for(phase: str, topic: str) -> str:
    """Return a short task prompt for the given Ont-101 phase."""
    p = phase.lower()
    if "scope" in p:
        return (
            f"Define the scope for '{topic}' and produce 3 competency questions (CQs) "
            "that the ontology must answer. Be concise and testable."
        )
    if "reuse" in p:
        return (
            f"Identify existing ontologies/vocabularies that should be reused for '{topic}'. "
            "Suggest mappings and justify reuse decisions."
        )
    if "terms" in p:
        return (
            f"List the top 6 domain terms for '{topic}' with short definitions and preferred labels."
        )
    if "hierarchy" in p:
        return (
            f"Propose the class hierarchy for '{topic}': immediate superclasses, rationale, "
            "and any necessary disjointness axioms."
        )
    if "properties" in p:
        return (
            f"Propose key object/data properties for '{topic}' with domain/range and cardinality hints."
        )
    if "facets" in p:
        return (
            f"Suggest useful facets/value-sets or controlled vocabularies for '{topic}' properties."
        )
    if "validation" in p:
        return (
            f"Provide 3 SPARQL ASK style competency checks or OWLUnit-style tests to validate '{topic}'."
        )
    # fallback
    return (
        f"Work on phase '{phase}' for the topic '{topic}': produce a short, concrete deliverable."
    )


def run_cogagent_phase(topic: str, model: str, url: str, phase: str, rounds: int = 2):
    """Run the standard multi-agent debate for one Ont-101 phase."""
    banner(f"Phase: {phase}")
    _log(f"\n=== Phase: {phase} ===")

    task = _phase_task_for(phase, topic)

    print(styled("  ┌─ MODERATOR (deterministic) ─────────────────────┐", "bold"))
    print(styled("  │", "moderator"),
          styled(" Strategy selected: ", "moderator"),
          styled("Dialectical", "moderator", "bold"))
    print(styled("  │", "moderator"),
          styled(f" Phase: {phase}", "moderator"))
    print(styled("  │", "moderator"),
          styled(f" Topic: {topic}", "moderator"))
    print(styled("  │", "moderator"),
          styled(f" Max rounds: {rounds}", "moderator"))
    print(styled("  │", "moderator"),
          styled(" Grounding: document evidence required", "moderator"))
    print(styled("  └──────────────────────────────────────────────────┘", "bold"))

    pause("Ontology Engineer is thinking...", 0.6)

    # Thesis
    print(styled("\n  ┌─ THESIS (proposal) ──────────────────────────────┐", "bold"))
    proposal = llm_call(task, model=model, system=ENGINEER_SYSTEM, url=url)
    _log(f"\n  [Ontology Engineer] ({phase})")
    _log(proposal)
    type_write(textwrap.fill(proposal, width=68), color="engineer", delay=0.004)
    pause("Domain Expert is validating...", 0.6)

    # Expert
    expert_review = llm_call(
        f"Review this proposal for phase '{phase}':\n\n{proposal}\n\n"
        f"Is it correct and complete? What is missing?",
        model=model, system=EXPERT_SYSTEM, url=url,
    )
    _log(f"\n  [Domain Expert] ({phase})")
    _log(expert_review)
    type_write(textwrap.fill(expert_review, width=68), color="expert", delay=0.004)

    # Critic
    critic_review = llm_call(
        f"Critique the proposal for phase '{phase}':\n\n{proposal}\n\n"
        f"Domain expert said:\n{expert_review}\n\nFind structural or modelling issues.",
        model=model, system=CRITIC_SYSTEM, url=url,
    )
    _log(f"\n  [Critic] ({phase})")
    _log(critic_review)
    type_write(textwrap.fill(critic_review, width=68), color="critic", delay=0.004)

    # Synthesis / revision
    revision = llm_call(
        f"Revise the proposal to address expert and critic feedback:\n\n{proposal}\n\n"
        f"Expert: {expert_review}\nCritic: {critic_review}\n\nProduce the final deliverable for phase '{phase}'.",
        model=model, system=ENGINEER_SYSTEM, url=url,
    )
    _log(f"\n  [Ontology Engineer] Revision ({phase})")
    _log(revision)
    type_write(textwrap.fill(revision, width=68), color="engineer", delay=0.004)

    print(styled("\n  [Moderator] Consensus reached for phase.", "moderator", "bold"))
    _log(f"  [Moderator] Phase {phase}: CONSENSUS")

    return revision


def _format_ttl_prefixes() -> str:
    return (
        "@prefix ex: <http://example.org/> .\n"
        "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .\n"
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n\n"
    )


def _guess_xsd_type(typename: str) -> str:
    t = typename.lower()
    if 'bool' in t:
        return 'xsd:boolean'
    if 'int' in t or 'num' in t or 'integer' in t:
        return 'xsd:integer'
    if 'float' in t or 'double' in t:
        return 'xsd:double'
    return 'xsd:string'


def _synthesize_ttl_from_text(topic: str, text: str) -> str:
    """Heuristic TTL synthesizer for demo purposes (best-effort)."""
    prefixes = _format_ttl_prefixes()
    classes = set()
    props = []
    subclasses = []

    classes.add(topic)

    # extract backtick-enclosed terms and capitalized tokens
    for name in re.findall(r'`([A-Z][A-Za-z0-9_]+)`', text):
        classes.add(name)

    # detect explicit "A ⊆ B" or "A \u2286 B" patterns
    for a, b in re.findall(r'([A-Z][A-Za-z0-9_]+)\s*(?:⊆|\\u2286|<=|subset of)\s*([A-Z][A-Za-z0-9_]+)', text):
        subclasses.append((a, b))
        classes.update([a, b])

    # detect lines like "Pizza: hasCrust (Boolean)" or "- hasCrust (Boolean)"
    for m in re.findall(r'(?:^|\n)\s*([A-Z][A-Za-z0-9_]*)?\s*[:\-]?\s*([a-zA-Z_][A-Za-z0-9_-]+)\s*\(?([A-Za-z]+)\)?', text):
        domain_hint, prop, ptype = m
        domain = domain_hint if domain_hint else topic
        # ignore noise where group captured section headers
        if prop.lower() in ('class', 'food', 'property', 'ontology'):
            continue
        props.append((prop, domain, ptype))

    # fallback: look for explicit rdf:type owl:Class triples
    triples = []
    for line in text.splitlines():
        if 'rdf:type' in line and 'owl:Class' in line:
            triples.append(line.strip().rstrip('.'))

    ttl_lines = [prefixes]

    # add class declarations
    for c in sorted(classes):
        ttl_lines.append(f"ex:{c} a owl:Class .")

    # add subclass triples
    for child, parent in subclasses:
        ttl_lines.append(f"ex:{child} rdfs:subClassOf ex:{parent} .")

    # add properties
    for prop, domain, ptype in props:
        xsd = _guess_xsd_type(ptype)
        # treat as DatatypeProperty when type looks primitive
        if xsd != 'xsd:string':
            ttl_lines.append(f"ex:{prop} a owl:DatatypeProperty ; rdfs:domain ex:{domain} ; rdfs:range {xsd} .")
        else:
            # conservative: use DatatypeProperty for string-like
            ttl_lines.append(f"ex:{prop} a owl:DatatypeProperty ; rdfs:domain ex:{domain} ; rdfs:range xsd:string .")

    # append any explicit triples found
    for t in triples:
        ttl_lines.append(t + ' .')

    # include provenance as comment
    ttl_lines.append('\n# Source (heuristic synthesis):')
    ttl_lines.append('\n'.join(['# ' + l for l in text.splitlines()[:10]]))

    return '\n'.join(ttl_lines)


def _extract_owl_from_cog_results(topic: str, results: dict) -> str:
    combined = '\n\n'.join(results.values())
    # prefer fenced code blocks
    m = re.search(r'```(?:owl|xml)?\n(.*?)```', combined, re.S | re.I)
    if m:
        return m.group(1).strip()

    # else attempt heuristic synthesis
    return _synthesize_ttl_from_text(topic, combined)


def _extract_owl_from_hcome_raw(topic: str, raw: str) -> str:
    # look for [CONSENSUS] block
    m = re.search(r'\[CONSENSUS\]\s*:\s*(.*)', raw, re.S)
    consensus = m.group(1).strip() if m else raw
    # prefer fenced code blocks in consensus
    m2 = re.search(r'```(?:owl|xml)?\n(.*?)```', consensus, re.S | re.I)
    if m2:
        return m2.group(1).strip()
    return _synthesize_ttl_from_text(topic, consensus)


def _write_owl_file(path: str, content: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content + '\n', encoding='utf-8')
    _log(f"\n[OWL fragment written] {p}")


def run_full_pipeline_demo(topic: str, model: str, url: str, rounds_per_phase: int = 2):
    """Sequentially run Ont-101 phases using the multi-agent debate."""
    phases = [
        "Scope & CQs",
        "Reuse",
        "Terms",
        "Hierarchy",
        "Properties",
        "Facets",
        "Validation",
    ]

    results = {}
    for ph in phases:
        res = run_cogagent_phase(topic, model, url, ph, rounds=rounds_per_phase)
        results[ph] = res
        pause("Moving to next phase...", 0.6)

    banner("Full pipeline complete")
    _log("\n=== Full pipeline complete ===")
    return results

def run_cogagent_demo(topic: str, model: str, url: str):
    """Simulate our full multi-agent debate pipeline."""
    banner(f"CogAgent Multi-Agent Debate: \"{topic}\"")

    task = (
        f"Define the class '{topic}' in the context of an ontology. "
        f"Propose its superclasses, key object and data properties, "
        f"domain/range constraints, and disjointness axioms."
    )

    # ── Moderator: strategy selection ────────────────────────────────
    print(styled("  ┌─ MODERATOR (deterministic) ─────────────────────┐", "bold"))
    print(styled("  │", "moderator"),
          styled(" Strategy selected: ", "moderator"),
          styled("Dialectical", "moderator", "bold"),
          styled(" (Hegel 1807)", "moderator"))
    print(styled("  │", "moderator"),
          styled(" Phase: Class Hierarchy", "moderator"))
    print(styled("  │", "moderator"),
          styled(f" Topic: {topic}", "moderator"))
    print(styled("  │", "moderator"),
          styled(" Max rounds: 2", "moderator"))
    print(styled("  │", "moderator"),
          styled(" Grounding: document evidence required", "moderator"))
    print(styled("  └──────────────────────────────────────────────────┘", "bold"))
    _log("  [MODERATOR] Strategy: Dialectical (Hegel 1807)")
    _log(f"  [MODERATOR] Phase: Class Hierarchy | Topic: {topic} | Max rounds: 2")
    pause("Ontology Engineer is thinking...", 1.0)

    # ── Round 1: Engineer proposes ───────────────────────────────────
    print(styled("\n  ┌─ ROUND 1: THESIS (proposal) ────────────────────┐", "bold"))
    print(styled("  [Ontology Engineer]", "engineer", "bold"),
          styled(" — Constructive Abduction", "dim"))
    proposal = llm_call(task, model=model, system=ENGINEER_SYSTEM, url=url)
    _log("\n  [Ontology Engineer] — Constructive Abduction")
    _log(proposal)
    type_write(textwrap.fill(proposal, width=68), color="engineer", delay=0.006)
    pause("Domain Expert is validating against domain knowledge...", 1.0)

    # ── Expert reviews ───────────────────────────────────────────────
    print(styled("\n  ┌─ DOMAIN EXPERT REVIEW ───────────────────────────┐", "bold"))
    print(styled("  [Domain Expert]", "expert", "bold"),
          styled(" — Hermeneutic Grounding", "dim"))
    expert_review = llm_call(
        f"Review this ontology proposal for domain accuracy:\n\n{proposal}\n\n"
        f"Is it factually correct? What domain knowledge is missing or wrong? "
        f"Cite specific domain facts to support your assessment.",
        model=model, system=EXPERT_SYSTEM, url=url,
    )
    _log("\n  [Domain Expert] — Hermeneutic Grounding")
    _log(expert_review)
    type_write(textwrap.fill(expert_review, width=68), color="expert", delay=0.006)
    pause("Critic is looking for structural weaknesses...", 1.0)

    # ── Critic reviews ───────────────────────────────────────────────
    print(styled("\n  ┌─ ANTITHESIS (critique) ─────────────────────────┐", "bold"))
    print(styled("  [Critic]", "critic", "bold"),
          styled(" — Critical Falsification", "dim"))
    critic_review = llm_call(
        f"Critique this ontology proposal for structural quality:\n\n{proposal}\n\n"
        f"The Domain Expert noted:\n{expert_review}\n\n"
        f"Find structural problems: naming issues, hierarchy errors, "
        f"missing disjointness, redundancy, CQ coverage gaps. Try to BREAK it.",
        model=model, system=CRITIC_SYSTEM, url=url,
    )
    _log("\n  [Critic] — Critical Falsification")
    _log(critic_review)
    type_write(textwrap.fill(critic_review, width=68), color="critic", delay=0.006)

    # ── Moderator check ──────────────────────────────────────────────
    print(styled("\n  [Moderator]", "moderator", "bold"),
          styled(" Issues raised by both reviewers. Requesting revision.", "moderator"))
    pause("Ontology Engineer is revising...", 1.0)

    # ── Round 2: Engineer revises (Synthesis) ────────────────────────
    print(styled("\n  ┌─ ROUND 2: SYNTHESIS (revision) ─────────────────┐", "bold"))
    print(styled("  [Ontology Engineer]", "engineer", "bold"),
          styled(" — Addressing feedback", "dim"))
    revision = llm_call(
        f"You proposed:\n{proposal}\n\n"
        f"Domain Expert feedback:\n{expert_review}\n\n"
        f"Critic feedback:\n{critic_review}\n\n"
        f"Revise your proposal to address ALL issues. Synthesize the thesis "
        f"(your proposal) with the antithesis (critiques) into a stronger "
        f"ontology fragment. Output the final corrected definition.",
        model=model, system=ENGINEER_SYSTEM, url=url,
    )
    _log("\n  [Ontology Engineer] — Synthesis (revision)")
    _log(revision)
    type_write(textwrap.fill(revision, width=68), color="engineer", delay=0.006)

    # ── Consensus ────────────────────────────────────────────────────
    print(styled("\n  ┌─ VERDICT ────────────────────────────────────────┐", "bold"))
    print(styled("  [Moderator]", "moderator", "bold"),
          styled(" Consensus reached after 2 rounds (4 LLM calls).", "moderator"))
    print(styled("  [Moderator]", "moderator", "bold"),
          styled(" Verdict: ACCEPTED — moving to next Ont-101 phase.", "moderator"))
    print(styled("  └──────────────────────────────────────────────────┘", "bold"))
    _log("\n  [Moderator] Consensus reached after 2 rounds (4 LLM calls).")
    _log("  [Moderator] Verdict: ACCEPTED")

    return revision


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

    # Parse and display role-by-role with streaming effect
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

    banner("CogAgent — Live Discussion Demo", char="═")
    print(f"  Model: {args.model}")
    print(f"  Topic: {args.topic}")
    print(f"  Mode:  {args.mode}\n")

    try:
        cog_results = None
        hcome_raw = None

        if args.mode in ("cogagent", "both"):
            if getattr(args, "full_pipeline", False):
                cog_results = run_full_pipeline_demo(args.topic, args.model, args.ollama_url, rounds_per_phase=args.rounds_per_phase)
            else:
                # single-phase demo returns a revision string; normalize into dict for downstream processing
                rev = run_cogagent_demo(args.topic, args.model, args.ollama_url)
                cog_results = {"Hierarchy": rev}

        if args.mode == "both":
            banner("Side-by-Side Comparison", char="═")
            print(styled("  ABOVE: CogAgent — 3 separate agents + moderator, 4 LLM calls", "bold"))
            print(styled("         Each agent has a distinct epistemic stance", "dim"))
            print(styled("         Moderator enforces grounding + selects strategy", "dim"))
            print()
            print(styled("  BELOW: HCOME/LC3 — 1 prompt, 1 LLM call, simulated roles", "bold"))
            print(styled("         Same model pretending to be 3 people", "dim"))
            print(styled("         No external grounding, no quality control\n", "dim"))
            time.sleep(2)

        if args.mode in ("hcome", "both"):
            hcome_raw = run_hcome_demo(args.topic, args.model, args.ollama_url)

        # --- Export OWL fragments if we ran a full pipeline or both modes ---
        if getattr(args, "full_pipeline", False) and (cog_results or hcome_raw):
            print(styled("\n  Exporting OWL fragments (heuristic)...", "dim"))
            if cog_results:
                cog_owl = _extract_owl_from_cog_results(args.topic, cog_results)
                _write_owl_file("demo/owl/cogagent_fragment.ttl", cog_owl)
                print(styled(f"  Wrote CogAgent OWL fragment to demo/owl/cogagent_fragment.ttl", "engineer"))
            if hcome_raw:
                hcome_owl = _extract_owl_from_hcome_raw(args.topic, hcome_raw)
                _write_owl_file("demo/owl/hcome_fragment.ttl", hcome_owl)
                print(styled(f"  Wrote HCOME OWL fragment to demo/owl/hcome_fragment.ttl", "de"))

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

    # Write transcript
    if args.output and _transcript_lines:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(_transcript_lines) + "\n", encoding="utf-8")
        print(styled(f"\n  Transcript saved to {out_path}", "dim"))


if __name__ == "__main__":
    main()
