# Expert Review Guide

## Overview

As a domain expert, you review proposed ontology classes generated from
document analysis. Your decisions determine which concepts become part of
the extended ontology.

## Review Process

For each proposed class you will see:

1. **Label** — the class name
2. **Definition** — auto-generated description
3. **Parent class** — where it fits in the ontology hierarchy
4. **Examples** — entity instances found in documents
5. **Frequency** — how often this concept appears
6. **Confidence** — algorithmic confidence score
7. **Properties** — suggested data properties
8. **Relations** — suggested object properties to other classes

## Decision Options

| Decision | When to use |
|----------|-------------|
| **Accept** | The class is well-defined and belongs in the ontology |
| **Reject** | The concept is wrong, too specific, or already covered |
| **Revise** | The idea is good but needs changes (definition, parent, etc.) |
| **Skip** | You want to come back to this one later |

## Tips

- If frequency is low (< 5), consider whether the class is important enough
- Check that the parent class makes sense in the hierarchy
- Look at examples — do they clearly belong to this class?
- If a class seems too specific, suggest merging with a broader class
- Always provide a rationale for rejections and revisions
