#!/usr/bin/env python3
"""Multiple LLM-Only Ontology Extension Baselines.

This script implements several baseline approaches for ontology extension:
1. Naive: Just ask LLM to extend everything at once
2. Modular: Break down by competency question themes
3. Iterative: Extend one theme at a time
4. Adaptive: Let LLM decide how many classes to add

Usage:
    python scripts/llm_only_baseline.py \\
        --model gemma4:e2b \\
        --strategy naive \\
        --output data/exports/baseline_naive \\
        --experiment-name baseline_naive

Strategies:
- naive: Single comprehensive prompt (original approach)
- modular: Group CQs by theme, single focused prompt
- iterative: Extend one theme at a time, combine results
- adaptive: Let LLM decide class count based on needs
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Literal

import httpx
import structlog
import wandb
from pydantic import BaseModel, Field
from rdflib import Graph, Namespace, RDF, RDFS, OWL, URIRef, Literal
from rdflib.namespace import XSD

from ontology_hitl.core.config import Settings

# Load .env file explicitly
from dotenv import load_dotenv
load_dotenv()

logger = structlog.get_logger(__name__)

# Ontology namespaces (same as used in the main system)
ONTOLOGY_NS = Namespace("http://www.semanticweb.org/ontology#")
PLAN_NS = Namespace("http://www.semanticweb.org/plan-ontology#")


class OntologyClass(BaseModel):
    """A new ontology class to add."""
    name: str = Field(description="The name of the new class")
    description: str = Field(description="What this class represents")
    parent_class: Optional[str] = Field(None, description="Existing class to inherit from, or null")
    properties: List[str] = Field(default_factory=list, description="Properties this class should have")


class OntologyProperty(BaseModel):
    """A new ontology property to add."""
    name: str = Field(description="The name of the new property")
    type: str = Field(description="Type of property: 'object' or 'datatype'")
    domain: str = Field(description="Class this property belongs to")
    range: str = Field(description="Target class or datatype (e.g., xsd:string, xsd:date)")
    description: str = Field(description="What this property represents")


class OntologyExtension(BaseModel):
    """Complete ontology extension response."""
    new_classes: List[OntologyClass] = Field(description="New classes to add to the ontology")
    new_properties: List[OntologyProperty] = Field(description="New properties to add to the ontology")


from abc import ABC, abstractmethod


class BaselineStrategy(ABC):
    """Abstract base for different baseline strategies.

    Subclasses *must* implement ``extend_ontology``; using ABC enforces this
    at import time and keeps the intent explicit. The original implementation
    raised a bare ``NotImplementedError`` which served as a stub; removing the
    runtime error lets type checkers and readers know the class is abstract.
    """

    def __init__(self, baseline: 'LLMOnlyBaseline'):
        self.baseline = baseline

    @abstractmethod
    def extend_ontology(self) -> Graph:
        """Implement the specific extension strategy.

        Returns
        -------
        Graph
            RDF graph representing the extensions produced by this strategy.
        """
        ...


class NaiveStrategy(BaselineStrategy):
    """Original naive approach: single comprehensive prompt."""
    
    def extend_ontology(self) -> Graph:
        prompt = self.baseline.generate_naive_prompt()
        parsed_data = self.baseline.call_llm_with_retry(prompt)
        return self.baseline.generate_owl_extensions(parsed_data)


class ModularStrategy(BaselineStrategy):
    """Modular approach: focused prompt with CQ grouping."""
    
    def extend_ontology(self) -> Graph:
        prompt = self.baseline.generate_modular_prompt()
        parsed_data = self.baseline.call_llm_with_retry(prompt)
        return self.baseline.generate_owl_extensions(parsed_data)


class IterativeStrategy(BaselineStrategy):
    """Iterative approach: extend one theme at a time."""
    
    def extend_ontology(self) -> Graph:
        combined_graph = Graph()
        prompts = self.baseline.generate_iterative_prompts()
        
        for i, prompt in enumerate(prompts):
            print(f"\n🔄 Iteration {i+1}/{len(prompts)}: Processing theme...")
            try:
                parsed_data = self.baseline.call_llm_with_retry(prompt)
                theme_graph = self.baseline.generate_owl_extensions(parsed_data)
                
                # Merge into combined graph
                for triple in theme_graph:
                    combined_graph.add(triple)
                    
                print(f"✅ Added {len(theme_graph)} triples from iteration {i+1}")
                
            except Exception as e:
                print(f"❌ Failed iteration {i+1}: {e}")
                continue
        
        return combined_graph


class AdaptiveStrategy(BaselineStrategy):
    """Adaptive approach: let LLM decide class count."""
    
    def extend_ontology(self) -> Graph:
        prompt = self.baseline.generate_adaptive_prompt()
        parsed_data = self.baseline.call_llm_with_retry(prompt)
        return self.baseline.generate_owl_extensions(parsed_data)


class LLMOnlyBaseline:
    """Multi-strategy LLM-only ontology extension baseline."""

    def __init__(
        self,
        seed_ontology_path: Path,
        cq_path: Path,
        strategy: Literal["naive", "modular", "iterative", "adaptive"] = "naive",
        ollama_url: str = "http://localhost:18135",
        model: str = "gemma4:e2b",
        verbose: bool = False,
    ):
        self.seed_path = seed_ontology_path
        self.cq_path = cq_path
        self.strategy_name = strategy
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self.verbose = verbose
        
        # Get timeout from settings (dynamic based on model size)
        settings = Settings()
        # Override timeout based on actual model being used
        model_lower = model.lower()
        print(f"DEBUG: model_lower = {model_lower}")
        if "qwen" in model_lower or "79b" in model_lower or "72b" in model_lower or "70b" in model_lower:
            self.timeout = 2400.0  # 40 minutes for large models
            print("DEBUG: Set timeout to 2400 for large model")
        elif "3b" in model_lower or "1.5b" in model_lower:
            self.timeout = 600.0   # 10 minutes for small models
            print("DEBUG: Set timeout to 600 for small model")
        else:
            self.timeout = 900.0   # 15 minutes for medium models
            print("DEBUG: Set timeout to 900 for medium model")

        # Load seed ontology
        self.seed_graph = Graph()
        self.seed_graph.parse(str(seed_ontology_path), format="xml")

        # Load competency questions
        with open(cq_path) as f:
            self.cqs = json.load(f)

        # Set up thinking token cache
        self.cache_dir = Path("data/cache/llm_responses")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Initialize strategy
        self.strategy = self._create_strategy()

        logger.info("llm_baseline_initialized",
                   seed_classes=len(list(self.seed_graph.subjects(RDF.type, OWL.Class))),
                   cqs=len(self.cqs),
                   model=model,
                   strategy=strategy,
                   timeout=self.timeout)

    def _create_strategy(self) -> BaselineStrategy:
        """Create the appropriate strategy instance."""
        if self.strategy_name == "naive":
            return NaiveStrategy(self)
        elif self.strategy_name == "modular":
            return ModularStrategy(self)
        elif self.strategy_name == "iterative":
            return IterativeStrategy(self)
        elif self.strategy_name == "adaptive":
            return AdaptiveStrategy(self)
        else:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")

    def _group_competency_questions(self) -> Dict[str, List[str]]:
        """Group competency questions by theme (literature approach: modular decomposition)."""
        groups = {
            "Planning & Scheduling": [],
            "Resource Management": [],
            "Safety & Risk": [],
            "Equipment & Facilities": [],
            "Regulatory & Compliance": [],
            "Waste Management": [],
            "Monitoring & Assessment": [],
            "Other": []
        }
        
        # Simple keyword-based grouping
        for cq_dict in self.cqs:
            cq_text = cq_dict["question"].lower()  # Extract question text from dict
            if any(word in cq_text for word in ["plan", "schedule", "sequence", "timeline"]):
                groups["Planning & Scheduling"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["resource", "personnel", "budget", "cost"]):
                groups["Resource Management"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["safety", "risk", "hazard", "protection"]):
                groups["Safety & Risk"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["equipment", "facility", "site", "building"]):
                groups["Equipment & Facilities"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["regulatory", "compliance", "license", "permit"]):
                groups["Regulatory & Compliance"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["waste", "disposal", "contamination"]):
                groups["Waste Management"].append(cq_dict["question"])
            elif any(word in cq_text for word in ["monitor", "assess", "measure", "evaluate"]):
                groups["Monitoring & Assessment"].append(cq_dict["question"])
            else:
                groups["Other"].append(cq_dict["question"])
        
        # Remove empty groups
        return {k: v for k, v in groups.items() if v}

    def generate_naive_prompt(self) -> str:
        """Generate the original naive prompt (comprehensive but overwhelming)."""
        existing_classes = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_classes.add(local_name)

        existing_properties = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)
        for s in self.seed_graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)

        cq_text = "\n".join(f"- {cq['question']}" for cq in self.cqs)

        prompt = f"""You are an ontology engineer. I need you to extend an existing ontology for AI planning domains.

EXISTING ONTOLOGY:
- Classes: {", ".join(sorted(existing_classes))}
- Properties: {", ".join(sorted(existing_properties))}

COMPETENCY QUESTIONS TO ANSWER:
{cq_text}

TASK: Extend the ontology by adding new classes and properties that would help answer these competency questions. Focus on the nuclear decommissioning domain.

Add as many classes and properties as needed - let the competency questions guide you.

OUTPUT FORMAT: Provide your answer in this exact JSON format:
{{
  "new_classes": [
    {{
      "name": "ClassName",
      "description": "What this class represents",
      "parent_class": "ExistingClassName or null",
      "properties": ["property1", "property2"]
    }}
  ],
  "new_properties": [
    {{
      "name": "propertyName",
      "type": "object|datatype",
      "domain": "ClassName",
      "range": "ClassName or xsd:string or xsd:date etc",
      "description": "What this property represents"
    }}
  ]
}}

Be comprehensive and add everything that would be useful.

IMPORTANT: Your response must be valid JSON only. Do not include any text before or after the JSON. The JSON should match this exact schema:
- new_classes: array of objects with name, description, parent_class, properties
- new_properties: array of objects with name, type, domain, range, description

Example valid response:
{{
  "new_classes": [
    {{
      "name": "NuclearFacility",
      "description": "A facility for nuclear operations",
      "parent_class": "ProblemObject",
      "properties": ["location", "capacity"]
    }}
  ],
  "new_properties": [
    {{
      "name": "hasLocation",
      "type": "datatype",
      "domain": "NuclearFacility",
      "range": "xsd:string",
      "description": "Location of the facility"
    }}
  ]
}}"""

        return prompt

    def generate_modular_prompt(self) -> str:
        """Generate the improved modular prompt with CQ grouping."""
        # Extract existing classes and properties
        existing_classes = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                # Get local name
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_classes.add(local_name)

        existing_properties = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)
        for s in self.seed_graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)

        # Group competency questions by theme
        cq_groups = self._group_competency_questions()
        
        # Create focused prompt
        prompt = f"""You are an expert ontology engineer specializing in nuclear decommissioning. Your task is to extend an existing ontology to better support competency questions.

EXISTING ONTOLOGY OVERVIEW:
- Core Classes: {", ".join(sorted(list(existing_classes)[:10]))}
- Key Properties: {", ".join(sorted(list(existing_properties)[:10]))}
- Total Classes: {len(existing_classes)}, Total Properties: {len(existing_properties)}

COMPETENCY QUESTIONS GROUPED BY THEME:
"""
        
        for theme, questions in cq_groups.items():
            prompt += f"\n{theme.upper()}:\n"
            for cq in questions[:3]:  # Limit questions per group
                prompt += f"- {cq}\n"

        prompt += f"""

APPROACH (Step-by-step reasoning):
1. ANALYZE: Identify missing concepts from the competency questions
2. DESIGN: Create focused classes that fill these gaps
3. CONNECT: Add properties to link new classes to existing ones
4. VALIDATE: Ensure extensions directly help answer the questions

Add as many classes and properties as needed for comprehensive coverage.

OUTPUT FORMAT: Provide your answer in this exact JSON format:
{{
  "reasoning": "Brief explanation of your approach",
  "new_classes": [
    {{
      "name": "ClassName",
      "description": "What this class represents",
      "parent_class": "ExistingClassName",
      "domain_focus": "which competency question theme this supports"
    }}
  ],
  "new_properties": [
    {{
      "name": "propertyName",
      "type": "object|datatype",
      "domain": "ClassName",
      "range": "ClassName or xsd:string",
      "description": "What this property represents"
    }}
  ]
}}

Be precise and comprehensive. Cover all important concepts."""

        return prompt

    def generate_iterative_prompts(self) -> List[str]:
        """Generate multiple focused prompts for iterative extension."""
        cq_groups = self._group_competency_questions()
        
        prompts = []
        for theme, questions in cq_groups.items():
            if not questions:
                continue
                
            # Create theme-specific prompt
            prompt = f"""Focus EXTENSIVELY on extending the ontology for: {theme}

Competency Questions:
{chr(10).join(f"- {cq}" for cq in questions)}

EXISTING CLASSES: {", ".join(sorted([str(s).split("#")[-1] for s in self.seed_graph.subjects(RDF.type, OWL.Class) if isinstance(s, URIRef)])[:15])}

Add as many classes and properties as needed for this specific theme. Be thorough and comprehensive.

OUTPUT FORMAT: Same JSON format as before.
"""
            prompts.append(prompt)
        
        return prompts

    def generate_adaptive_prompt(self) -> str:
        """Generate adaptive prompt that lets LLM decide class count."""
        existing_classes = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_classes.add(local_name)

        cq_text = "\n".join(f"- {cq['question']}" for cq in self.cqs)

        prompt = f"""You are an ontology engineer. Analyze these competency questions and decide how many classes and properties are needed to adequately support them.

EXISTING ONTOLOGY CLASSES: {", ".join(sorted(existing_classes))}

COMPETENCY QUESTIONS:
{cq_text}

INSTRUCTIONS:
1. Analyze the competency questions carefully
2. Determine how many new classes are truly needed (don't add unnecessary ones)
3. Decide on the appropriate number of properties
4. Focus on quality over quantity

Your response should include:
- "analysis": Your assessment of what's missing
- "estimated_classes_needed": How many classes you think are needed
- "estimated_properties_needed": How many properties you think are needed
- Then the usual "new_classes" and "new_properties" arrays

Be thoughtful and economical in your extensions."""

        return prompt

    def call_llm(self, prompt: str, verbose: bool = False) -> str:
        """Call Ollama LLM with the extension prompt (with thinking token caching)."""
        import time
        
        # Create cache key from prompt
        prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:16]
        cache_file = self.cache_dir / f"{self.model.replace(':', '_')}_{prompt_hash}.json"
        
        # Check cache first
        if cache_file.exists():
            print(f"   💾 Cache hit! Loading from {cache_file}")
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                    return cached_data['response']
            except Exception as e:
                print(f"   ⚠️  Cache read failed: {e}, proceeding with fresh call")
        
        url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,  # Enable streaming to see progress
            "options": {
                "temperature": float(getattr(self, "temperature", 0.5)),
                "num_predict": 2048,
            }
        }

        logger.info("calling_llm", model=self.model, prompt_length=len(prompt))
        if verbose:
            print(f"\n🤖 {self.model} is thinking...")
            print("=" * 60)
        else:
            print(f"\n🚀 Preparing to call {self.model}...")
            print(f"   📝 Prompt length: {len(prompt)} characters")
            print(f"   ⏱️  Timeout: {self.timeout}s")
            print(f"   🌐 API URL: {url}")
            print(f"   🔄 Starting LLM call (cache miss)...")

        if not verbose:
            print(f"\n🤖 Starting LLM generation...")
        start_time = time.time()
        
        try:
            with httpx.stream("POST", url, json=payload, timeout=self.timeout) as resp:
                print(f"   📡 HTTP status: {resp.status_code}")
                if resp.status_code != 200:
                    error_text = resp.text
                    print(f"   ❌ HTTP error: {error_text}")
                    raise Exception(f"HTTP {resp.status_code}: {error_text}")
                    
                resp.raise_for_status()
                full_response = ""
                tokens_received = 0
                last_update = start_time
                
                for line in resp.iter_lines():
                    if line:
                        try:
                            # Handle both bytes and str (httpx version differences)
                            if isinstance(line, bytes):
                                line = line.decode('utf-8')
                            data = json.loads(line)
                            
                            # Handle both 'response' (llama-style) and 'thinking' (qwen-style) streaming
                            chunk = ""
                            if 'response' in data and data['response']:
                                chunk = data['response']
                            elif 'thinking' in data and data['thinking']:
                                chunk = data['thinking']
                            
                            if chunk:
                                full_response += chunk
                                tokens_received += 1
                                
                                # Verbose output: stream tokens continuously with visual indicators
                                if verbose:
                                    if chunk == '\n':
                                        print('↵', end='', flush=True)
                                    elif chunk == '\t':
                                        print('→', end='', flush=True)
                                    elif chunk == ' ':
                                        print('·', end='', flush=True)  # Show spaces as dots
                                    else:
                                        print(chunk, end='', flush=True)
                                
                                # Minimal progress indicator (only for non-verbose mode)
                                current_time = time.time()
                                if not verbose and (tokens_received % 10 == 0 or current_time - last_update > 2):
                                    elapsed = current_time - start_time
                                    print(f"\r📝 Generating... {tokens_received} tokens in {elapsed:.1f}s", end='', flush=True)
                                    last_update = current_time
                            
                            # Check if generation is done
                            if data.get('done', False):
                                total_time = time.time() - start_time
                                if verbose:
                                    print(f"\n{'=' * 60}")
                                    print(f"✅ Generation complete! | {tokens_received} tokens | {total_time:.1f}s | {tokens_received/total_time:.1f} t/s")
                                else:
                                    print(f"\n✅ LLM generation completed in {total_time:.1f}s")
                                    print(f"   📊 Total tokens: {data.get('eval_count', tokens_received)}")
                                    print(f"   🚀 Tokens/second: {tokens_received/total_time:.1f}")
                                break
                                
                        except json.JSONDecodeError as e:
                            print(f"\n⚠️  JSON decode error: {e}")
                            print(f"   Raw line: {line[:200]}...")
                            continue
                
                if not full_response:
                    raise Exception("No response received from LLM")
                
                # Cache the response
                cache_data = {
                    'model': self.model,
                    'prompt_hash': prompt_hash,
                    'timestamp': time.time(),
                    'response': full_response,
                    'tokens': tokens_received
                }
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(cache_data, f, indent=2)
                    print(f"   💾 Cached response to {cache_file}")
                except Exception as e:
                    print(f"   ⚠️  Cache write failed: {e}")
                    
                return full_response
                
        except Exception as e:
            print(f"\n❌ LLM call failed: {e}")
            logger.error("llm_call_failed", error=str(e))
            raise
        """Generate the comprehensive prompt for LLM-only extension."""

        # Extract existing classes and properties
        existing_classes = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.Class):
            if isinstance(s, URIRef):
                # Get local name
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_classes.add(local_name)

        existing_properties = set()
        for s in self.seed_graph.subjects(RDF.type, OWL.ObjectProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)
        for s in self.seed_graph.subjects(RDF.type, OWL.DatatypeProperty):
            if isinstance(s, URIRef):
                local_name = str(s).split("#")[-1] if "#" in str(s) else str(s).split("/")[-1]
                existing_properties.add(local_name)

        # Group competency questions by theme (literature approach: modular extension)
        cq_groups = self._group_competency_questions()
        
        # Create a more focused, step-by-step prompt (literature approach: chain-of-thought)
        prompt = f"""You are an expert ontology engineer specializing in nuclear decommissioning. Your task is to extend an existing ontology to better support competency questions.

EXISTING ONTOLOGY OVERVIEW:
- Core Classes: {", ".join(sorted(list(existing_classes)[:10]))}  # Limit to avoid overwhelming
- Key Properties: {", ".join(sorted(list(existing_properties)[:10]))}
- Total Classes: {len(existing_classes)}, Total Properties: {len(existing_properties)}

COMPETENCY QUESTIONS GROUPED BY THEME:
"""
        
        for theme, questions in cq_groups.items():
            prompt += f"\n{theme.upper()}:\n"
            for cq in questions[:3]:  # Limit questions per group
                prompt += f"- {cq}\n"

        prompt += f"""

APPROACH (Step-by-step reasoning):
1. ANALYZE: Identify missing concepts from the competency questions
2. DESIGN: Create 3-8 focused classes that fill these gaps
3. CONNECT: Add properties to link new classes to existing ones
4. VALIDATE: Ensure extensions directly help answer the questions

REQUIREMENTS:
- Focus on nuclear decommissioning domain concepts
- Create logical class hierarchies
- Add only essential properties
- Keep extensions minimal but complete

OUTPUT FORMAT: Provide your answer in this exact JSON format:
{{
  "reasoning": "Brief explanation of your approach",
  "new_classes": [
    {{
      "name": "ClassName",
      "description": "What this class represents",
      "parent_class": "ExistingClassName",
      "domain_focus": "which competency question theme this supports"
    }}
  ],
  "new_properties": [
    {{
      "name": "propertyName",
      "type": "object|datatype",
      "domain": "ClassName",
      "range": "ClassName or xsd:string",
      "description": "What this property represents"
    }}
  ]
}}

Be precise and focused. Quality over quantity."""

    def generate_iterative_extension_prompts(self) -> List[str]:
        """Generate multiple focused prompts for iterative extension (literature approach)."""
        cq_groups = self._group_competency_questions()
        
        prompts = []
        for theme, questions in cq_groups.items():
            if not questions:
                continue
                
            # Create theme-specific prompt
            prompt = f"""Focus on extending the ontology for: {theme}

Competency Questions:
{chr(10).join(f"- {cq}" for cq in questions[:2])}

Add 2-4 classes and 3-6 properties specifically for this theme.
Be very focused and avoid generic additions.

[Same JSON format as before]
"""
            prompts.append(prompt)
        
        return prompts
        """Call Ollama LLM with the extension prompt."""
        url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,  # Enable streaming to see progress
            "options": {
                "temperature": float(getattr(self, "temperature", 0.5)),
                "num_predict": 2048,
            }
        }

        logger.info("calling_llm", model=self.model, prompt_length=len(prompt))

        try:
            with httpx.stream("POST", url, json=payload, timeout=self.timeout) as resp:
                resp.raise_for_status()
                full_response = ""
                print(f"\n🤖 Starting LLM generation with {self.model}...")
                
                for line in resp.iter_lines():
                    if line:
                        try:
                            data = json.loads(line.decode('utf-8'))
                            if 'response' in data:
                                chunk = data['response']
                                full_response += chunk
                                print(chunk, end='', flush=True)
                            
                            # Check if generation is done
                            if data.get('done', False):
                                print(f"\n✅ LLM generation completed. Total tokens: {data.get('eval_count', 'unknown')}")
                                break
                                
                        except json.JSONDecodeError:
                            continue
                
                return full_response
                
        except Exception as e:
            print(f"\n❌ Streaming failed: {e}")
            print("Falling back to non-streaming mode...")
            logger.warning("streaming_failed", error=str(e))
            
            # Fall back to non-streaming
            payload["stream"] = False
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            result = resp.json()
            return result["response"]

    def _extract_json_block(self, text: str) -> str | None:
        """Try multiple heuristics to extract a JSON object from LLM text."""
        # 1) fenced ```json``` blocks
        m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text, re.IGNORECASE)
        if m:
            return m.group(1)

        # 2) first balanced JSON object that contains the keys we expect
        key_pos = None
        for key in ("new_classes", "new_properties"):
            kp = text.find(key)
            if kp != -1:
                key_pos = kp
                break

        if key_pos is None:
            # fallback: find first '{' and try to balance
            start = text.find('{')
        else:
            # find nearest '{' before the key
            start = text.rfind('{', 0, key_pos)
            if start == -1:
                start = text.find('{')

        if start == -1:
            return None

        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

        return None

    def call_llm_with_retry(
        self,
        prompt: str,
        max_retries: int = 3,
    ) -> Dict:
        """Call LLM and parse its response with automatic retries.

        On each retry the prompt is augmented with a strong "JSON only" nudge
        so that models that initially output free-text analysis have another
        chance to produce valid JSON.

        After exhausting retries the method returns a minimal empty extension
        instead of crashing, so experiments can still record a 0-class result
        rather than an outright failure.
        """
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                if attempt == 1:
                    current_prompt = prompt
                else:
                    # Augment prompt with explicit JSON-only instruction
                    current_prompt = (
                        prompt
                        + "\n\n"
                        + "CRITICAL REMINDER (retry attempt {attempt}): "
                        + "Your ENTIRE response must be a single valid JSON object. "
                        + "Do NOT include any analysis, reasoning, markdown, or text "
                        + "outside the JSON. Start your response with {{ and end with }}. "
                        + 'The JSON must have "new_classes" and "new_properties" arrays.'
                    ).replace("{attempt}", str(attempt))
                    # Bust the response cache so we get a fresh answer
                    current_prompt += f"  [retry-{attempt}]"

                response = self.call_llm(current_prompt, verbose=self.verbose)
                parsed = self.parse_llm_response(response)
                if attempt > 1:
                    logger.info("retry_succeeded", attempt=attempt)
                return parsed

            except Exception as e:
                last_error = e
                logger.warning(
                    "llm_parse_retry",
                    attempt=attempt,
                    max_retries=max_retries,
                    error=str(e)[:300],
                )
                print(f"   ⚠️  Attempt {attempt}/{max_retries} failed: {str(e)[:120]}")

        # All retries exhausted — return empty extension so the experiment
        # records a 0-class result instead of crashing.
        logger.error(
            "all_retries_exhausted",
            max_retries=max_retries,
            last_error=str(last_error)[:500],
        )
        print(f"   ❌ All {max_retries} attempts exhausted — returning empty extension")
        return {"new_classes": [], "new_properties": []}

    def parse_llm_response(self, response: str) -> Dict:
        """Parse the LLM's JSON response into structured data using Pydantic validation.

        This is tolerant to LLMs that prepend analysis or include lists for property
        ranges. It will extract the JSON block when possible and normalize common
        variant shapes (list ranges, pipe-separated types).
        """

        # Strip <think>...</think> blocks (qwen-style reasoning tokens)
        if "</think>" in response:
            response = response.split("</think>", 1)[1].strip()

        try:
            # With structured outputs, the response should be pure JSON
            extension = OntologyExtension.model_validate_json(response)
            return extension.model_dump()
        except Exception as e:
            # Fallback to manual parsing if structured output fails
            logger.warning("structured_parse_failed", error=str(e), response=response[:500])

            json_str = self._extract_json_block(response)
            if not json_str:
                raise ValueError(f"No JSON found in LLM response: {response[:500]}...")

            try:
                data = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error("json_parse_failed", error=str(e), response=response[:1000])
                raise

            # --- Normalise common LLM variations ---
            # Ensure new_properties ranges are strings (LLM may return lists)
            for p in data.get("new_properties", []):
                rv = p.get("range")
                if isinstance(rv, list) and rv:
                    # prefer an XSD-like type if present, otherwise first element
                    picked = next((r for r in rv if isinstance(r, str) and r.lower().startswith("xsd:")), rv[0])
                    p["range"] = picked
                # Normalize 'type' fields like 'object|datatype'
                t = p.get("type")
                if isinstance(t, str) and "|" in t:
                    opts = [s.strip().lower() for s in t.split("|")]
                    p["type"] = "object" if "object" in opts else opts[0]

            # Ensure new_classes are well-formed (fill missing fields)
            for c in data.get("new_classes", []):
                if "properties" not in c or c["properties"] is None:
                    c["properties"] = []
                if "parent_class" not in c:
                    c["parent_class"] = None

            return data

    def generate_owl_extensions(self, parsed_data: Dict) -> Graph:
        """Convert parsed LLM response into OWL RDF graph."""

        extension_graph = Graph()

        # Bind namespaces
        extension_graph.bind("owl", OWL)
        extension_graph.bind("rdf", RDF)
        extension_graph.bind("rdfs", RDFS)
        extension_graph.bind("xsd", XSD)
        extension_graph.bind("plan", PLAN_NS)
        extension_graph.bind("", ONTOLOGY_NS)

        # Add new classes
        for class_data in parsed_data.get("new_classes", []):
            class_name = class_data["name"]
            class_uri = ONTOLOGY_NS[class_name]

            # Add class declaration
            extension_graph.add((class_uri, RDF.type, OWL.Class))

            # Add label/description
            if "description" in class_data:
                extension_graph.add((class_uri, RDFS.comment, Literal(class_data["description"])))

            # Add subclass relationship
            parent = class_data.get("parent_class")
            if parent:
                if parent in ["Thing", "owl:Thing"]:
                    parent_uri = OWL.Thing
                else:
                    # Try to find parent in seed ontology or assume it's in our namespace
                    parent_uri = ONTOLOGY_NS[parent]
                extension_graph.add((class_uri, RDFS.subClassOf, parent_uri))

        # Add new properties
        for prop_data in parsed_data.get("new_properties", []):
            prop_name = prop_data["name"]
            prop_uri = ONTOLOGY_NS[prop_name]

            # Determine property type
            prop_type = prop_data.get("type", "object")
            if prop_type == "object":
                rdf_type = OWL.ObjectProperty
            else:
                rdf_type = OWL.DatatypeProperty

            extension_graph.add((prop_uri, RDF.type, rdf_type))

            # Add label/description
            if "description" in prop_data:
                extension_graph.add((prop_uri, RDFS.comment, Literal(prop_data["description"])))

            # Add domain
            domain = prop_data.get("domain")
            if domain:
                domain_uri = ONTOLOGY_NS[domain]
                extension_graph.add((prop_uri, RDFS.domain, domain_uri))

            # Add range (tolerant to lists and multiple formats)
            range_val = prop_data.get("range")
            if range_val:
                # Accept list forms produced by some LLMs
                if isinstance(range_val, list) and range_val:
                    # choose first XSD-like if present else first element
                    candidate = next((r for r in range_val if isinstance(r, str) and r.lower().startswith("xsd:")), range_val[0])
                    range_val = candidate

                if isinstance(range_val, str) and range_val.startswith("xsd:"):
                    # XSD datatype
                    range_uri = XSD[range_val[4:]]  # Remove "xsd:" prefix
                elif isinstance(range_val, str) and range_val in ["string", "date", "int", "boolean"]:
                    # Common XSD types without prefix
                    range_uri = XSD[range_val]
                elif isinstance(range_val, str):
                    # Assume it's a class in our ontology
                    range_uri = ONTOLOGY_NS[range_val]
                else:
                    # Fallback to string
                    range_uri = XSD.string

                extension_graph.add((prop_uri, RDFS.range, range_uri))

        logger.info("owl_extensions_generated",
                   new_classes=len(parsed_data.get("new_classes", [])),
                   new_properties=len(parsed_data.get("new_properties", [])),
                   triples=len(extension_graph))

        return extension_graph

    def extend_ontology(self) -> Graph:
        """Delegate to the strategy's extend_ontology method."""
        return self.strategy.extend_ontology()

    def save_results(self, graph: Graph, output_dir: Path, experiment_name: str):
        """Save the extended ontology and metadata."""

        output_dir.mkdir(parents=True, exist_ok=True)

        # Save OWL file
        owl_path = output_dir / "ontology_latest.owl"
        graph.serialize(str(owl_path), format="xml")
        logger.info("owl_saved", path=owl_path)

        # Save metadata
        metadata = {
            "experiment_name": experiment_name,
            "method": "llm_only_baseline",
            "model": self.model,
            "seed_ontology": str(self.seed_path),
            "competency_questions": len(self.cqs),
            "final_triples": len(graph),
            "seed_triples": len(self.seed_graph),
            "extension_triples": len(graph) - len(self.seed_graph),
        }

        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        logger.info("metadata_saved", path=metadata_path)


def main():
    """CLI entry point for LLM-only baseline."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="LLM-only ontology extension baseline")
    parser.add_argument("--model", default="gemma4:e2b", help="Ollama model to use")
    parser.add_argument("--strategy", default="naive", 
                       choices=["naive", "modular", "iterative", "adaptive"],
                       help="Baseline strategy to use")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--experiment-name", required=True, help="Experiment identifier")
    parser.add_argument("--seed", default="data/seed_ontology/plan-ontology-v1.0.owl", help="Seed ontology path")
    parser.add_argument("--cqs", default="data/evaluation/competency_questions.json", help="Competency questions path")
    parser.add_argument("--verbose", action="store_true", help="Show verbose token output during generation")
    parser.add_argument("--timeout", type=float, default=None, help="Override LLM HTTP timeout (seconds)")
    parser.add_argument("--temperature", type=float, default=None, help="Override generation temperature for the LLM")

    args = parser.parse_args()

    # Load settings to check W&B configuration
    settings = Settings()

    # Initialize W&B with clean naming if enabled
    if settings.wandb_enabled:
        run_name = args.experiment_name if args.experiment_name else f"llm_only_{args.strategy}"
        model_short = args.model.split(":")[0]  # Just the model name, not version
        tags = [model_short]  # Include the clean model name
        if args.experiment_name:
            tags.append(args.experiment_name)
        
        wandb.init(
            project=settings.wandb_project,
            entity=settings.wandb_entity,
            name=run_name,
            config={
                "model": args.model,
                "strategy": args.strategy,
                "experiment_name": args.experiment_name,
                "method": f"llm_only_{args.strategy}",
                "seed_ontology": args.seed,
                "competency_questions": args.cqs,
            },
            tags=tags,
        )
    else:
        logger.info("wandb_disabled", msg="W&B logging disabled")

    # Set LangSmith experiment context for trace grouping
    try:
        from ontology_hitl.agents.base import set_experiment_context, clear_experiment_context
        set_experiment_context(
            experiment_name=args.experiment_name or f"llm_only_{args.strategy}",
            model=args.model,
            strategy=args.strategy,
        )
    except Exception:
        pass

    start_time = time.time()

    try:
        # Initialize baseline
        baseline = LLMOnlyBaseline(
            seed_ontology_path=Path(args.seed),
            cq_path=Path(args.cqs),
            strategy=args.strategy,
            model=args.model,
            verbose=args.verbose
        )

        # Apply optional overrides passed via CLI
        if args.timeout is not None:
            baseline.timeout = float(args.timeout)
        if args.temperature is not None:
            # attach temperature to instance for use by call_llm
            setattr(baseline, "temperature", float(args.temperature))

        # Run extension
        extended_graph = baseline.extend_ontology()

        # Save results
        output_dir = Path(args.output)
        baseline.save_results(extended_graph, output_dir, args.experiment_name)

        # Log metrics to W&B
        execution_time = time.time() - start_time
        metadata = {
            "experiment_name": args.experiment_name,
            "method": "llm_only_baseline",
            "model": args.model,
            "seed_ontology": str(baseline.seed_path),
            "competency_questions": len(baseline.cqs),
            "final_triples": len(extended_graph),
            "seed_triples": len(baseline.seed_graph),
            "extension_triples": len(extended_graph) - len(baseline.seed_graph),
            "execution_time_seconds": execution_time,
        }
        
        wandb.log(metadata)
        wandb.finish()

        # Clear LangSmith experiment context
        try:
            clear_experiment_context()
        except Exception:
            pass

        print(f"LLM-only baseline completed for {args.experiment_name}")
        print(f"Results saved to {output_dir}")
        print(f"W&B run: {run_name}")

    except Exception as e:
        try:
            clear_experiment_context()
        except Exception:
            pass
        wandb.finish()
        raise


if __name__ == "__main__":
    main()