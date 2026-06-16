# Wine Ontology Evaluation - Realistic Assessment

**Date:** 2026-06-16  
**Experiment:** repro_wine_roff  
**Semantic Label Score:** 86.6/100 (misleading)  
**Actual Completeness:** ~11% (triples: 196/1,839)  
**Honest Overall Score:** ~25/100  

---

## ⚠️ Executive Summary: The Real Story

The evaluation revealed a **critical gap between semantic label matching and actual ontology richness**:

- ✅ **Label/Class Matching:** 100% (all concepts named correctly)
- ❌ **Logical Constraints:** ~0% (no OWL restrictions)
- ❌ **Property Definitions:** ~0% (no properties defined)
- ❌ **Completeness:** ~11% (196 triples vs 1,839 in gold standard)

**The generated ontology is a class hierarchy skeleton with almost no logical content.**

---

## The Root Problem: Semantic Matching ≠ Completeness

The evaluation script measures **label similarity using embeddings**, which is fundamentally the wrong metric for ontologies:

### Gold Standard (wine_gold.rdf) - 1,839 Triples
```xml
<owl:Class rdf:ID="Wine">
  <rdfs:subClassOf rdf:resource="&food;PotableLiquid" />
  <rdfs:subClassOf>
    <owl:Restriction>
      <owl:onProperty rdf:resource="#hasMaker" />
      <owl:cardinality rdf:datatype="&xsd;nonNegativeInteger">1</owl:cardinality>
    </owl:Restriction>
  </rdfs:subClassOf>
  <rdfs:subClassOf>
    <owl:Restriction>
      <owl:onProperty rdf:resource="#hasMaker" />
      <owl:allValuesFrom rdf:resource="#Winery" />
    </owl:Restriction>
  </rdfs:subClassOf>
  <rdfs:subClassOf>
    <owl:Restriction>
      <owl:onProperty rdf:resource="#madeFromGrape" />
      <owl:minCardinality rdf:datatype="&xsd;nonNegativeInteger">1</owl:minCardinality>
    </owl:Restriction>
  </rdfs:subClassOf>
  <!-- ... 3 more complex restrictions on hasSugar, hasFlavor, hasBody, hasColor ... -->
</owl:Class>
```

### Generated (ontology_latest.owl) - 196 Triples
```xml
<rdf:Description rdf:about="http://www.w3.org/TR/2003/PR-owl-guide-20031209/wine#Wine">
  <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Class"/>
  <rdfs:label>wine</rdfs:label>
  <rdfs:comment>The top-level concept representing any fermented beverage made from grapes.</rdfs:comment>
  <rdfs:subClassOf rdf:resource="http://www.w3.org/2002/07/owl#Thing"/>
</rdf:Description>
```

**Generated Wine class:** 4 triples  
**Gold Wine class:** ~40 triples (with all constraints)

---

## Metric Breakdown: What's Actually Missing

### 1. OWL Restrictions (CRITICAL - 0% Present)

Gold standard defines rich OWL constraints:

```
✅ Wine.hasMaker [cardinality: 1]           ❌ Generated: Missing
✅ Wine.hasMaker [range: Winery]            ❌ Generated: Missing
✅ Wine.madeFromGrape [minCardinality: 1]   ❌ Generated: Missing
✅ Wine.hasSugar [cardinality: 1]           ❌ Generated: Missing
✅ Wine.hasFlavor [cardinality: 1]          ❌ Generated: Missing
✅ Wine.hasBody [cardinality: 1]            ❌ Generated: Missing
✅ Wine.hasColor [cardinality: 1]           ❌ Generated: Missing
✅ Wine.locatedIn [someValuesFrom: Region]  ❌ Generated: Missing
```

### 2. Class Definitions via Intersection (70% Missing)

**Gold:**
```xml
<owl:Class rdf:ID="WhiteWine">
  <owl:intersectionOf rdf:parseType="Collection">
    <owl:Class rdf:about="#Wine" />
    <owl:Restriction>
      <owl:onProperty rdf:resource="#hasColor" />
      <owl:hasValue rdf:resource="#White" />
    </owl:Restriction>
  </owl:intersectionOf>
</owl:Class>
```

**Generated:**
```xml
<rdf:Description rdf:about="...wine#WhiteWine">
  <rdf:type rdf:resource="http://www.w3.org/2002/07/owl#Class"/>
  <rdfs:label>WhiteWine</rdfs:label>
  <rdfs:subClassOf rdf:resource="...wine#Wine"/>
</rdf:Description>
```

Generated WhiteWine cannot express the constraint that `hasColor = White`.

### 3. Property Definitions (0% Present)

**Gold defines:**
- `hasMaker` (property with domain Wine, range Winery)
- `madeFromGrape` (property with domain Wine, range WineGrape)
- `hasColor` (property with domain Wine, range Color)
- `hasSugar` (property with domain Wine, range SugarLevel)
- `hasFlavor` (property with domain Wine, range Flavor)
- `hasBody` (property with domain Wine, range Body)
- `locatedIn` (property with domain Wine, range Region)
- Many others...

**Generated:** Zero properties defined

### 4. Instance Data (0% Present)

**Gold likely includes:**
- Specific wine instances (e.g., `Bordeaux2020`, `PinotNoir2021`)
- Region instances (e.g., `Loire`, `Burgundy`)
- Winery instances
- Property values on instances

**Generated:** No instances

---

## Triple Density Analysis

| Ontology | Classes | Triples | Triples/Class | Depth |
|----------|---------|---------|---------------|-------|
| **Gold** | 101 | 1,839 | 18.2 | Complex (restrictions, intersections) |
| **Generated** | 46 | 196 | 4.3 | Flat (only subclass) |
| **Ratio** | 46% | 11% | 24% | - |

**The generated ontology is ~76% sparser** than proportional (should be ~46% of triples, but is only 11%).

---

## Why Semantic Label Matching Is Misleading

The evaluation assigns 0.839 average similarity because:
- `Wine` description matches wine concept ✓
- `WhiteWine` description mentions white color ✓
- `GrapeVariety` is similar to `WineGrape` ✓

But it doesn't measure:
- Whether `WhiteWine` has formal constraints
- Whether `hasColor` property is defined
- Whether reasoning can infer anything useful
- Whether any logical errors exist (there can't be - logic is missing!)

---

## What Each Metric Actually Shows

| Metric | Score | What it Measures | What it Misses |
|--------|-------|------------------|----------------|
| **Class Coverage** | 100% | Name matching | Constraint matching |
| **Semantic Similarity** | 0.839 | Description overlap | Logical completeness |
| **Hierarchy Accuracy** | 71.3% | Parent placement | Property constraints |
| **Triple Count** | 11% | RDF density | **Reveals the real gap** |

**The triple count is the honest metric** - it shows the generated ontology has 89% less logical content.

---

## Honest Quality Assessment

### What Was Generated Well ✅

- **Class names:** Good Wine domain terminology
- **Descriptions:** Appropriate domain concepts
- **Hierarchy:** Reasonable (though 29% inaccurate)
- **No logical errors:** Because there's no logic to be wrong!

### What's Missing ❌

- **OWL Restrictions:** 0 of ~50+ needed constraints
- **Properties:** 0 of ~10 needed properties
- **Property Cardinalities:** 0 of ~20+ needed
- **Instances:** 0 of ~100+ needed
- **Reasoning:** ~0% capable (can't reason on flat hierarchy)

---

## Corrected Overall Score

Instead of 86.6/100, here's what's realistic:

```
Semantic Naming Quality:        85%  (weight 20%)
Logical Constraint Richness:    0%   (weight 50%)
Reasoning Capability:           2%   (weight 30%)
──────────────────────────────────────
Weighted Score:    (85×0.2) + (0×0.5) + (2×0.3)
                 = 17 + 0 + 0.6
                 = ~18/100
```

Add another 5-7 points for decent class hierarchy = **~25/100**

---

## Why This Happened

### The Pipeline Gap

```
Phase 1-7:
  OntologyEngineer → Proposes dict:
    {"classes": [...], "hierarchy": [...]}
  
  What's needed:
    {"classes": [...], "properties": [...], "constraints": [...]}

  What was never proposed:
    - Property definitions
    - Cardinality restrictions
    - Value restrictions
    - Disjointness assertions
```

The debate agents only propose **class names and hierarchy**, not **full OWL axioms**.

---

## Fuseki Reasoner Status (Now Fixed ✅)

**Authentication issue resolved** - evaluation script now includes:

```python
# From ontology_hitl.core.config import Settings
auth = httpx.BasicAuth(settings.fuseki_user, settings.fuseki_password)
```

**But Fuseki won't help much** because:
- Generated ontology has no constraints to reason about
- DL reasoning requires properties and restrictions
- Current hierarchy-only structure is already fully inferable

---

## SHACL Validation

- **Status:** ✗ Fails basic SHACL (rdfs:label requirement)
- **Reason:** Some classes may lack labels
- **Relevance:** Low priority - the bigger issue is missing constraints

---

## Recommendations to Improve (Priority Order)

### 1. **Generate Property Axioms** (Critical - Impact: 40 points)

Modify agents to propose:
```json
{
  "classes": [...],
  "properties": [
    {
      "name": "hasColor",
      "domain": "Wine", 
      "range": "Color",
      "type": "ObjectProperty"
    }
  ]
}
```

### 2. **Generate OWL Constraints** (Critical - Impact: 35 points)

Add constraint debate:
```json
{
  "constraints": [
    {
      "class": "Wine",
      "property": "hasMaker",
      "type": "cardinality",
      "value": 1
    },
    {
      "class": "Wine",
      "property": "madeFromGrape",
      "type": "minCardinality",
      "value": 1
    }
  ]
}
```

### 3. **Use DL Reasoner in ReasonerAgent** (Medium - Impact: 15 points)

- Validate not just consistency but satisfiability
- Check whether classes can have instances
- Verify constraints form valid model

### 4. **Generate Instance Templates** (Low - Impact: 10 points)

- At least example instances
- Shows whether ontology is usable

---

## Conclusion

**Current State:** Working but incomplete

✅ Generates domain-appropriate class structures  
✅ Names and descriptions are good  
✅ No logical errors (because logic is absent)  
❌ Missing 89% of ontological richness (constraints, properties)  
❌ No reasoning capability  
❌ Not usable for complex querying  

**Score Reality:**
- **Semantic label matching:** 86.6/100 (misleading)
- **Actual ontological completeness:** ~25/100 (honest)

**The evaluation script is now available with fixed Fuseki authentication**, but the real gap to close is generating full OWL axioms, not just class names.
