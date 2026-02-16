# OntoURL Benchmark Domains and Ontologies

This document lists the 40+ ontologies included in the OntoURL benchmark, grouped by domain. This information is critical for sourcing domain documents for RAG experiments.

## 1. Domains Overview

The benchmark covers 8 primary domains with ~58,000 questions total.

| Domain | Ontologies | Potential Document Sources |
|---|---|---|
| **Health & Medicine** | Alzheimer's, Addiction, Disease (DOID), Phenotype (HPO), Anatomy (FMA), Gene (GO), NCI Thesaurus, ICD | **PubMed abstracts**, Merck Manuals, WHO classification portals, CDC fact sheets |
| **Food & Agriculture** | Pizza, Wine, FoodOn, Crop Ontology, Plant Ontology | **Wikipedia** (for Pizza/Wine), USDA FoodData Central, FAO reports |
| **Business & Finance** | FIBO, Financial Instruments, BPMN, Public Contracts | **Investopedia**, SEC filings (EDGAR), Central Bank glossaries |
| **Arts & Media** | MusicOntology, Movie, Video Game, Propp (Folktales), CIDOC-CRM (Museums) | **IMDb**, MusicBrainz, Museum collection descriptions, TV Tropes (for narrative) |
| **Earth & Environment** | ENVO, SWEET (NASA), African Wildlife, GeoCore | **NASA EarthData**, National Geographic, IPCC reports |
| **Sciences** | Chebi (Chemistry), Cell Ontology, Software Ontology (SWO), Uberon | **ScienceDirect**, Textbooks, GitHub documentation |
| **Legal** | LKIF, European Legislation, Public Procurement | **EUR-Lex**, Cornell Law Institute (LII) |
| **Human Society** | Emotion, People, GSSO | **Psychology Today**, Sociology textbooks |

## 2. Detailed Ontology List

### Arts, Media & Entertainment
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **CIDOC CRM** | Cultural heritage, museum documentation | [CIDOC-CRM.org](http://www.cidoc-crm.org/), Museum collection portals |
| **Comic Book Ontology** | Comic books, characters, issues | Grand Comics Database, Comic Vine |
| **Movie Ontology** | Films, actors, production | IMDb, The Movie Database (TMDB) |
| **Music Ontology** | Music artists, albums, tracks | MusicBrainz, Discogs |
| **Propp Ontology** | Narrative structures, folktale morphology | Folklore texts, *Morphology of the Folktale* |
| **Video Game Ontology** | Games, genres, platforms | MobyGames, IGDB |
| **VideoWL** | Video content, segments | Video metadata schemas |

### Business & Finance
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **BPMN** | Business process modeling | OMG BPMN Spec, Corporate process manuals |
| **FIBO** | Financial industry | EDM Council, SEC Filings (EDGAR) |
| **Financial Instruments** | Financial products/derivatives | Product prospectuses, Investopedia |
| **Occupation Ontology** | Jobs, skills, sectors | ESCO Portal, O*NET OnLine |
| **Organization Ontology** | Corporate structures | Company registers, W3C Org Format |
| **Public Contracts** | Government contracting | Tenders Electronic Daily (TED) |

### Earth & Environment
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **African Wildlife** | Flora and fauna of Africa | Safari guides, AWF reports |
| **ENVO** | Environmental entities | Environment Ontology site, NOAA data |
| **Extensible Obs. (OBOE)** | Scientific observations | Ecological datasets (LTER) |
| **GeoCore** | Geological features | USGS surveys, Drill core logs |
| **SWEET** | Earth system science | NASA EarthData, JPL resources |

### Food & Agriculture
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **Crop Ontology** | Crop traits, breeding | Crop Ontology Curation Tool |
| **FoodOn** | Food products, safety | FoodOn.org, USDA FoodData Central |
| **Food Ontology** | Generic food concepts | Open Food Facts, Recipe DBs |
| **Pizza Ontology** | Pizza varieties | Domino's Menu, Wikipedia |
| **Plant Ontology** | Plant anatomy | Planteome, Botanical glossaries |
| **Wine Ontology** | Wine types, regions | Vivino, Wine Spectator |

### Health & Medicine
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **Addiction Ontology** | Substance abuse | NIDA, Addiction journals |
| **Alzheimer's Disease** | Neurodegeneration | Alzforum, Mayo Clinic |
| **FMA** | Human anatomy | Siibra Explorer, Gray's Anatomy |
| **General Med. Science** | Medical entities | OGMS GitHub, Clinical protocols |
| **Human Disease (DOID)** | Pathologies | Disease Ontology, CDC |
| **Human Phenotype (HPO)** | Phenotypic abnormalities | HPO Browser, OMIM |
| **ICD** | Disease classification | ICD-11 Browser (WHO) |
| **NCI Thesaurus** | Cancer-related terms | NCI EVS, PubMed Oncology |

### Human Society
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **Emotion Ontology** | Affective states | Psychology Today |
| **People Ontology** | Persons, relationships | Biographies, FOAF Spec |
| **GSSO** | Gender, sex, sexual orientation | Gender studies literature |

### Legal
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **ELI** | European Legislation Identifier | EUR-Lex |
| **LKIF Core** | Legal knowledge | Court judgments, Legal textbooks |
| **Public Procurement** | Procurement regulations | Public procurement acts |

### Sciences
| Ontology | Primary Topic | Potential Docs |
|---|---|---|
| **Cell Ontology** | Biological cell types | Cell Ontology Browser |
| **ChEBI** | Small chemical molecules | ChEBI EMBL-EBI, PubChem |
| **CHEMINF** | Chemical information | Cheminformatics journals |
| **Conference Ontology** | Academic conferences | OpenReview, Conference sites |
| **Gene Ontology (GO)** | Molecular function | GeneOntology.org, UniProt |
| **Software Ontology** | Software types, data | SourceForge, GitHub topics |
| **Uberon** | Cross-species anatomy | Uberon.org |
