
import datasets
import pyarrow.parquet as pq
import os
import re
from urllib.parse import urlparse
import glob

# Path to the directory containing arrow files
data_dir = "data/benchmark_datasets/ontourl/XiaoZhang98___onto_url/default/0.0.0/f44025445b431afd31d10b2cb444683c3a9e9ce8"
arrow_files = glob.glob(os.path.join(data_dir, "*.arrow"))

if not arrow_files:
    print(f"No arrow files found in {data_dir}")
    exit(1)

domain_ontologies = {}
ontology_names_map = {} # IRI prefix -> Name

def extract_ontology_name(iri):
    parsed = urlparse(iri)
    netloc = parsed.netloc
    path = parsed.path
    
    name = "Unknown"
    
    if "purl.obolibrary.org/obo/" in iri:
        # http://purl.obolibrary.org/obo/ENVO_...
        match = re.search(r'obo/([A-Z]+)_', iri)
        if match:
            name = match.group(1)
        else:
            match = re.search(r'obo/([a-z]+)\.owl', iri)
            if match:
                name = match.group(1).upper()
            else:
                 # Some use other patterns
                 match = re.search(r'obo/([a-z]+)/', iri) # e.g. obo/ncbitaxon/
                 if match:
                     name = match.group(1).upper()
                 else:
                     name = path.split('/')[-1]

    elif "bioontology.org" in iri:
         # http://purl.bioontology.org/ontology/SNOMEDCT/
         parts = path.split('/')
         if 'ontology' in parts:
             idx = parts.index('ontology')
             if idx + 1 < len(parts):
                 name = parts[idx+1]
    
    elif "spec.edmcouncil.org" in iri:
        if "fibo" in path:
             name = "FIBO"
    
    elif "geonames" in iri:
        name = "GeoNames"
    
    elif "schema.org" in iri:
        name = "Schema.org"
        
    elif "dbpedia" in iri:
        name = "DBpedia"
        
    elif "foodon" in iri.lower():
         name = "FoodOn"
         
    elif "w3.org" in iri:
         name = "W3C"
         
    elif "linkedgeodata.org" in iri:
        name = "LinkedGeoData"
        
    elif "omg.org" in iri:
        name = "OMG"
         
    else:
        # Fallback: try to guess from the last part of the path or filename
        parts = path.split('/')
        if parts:
            last = parts[-1]
            if '.owl' in last:
                name = last.replace('.owl', '')
            elif '.rdf' in last:
                name = last.replace('.rdf', '')
            elif '#' in last:
                name = last.split('#')[0]
            elif '_' in last: # common pattern like OBI_0000..
                name = last.split('_')[0]
            else:
                name = last
                
    return name

print(f"Processing {len(arrow_files)} files...")

for file_path in arrow_files:
    try:
        ds = datasets.Dataset.from_file(file_path)
        # We can just iterate once or convert to pandas for unique values
        # Since datasets are loaded lazily, to_pandas might be memory intensive but for inspection it is fine.
        # But let's be safer and iterate if it is too big. 
        # Actually OntoURL is not huge (few GBs total but one file is small)
        
        # Check columns. Usually key is 'domain', 'context', 'question', 'answers', 'iri'
        # But 'iri' might be inside 'context' or somewhere. The previous script assumed a column 'iri'.
        # Let's check the column names first.
        cols = ds.column_names
        
        # The iri is usually in the 'context' (ontology snippet) or 'id'.
        # Wait, previous script used `row['iri']`. Let's assume it exists.
        
        unique_domains = set()
        if 'domain' in cols:
             unique_domains = set(ds.unique('domain'))
        
        for domain in unique_domains:
            if domain not in domain_ontologies:
                domain_ontologies[domain] = set()

        # We need to iterate rows to find IRIs related to the domain
        # Or just get unique (domain, iri) pairs
        
        # If 'iri' column exists
        if 'iri' in cols:
            df = ds.select_columns(['domain', 'iri']).to_pandas()
            for _, row in df.iterrows():
                domain = row['domain']
                iri = row['iri']
                if iri:
                    name = extract_ontology_name(iri)
                    domain_ontologies[domain].add(name)
        elif 'context' in cols:
             # Just checking if we can find ontology info in context if needed
             pass

    except Exception as e:
        print(f"Error processing {file_path}: {e}")

print("\n=== Result ===")
for domain, ontos in domain_ontologies.items():
    print(f"## {domain}")
    for o in sorted(ontos):
        print(f"- {o}")
