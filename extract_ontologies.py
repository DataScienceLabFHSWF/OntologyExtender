
import datasets
import pyarrow.parquet as pq
import os
import re

def extract_ontologies_from_arrow(file_path):
    table = datasets.arrow_dataset.Dataset.from_file(file_path)
    domains_ontologies = {}
    
    unique_domains = set(table['domain'])
    print(f"Found {len(unique_domains)} domains: {unique_domains}")

    for row in table:
        domain = row['domain']
        iri = row['iri']
        if domain not in domains_ontologies:
            domains_ontologies[domain] = set()
            
        # Try to extract ontology name from IRI
        ontology_name = "Unknown"
        if "snomed" in iri.lower():
            ontology_name = "SNOMED CT"
        elif "fibo" in iri.lower():
             ontology_name = "FIBO"
        elif "geonames" in iri.lower():
             ontology_name = "GeoNames"
        elif "purl.obolibrary.org/obo/" in iri:
            # Extract OBO ontology ID like ENVO, GO, DOID, etc.
            match = re.search(r'obo/([A-Z]+)_', iri)
            if match:
                ontology_name = match.group(1)
            else:
                 # Some use other patterns
                 match = re.search(r'obo/([a-z]+)\.owl', iri)
                 if match:
                     ontology_name = match.group(1).upper()
                 else:
                     ontology_name = iri.split('/')[-1].split('_')[0] # Heuristic
        elif "bioontology.org" in iri:
             parts = iri.split('/')
             if "ontology" in parts:
                 idx = parts.index("ontology")
                 if idx + 1 < len(parts):
                     ontology_name = parts[idx+1]
        elif "dbpedia" in iri:
             ontology_name = "DBpedia"
        elif "schema.org" in iri:
             ontology_name = "Schema.org"
        else:
             # Just use the domain prefix
             try:
                 from urllib.parse import urlparse
                 parsed = urlparse(iri)
                 ontology_name = parsed.netloc
             except:
                 ontology_name = iri[:30]

        domains_ontologies[domain].add(ontology_name)

    return domains_ontologies

# Paths to process
paths = [
    "data/benchmark_datasets/ontourl/XiaoZhang98___onto_url/default/0.0.0/f44025445b431afd31d10b2cb444683c3a9e9ce8/onto_url-1_1_class_definition_understanding.arrow",
    "data/benchmark_datasets/ontourl/XiaoZhang98___onto_url/default/0.0.0/f44025445b431afd31d10b2cb444683c3a9e9ce8/onto_url-1_5_instance_definition_understanding.arrow"
]

all_ontologies = {}

for p in paths:
    if os.path.exists(p):
        print(f"Processing {p}...")
        res = extract_ontologies_from_arrow(p)
        for d, ontos in res.items():
            if d not in all_ontologies:
                all_ontologies[d] = set()
            all_ontologies[d].update(ontos)

print("\n--- Summary ---")
for d, ontos in all_ontologies.items():
    print(f"Domain: {d}")
    for o in sorted(ontos):
        print(f"  - {o}")
