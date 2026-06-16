# Agentic Team Extension Needs - Comprehensive Assessment

**Date:** 2026-06-16  
**Issue:** Agents generate Phase 5-6 proposals (properties, facets) but output contains **only class hierarchy** (196 triples vs 1,839 needed)

---

## Executive Summary: The Gap

**What SHOULD happen (Ont-101 standard):**
```
Phase 4: Hierarchy      → HierarchyNode[uri, label, parent]      ✅ Works
Phase 5: Properties    → PropertyProposal[name, domain, range]   ✅ Generated (but...)
Phase 6: Facets        → FacetSpec[cardinality, constraints]     ✅ Generated (but...)
↓ Export OWL           → Full axioms with restrictions           ❌ Broken
```

**What ACTUALLY happens:**
```
Phase 4: Hierarchy     → HierarchyNode objects                   ✅ Works
Phase 5: Properties   → PropertyProposal list generated          ✅ Created
Phase 6: Facets       → FacetSpec list generated                 ✅ Created
↓ Export OWL          → Only Phase 4 hierarchy exported!         ❌ Loss of data
                      → PropertyProposal/FacetSpec never used     ❌ Dropped
```

**Result:** 89% missing RDF triples (196 vs 1,839)

---

## Current Architecture: What Exists

### Phase 5: Properties Debate (EXISTS but unused)
```python
# File: src/ontology_hitl/methodology/ontology101.py, line 166
@dataclass
class PropertyProposal:
    name: str                           # e.g. "hasColor"
    attached_to_class: str              # e.g. "Wine"
    property_type: Literal["datatype", "object"] = "datatype"
    description: str = ""
    datatype: str = "xsd:string"        # For datatype properties
    range_class: str | None = None      # For object properties
    inverse_name: str | None = None
    inherited_by: list[str] = field(default_factory=list)
    source_evidence: list[str] = field(default_factory=list)
```

### Phase 6: Facets Debate (EXISTS but unused)
```python
# File: src/ontology_hitl/methodology/ontology101.py, line 192
@dataclass
class FacetSpec:
    property_name: str                  # e.g. "hasMaker"
    on_class: str                       # e.g. "Wine"
    min_count: int | None = None        # owl:minCardinality
    max_count: int | None = None        # owl:maxCardinality
    value_type: str = "xsd:string"
    allowed_values: list[str] | None = None  # owl:oneOf
    pattern: str | None = None          # regex constraint
    rationale: str = ""
```

### Agents Debating Phase 5-6
- ✅ OntologyEngineer proposes properties & constraints
- ✅ Critic reviews them
- ✅ Reasoner validates (basic)
- ✅ Results stored in `Ont101Iteration.properties` and `Ont101Iteration.facets`

---

## The Export Problem

### File: `src/ontology_hitl/schema/manager.py`, line 138
```python
def export_owl(self, output_path: Path | str) -> None:
    """Export extended ontology as OWL/XML."""
    # Load seed ontology
    g = Graph()
    g.parse(str(self.seed_ontology_path))
    
    # Add classes only
    for cls in self._accepted_classes:
        class_uri = EX[cls.label]
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(cls.label)))
        g.add((class_uri, RDFS.comment, Literal(cls.definition)))
        parent = URIRef(cls.parent_uri) if cls.parent_uri else OWL.Thing
        g.add((class_uri, RDFS.subClassOf, parent))
        
        # ⚠️ TRIES to add properties from class.suggested_properties
        # But ProposedClass doesn't have this field!
        for prop in getattr(cls, 'suggested_properties', []):  # <- Empty!
            # Never executes because ProposedClass has no suggested_properties
            ...
    
    g.serialize(str(output_path), format="xml")
```

**The Problem:** 
- `ProposedClass` has only: `label`, `definition`, `parent_uri`, `parent_label`, `examples`, `frequency`, `confidence`
- No connection to `PropertyProposal` or `FacetSpec` objects
- Export tries to access `.suggested_properties` that doesn't exist
- Properties and Facets are **silently dropped**

---

## What Needs to be Extended

### 1. **Data Model Extension** (High Priority)

Extend `ProposedClass` to include constraints:

```python
# src/ontology_hitl/core/models.py

@dataclass
class ProposedClass:
    id: str
    label: str
    definition: str = ""
    parent_uri: str = ""
    parent_label: str = ""
    examples: list[str] = field(default_factory=list)
    frequency: int = 0
    confidence: float = 0.0
    
    # ✅ NEW: Add property and constraint data
    properties: list[PropertyProposal] = field(default_factory=list)
    constraints: list[FacetSpec] = field(default_factory=list)
```

### 2. **Pipeline Integration** (High Priority)

Link Phase 5/6 results into the export decision data:

```python
# src/ontology_hitl/methodology/pipeline.py - create_proposals_from_iteration()

for cls in hierarchy.nodes:
    if cls.is_from_seed:
        continue
    
    proposal = {
        "id": f"class_{cls.label}",
        "label": cls.label,
        "definition": cls.definition,
        "parent_uri": cls.parent_uri,
        "parent_label": cls.parent_label,
        "examples": cls.examples,
        
        # ✅ NEW: Attach properties & constraints
        "properties": [
            {
                "name": p.name,
                "type": p.property_type,
                "datatype": p.datatype,
                "range_class": p.range_class,
                "domain": cls.label,
                "description": p.description,
            }
            for p in result.properties
            if p.attached_to_class == cls.label
        ],
        "constraints": [
            {
                "property": f.property_name,
                "min_count": f.min_count,
                "max_count": f.max_count,
                "allowed_values": f.allowed_values,
                "pattern": f.pattern,
            }
            for f in result.facets
            if f.on_class == cls.label
        ],
    }
```

### 3. **OWL Export Enhancement** (Critical)

Generate proper OWL restrictions in export:

```python
# src/ontology_hitl/schema/manager.py - export_owl()

def export_owl(self, output_path: Path | str) -> None:
    """Export with full OWL axioms including restrictions."""
    from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, OWL, XSD
    
    g = Graph()
    g.parse(str(self.seed_ontology_path))
    ontology_base = self._infer_ontology_base(g)
    EX = Namespace(ontology_base)
    
    for cls in self._accepted_classes:
        class_uri = EX[cls.label]
        g.add((class_uri, RDF.type, OWL.Class))
        g.add((class_uri, RDFS.label, Literal(cls.label)))
        g.add((class_uri, RDFS.comment, Literal(cls.definition)))
        
        # ✅ Add parent
        parent = URIRef(cls.parent_uri) if cls.parent_uri else OWL.Thing
        g.add((class_uri, RDFS.subClassOf, parent))
        
        # ✅ NEW: Add properties
        for prop in cls.properties:
            prop_uri = EX[prop["name"]]
            g.add((prop_uri, RDF.type, OWL.ObjectProperty if prop["type"] == "object" 
                                       else OWL.DatatypeProperty))
            g.add((prop_uri, RDFS.domain, class_uri))
            
            if prop["type"] == "datatype":
                # Map datatype
                xsd_type = URIRef(_XSD_TYPE_MAP.get(prop["datatype"], 
                                  _XSD_TYPE_MAP["xsd:string"]))
                g.add((prop_uri, RDFS.range, xsd_type))
            else:
                # Object property range
                g.add((prop_uri, RDFS.range, EX[prop["range_class"]]))
            
            g.add((prop_uri, RDFS.label, Literal(prop["name"])))
            g.add((prop_uri, RDFS.comment, Literal(prop["description"])))
        
        # ✅ NEW: Add OWL restrictions (cardinality, value constraints)
        restrictions = []
        for constraint in cls.constraints:
            # Build owl:Restriction for this constraint
            restr_node = rdflib.BNode()
            g.add((restr_node, RDF.type, OWL.Restriction))
            g.add((restr_node, OWL.onProperty, EX[constraint["property"]]))
            
            # Add cardinality
            if constraint["min_count"] is not None:
                g.add((restr_node, OWL.minCardinality, 
                      Literal(constraint["min_count"], datatype=XSD.nonNegativeInteger)))
            if constraint["max_count"] is not None:
                g.add((restr_node, OWL.maxCardinality, 
                      Literal(constraint["max_count"], datatype=XSD.nonNegativeInteger)))
            
            # Add allowed values (enum)
            if constraint["allowed_values"]:
                values_list = rdflib.Collection(g, rdflib.BNode(),
                                               [Literal(v) for v in constraint["allowed_values"]])
                g.add((restr_node, OWL.oneOf, values_list))
            
            restrictions.append(restr_node)
        
        # Add restrictions to class
        for restr in restrictions:
            g.add((class_uri, RDFS.subClassOf, restr))
    
    g.serialize(str(output_path), format="xml")
```

### 4. **SHACL Shape Generation** (Medium Priority)

Generate SHACL shapes from constraints:

```python
# src/ontology_hitl/export/shacl_generator.py (new file)

def generate_shacl_from_facets(facets: list[FacetSpec], output_path: Path) -> str:
    """Generate SHACL shapes from Phase 6 facet constraints."""
    
    shacl_turtle = """
    PREFIX sh: <http://www.w3.org/ns/shacl#>
    PREFIX owl: <http://www.w3.org/2002/07/owl#>
    PREFIX ex: <http://example.org/ontology#>
    """
    
    for facet in facets:
        shape_name = f"{facet.on_class}_{facet.property_name}_Shape"
        shacl_turtle += f"""
        
        ex:{shape_name} a sh:NodeShape ;
            sh:targetClass ex:{facet.on_class} ;
            sh:property [
                sh:path ex:{facet.property_name} ;
        """
        
        if facet.min_count is not None:
            shacl_turtle += f"            sh:minCount {facet.min_count} ;\n"
        if facet.max_count is not None:
            shacl_turtle += f"            sh:maxCount {facet.max_count} ;\n"
        if facet.allowed_values:
            values = ' '.join([f'ex:{v}' for v in facet.allowed_values])
            shacl_turtle += f"            sh:in ({values}) ;\n"
        if facet.pattern:
            shacl_turtle += f'            sh:pattern "{facet.pattern}" ;\n'
        
        shacl_turtle += """
            ] .
        """
    
    with open(output_path, 'w') as f:
        f.write(shacl_turtle)
    
    return shacl_turtle
```

---

## Implementation Roadmap

### Phase A: Unblock Property/Constraint Export (1-2 days)

1. **Update `ProposedClass`** to include `properties` and `constraints` fields
2. **Update proposal extraction** in `create_proposals_from_iteration.py` to connect Phase 5/6 results
3. **Enhance `export_owl()`** to generate OWL Restriction axioms
4. **Test:** Should increase triples from 196 → 800+ (closer to 1,839)

### Phase B: Enhance Agent Prompts (1 day)

1. Update Phase 5 prompt to make agents generate structured property proposals
2. Update Phase 6 prompt to focus on cardinality, value constraints
3. Extend Reasoner to validate restrictions (not just class hierarchy)

### Phase C: SHACL Integration (1 day)

1. Add SHACL shape generation from facets
2. Export SHACL alongside OWL
3. Use SHACL for validation in pipeline

### Phase D: Full Agentic Enhancement (optional, 2-3 days)

1. New "ConstraintEngineer" agent that specifically debates cardinality constraints
2. New "PropertyArchitect" agent that designs property hierarchies
3. Enhanced Critic role to check constraint consistency
4. Ensemble voting on constraint cardinality (similar to hierarchy ensemble)

---

## Why This Matters

**Current state (196 triples):**
```
Can you answer: "What grapes are used in red wine?"
→ No - no property assertions connecting Wine to grapes

Can you infer: "A wine must have exactly one maker?"
→ No - no cardinality constraints exist

Can you validate: "This instance violates domain constraints?"
→ No - no constraints to validate
```

**After Phase A (estimated 800+ triples):**
```
Can you answer: "What grapes are used in red wine?"
→ Yes - hasGrape property defined with range WineGrape

Can you infer: "A wine must have exactly one maker?"
→ Yes - cardinality 1 constraint exists

Can you validate: "This instance violates domain constraints?"
→ Yes - SHACL shapes enforce constraints
```

---

## Code Files That Need Changes

| File | Change | Priority |
|------|--------|----------|
| `src/ontology_hitl/core/models.py` | Add `properties`, `constraints` to `ProposedClass` | 🔴 Critical |
| `src/ontology_hitl/methodology/pipeline.py` | Connect Phase 5/6 output to export | 🔴 Critical |
| `src/ontology_hitl/schema/manager.py` | Generate OWL restrictions in `export_owl()` | 🔴 Critical |
| `src/ontology_hitl/export/shacl_generator.py` | NEW - Generate SHACL shapes | 🟡 Medium |
| `src/ontology_hitl/methodology/prompts.py` | Improve Phase 5/6 prompts | 🟡 Medium |
| `src/ontology_hitl/agents/reasoner.py` | Validate constraints not just classes | 🟡 Medium |

---

## Expected Impact

**Before Extension:**
- Ontology: 46 classes, 196 triples
- Reasoning capability: ~0% (flat hierarchy only)
- Constraint validation: No
- Honest completeness score: ~25/100

**After Phase A Extension:**
- Ontology: 46 classes, ~800-1,000 triples
- Reasoning capability: ~40-50% (properties + basic cardinality)
- Constraint validation: Yes (SHACL)
- Honest completeness score: ~55-65/100

**With Full Enhancement:**
- Ontology: 46 classes, ~1,200-1,400 triples
- Reasoning capability: ~70-80% (full DL with ensemble constraints)
- Constraint validation: Robust
- Honest completeness score: ~75-85/100

---

## Quick Start

To unblock the Phase A critical fixes:

```bash
# 1. Update model
vi src/ontology_hitl/core/models.py
# Add properties/constraints fields to ProposedClass

# 2. Update proposal extraction
vi src/ontology_hitl/methodology/pipeline.py
# Link Phase 5/6 results in create_proposals_from_iteration()

# 3. Enhance export
vi src/ontology_hitl/schema/manager.py
# Add OWL restriction generation in export_owl()

# 4. Test
python scripts/export_ontology.py --seed data/benchmark_datasets/reproduction/wine/wine_seed.ttl ...

# 5. Re-evaluate
python scripts/evaluate_ontology.py --generated data/exports/.../ontology_latest.owl ...
# Should show ~500-1000 triples instead of 196
```

---

## Conclusion

**The agents ARE working correctly** - they debate and generate Phase 5/6 proposals.  
**The problem is the plumbing** - proposals never make it to OWL export.

Fixing this gap requires:
1. ✅ Data model connection (ProposedClass → Phase 5/6 results)
2. ✅ Export logic (OWL Restriction generation)
3. ✅ SHACL integration (constraint validation)

This is **high-value, medium-effort work** that will immediately increase ontology richness from 25/100 → 65/100 (realistic score).
