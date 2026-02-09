# Iteration Workflow

End-to-end workflow for one ontology extension iteration cycle.

## Prerequisites

- KnowledgeGraphBuilder has been run at least once (extraction checkpoint exists)
- Fuseki running with seed ontology loaded
- Ollama running with qwen3:8b model

## Full Iteration Cycle

```
Step 1: Run KGB pipeline (in KnowledgeGraphBuilder repo)
  → output/extraction_checkpoint.json

Step 2: Gap Analysis
  $ make gap V=v1 CHECKPOINT=<path-to-checkpoint>
  → data/iterations/v1/gap_report.json

Step 3: Generate Proposals
  $ make proposals V=v1
  → data/iterations/v1/proposals.json

Step 4: Expert Review
  $ make review V=v1
  → data/iterations/v1/decisions.json

Step 5: Export Extended Ontology
  $ make export V=v1
  → data/exports/ontology_v1.owl + data/exports/cq_v1.json

Step 6: Re-run KGB with extended ontology (in KnowledgeGraphBuilder repo)

Step 7: Evaluate Improvement
  $ make evaluate V=v1
  → data/iterations/v1/evaluation_report.json

Step 8: Decide → Iterate (v2) or Ship
```

## Iteration Schedule

| Iteration | Focus | Expected Classes | Target Coverage |
|-----------|-------|-----------------|-----------------|
| v1 | Core domain concepts | 8-12 | 55-65% |
| v2 | Process concepts | 6-10 | 70-80% |
| v3 | Fine-grained types | 5-8 | 80-85% |
| v4 | Edge cases + refinement | 3-5 | 85%+ |
