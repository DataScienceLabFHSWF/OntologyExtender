
import datasets
import pyarrow.parquet as pq
import os
import re
from collections import Counter
from urllib.parse import urlparse

# Paths to process (relative to project root)
paths = [
    "data/benchmark_datasets/ontourl/XiaoZhang98___onto_url/default/0.0.0/f44025445b431afd31d10b2cb444683c3a9e9ce8/onto_url-1_1_class_definition_understanding.arrow",
    "data/benchmark_datasets/ontourl/XiaoZhang98___onto_url/default/0.0.0/f44025445b431afd31d10b2cb444683c3a9e9ce8/onto_url-1_5_instance_definition_understanding.arrow"
]

files_to_process = []
for p in paths:
    if os.path.exists(p):
        files_to_process.append(p)
    else:
        print(f"Skipping {p}: File not found")

if not files_to_process:
    exit(1)

domain_stats = {}
domain_ontologies = {}

for file_path in files_to_process:
    print(f"Loading {file_path}...")
    try:
        ds = datasets.Dataset.from_file(file_path)
        
        # We can iterate over batches or load all if memory permits
        # Since it's ~20MB, it's fine to load all
        data = ds.to_pandas()
        
        # Each row has domain, iri
        unique_domains = data['domain'].unique()
        print(f"Found domains: {unique_domains}")
        
        for domain in unique_domains:
            if domain not in domain_ontologies:
                domain_ontologies[domain] = set()
            
            subset = data[data['domain'] == domain]
            iris = subset['iri'].dropna().unique()
            
            for iri in iris:
                ontology_name = "Unknown"
                
                # Heuristics
                parsed = urlparse(iri)
                netloc = parsed.netloc
                path = parsed.path
                
                if "purl.obolibrary.org/obo/" in iri:
                    # http://purl.obolibrary.org/obo/ENVO_...
                    # Regex for OBO ontology ID
                    match = re.search(r'obo/([A-Z]+)_', iri)
                    if match:
                        ontology_name = match.group(1)
                    else:
                        match = re.search(r'obo/([a-z]+)\.owl', iri)
                        if match:
                            ontology_name = match.group(1).upper()
                        else:
                            # Try splitting by _ or #
                            parts = path.split('/')
                            last = parts[-1]
                            if '_' in last:
                                ontology_name = last.split('_')[0]
                            elif '#' in last:
                                ontology_name = last.split('#')[0]
                            else:
                                ontology_name = last
                elif "bioontology.org" in netloc:
                    # http://purl.bioontology.org/ontology/SNOMEDCT/
                    parts = path.split('/')
                    if 'ontology' in parts:
                        idx = parts.index('ontology')
                        if idx + 1 < len(parts):
                            ontology_name = parts[idx+1]
                elif "spec.edmcouncil.org" in netloc:
                    if "fibo" in path:
                         ontology_name = "FIBO"
                elif "geonames" in netloc:
                    ontology_name = "GeoNames"
                elif "schema.org" in netloc:
                    ontology_name = "Schema.org"
                elif "dbpedia" in netloc:
                    ontology_name = "DBpedia"
                elif "foodon" in iri.lower():
                     ontology_name = "FoodOn"
                elif "w3.org" in netloc:
                     ontology_name = "W3C"
                else:
                    ontology_name = netloc
                
                domain_ontologies[domain].add(ontology_name)

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

print("\n=== Result ===")
for domain, ontos in domain_ontologies.items():
    print(f"[{domain}]: {', '.join(sorted(ontos))}")

