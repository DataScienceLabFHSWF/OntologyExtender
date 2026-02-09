# Expert Review Guide

## Overview

The OntologyExtender uses a multi-agent system where three AI agents
(OntologyEngineer, DomainExpert, Critic) collaborate to extend the
ontology. Most decisions are resolved autonomously through structured
debates. As a human reviewer, **you only handle escalated disagreements**
— cases where the agents could not reach consensus.

## How the System Works

The system follows the **Ontology 101 methodology** (Noy & McGuinness, 2001)
across seven phases:

1. **Scope & Competency Questions** — what the ontology should cover
2. **Reuse Analysis** — existing ontologies to incorporate
3. **Term Enumeration** — important domain terms from documents
4. **Class Hierarchy** — taxonomic structure of classes
5. **Property Definition** — data and object properties
6. **Facet Specification** — cardinality, ranges, constraints
7. **Instance Validation** — verification against sample data

Each phase runs as a **debate**:
- The OntologyEngineer proposes artefacts
- The DomainExpert reviews against document evidence
- The Critic checks structural quality and consistency
- If they disagree after multiple rounds → **the question comes to you**

## What You Review

You will see **escalated questions** — specific points of disagreement
that the agents could not resolve. Each question includes:

1. **Phase** — which Ont-101 phase the question arose in
2. **Context** — the agent discussion leading to the disagreement
3. **The specific question** — what needs your decision
4. **Agent positions** — what each agent proposed and why
5. **Document evidence** — relevant excerpts from the source documents

### Example Escalated Questions

- *"Should `NuclearFacility` be a subclass of `DomainConstant` or `PhysicalEntity`? The DomainExpert found evidence for both."*
- *"The Critic flagged that `DecommissioningPhase` overlaps with `Action`. Should we merge them?"*
- *"Is `RegulatoryPermit` domain-specific enough to warrant its own class, or should it be a property of `Action`?"*

## Decision Options

| Decision | When to use |
|----------|-------------|
| **Accept proposal** | The OntologyEngineer's latest revision is correct |
| **Accept alternative** | A reviewer agent's suggestion is better |
| **Provide guidance** | Neither position is right — give direction for the agents |
| **Defer** | You need more information — agents will gather it in the next iteration |

## Tips

- Trust the agents' consensus — only escalated items need your attention
- The DomainExpert's reviews are grounded in actual document excerpts
- The Critic catches structural issues (naming, hierarchy depth, redundancy)
- If agents escalated it, the disagreement is usually substantive
- Your guidance feeds back into the next iteration's debates
- Provide rationale — agents learn from your reasoning patterns

## Running a Review Session

```bash
# Review escalated questions from the latest iteration
make review V=v1

# Or run the feedback loop with auto-review (agents resolve everything)
python scripts/run_feedback_loop.py --mode standalone --auto-review
```

## Iteration Flow

```
Iteration N:
  Agents run 7-phase pipeline
  → Most phases reach consensus automatically
  → Escalated questions presented to you
  → Your decisions feed into iteration N+1
  → Repeat until convergence (80%+ coverage)
```
