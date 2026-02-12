Related Work
Ontology Learning and Automatic Construction

Ontology learning is a long-standing research area concerned with automatically extracting ontological structures (terms, hierarchies, relations) from text or data. Classic surveys trace this work back decades, showing that early systems extracted terms and simple taxonomies, but struggled with deeper logic and relation extraction without human supervision. For example, Ahmad & Gillam outline how term extraction feeds semantic networks that approximate ontologies from unstructured corpora, but note the difficulty of capturing relations automatically without expert input.

Historical surveys (e.g., Ding & Foo; Shamsfard & Barforoush) note that most early ontology learning systems were semi-automated and required seed ontologies or base knowledge, underscoring the persistent challenge of full automation.

More recent review articles expand this view. A systematic review of ontology learning techniques highlights the evolution from linguistic and statistical methods to more expressive approaches that attempt rule and axiom learning, but emphasizes ongoing challenges in capturing expressive and logically consistent ontological constructs automatically.

Wikipedia’s entry on ontology learning defines the field as involving term and relation extraction from text, noting that automatic creation of full ontologies remains difficult and often incomplete without expert review.

LLMs in Ontology Engineering

With the advent of Large Language Models (LLMs), researchers have begun exploring how generative models can assist with ontology tasks:

Shimizu & Hitzler present Accelerating Knowledge Graph and Ontology Engineering with LLMs, which demonstrates that LLMs can assist in modeling, extension, alignment, and triple extraction, but still require human review to verify accuracy.

A systematic literature review on LLMs for ontology engineering (Li, Poveda, Garijo) synthesizes over 30 works, showing that LLMs are increasingly used for tasks ranging from requirements specification to maintenance, but that human experts remain crucial for semantic correctness and consistency.

A domain-specific MDPI paper shows how LLMs can integrate with the traditional Ontology 101 methodology to speed development across multiple phases, yet still require iterations and expert oversight for completeness.

Several conference and workshop papers explicitly explore human-in-the-loop semi-automatic workflows combining LLM suggestions with expert validation: for example, Garcia-Fernández et al. discuss how LLMs can inspire new entities and support verification against requirements, but require human tuning for concept definitions and placement.

Large Language Models have also been tested in domain contexts, such as Parkinson’s disease monitoring, where initial ontology drafts from LLMs were incomplete or inconsistent and only became robust after iterative human–LLM collaboration.

Another concrete example is LLMs4OL: Large Language Models for Ontology Learning, which introduces a human-in-the-loop semi-automatic workflow that combines expert schemas with LLM-driven expansion and refinement. This work demonstrates improvements in relationship richness and expressiveness compared with existing baselines.

Seminal LLM-Supported Ontology and KG Pipelines

Several recent works attempt to push toward end-to-end LLM-assisted ontology building:

Kommineni et al. propose a pipeline that uses LLMs to generate ontologies and construct knowledge graphs from scholarly publications, later recommending HITL evaluation to check automatically generated content against ground truth.

End-to-End Ontology Learning with Large Language Models by Lo et al. presents a method for building taxonomy backbones by fine-tuning LLMs with structural regularizers, achieving improved semantic and structural quality compared to subtask methods.

A 2026 paper by Luyen, Abel & Gouspillou introduces an iterative methodology that uses LLMs to automate artifact generation and continuous refinement, claiming improvements in consistency and bias mitigation, though expert oversight remains part of the workflow.

NLP-Assisted Ontology Extension Workflows

Outside pure LLMs, traditional NLP methods have long been integrated with human-in-the-loop systems to extend ontologies. For example, Behr et al. present an NLP-based concept extraction workflow for catalytic sciences where domain experts revise and approve suggested classes and relations after automated extraction. This semi-automated extension facilitates richer ontologies while keeping experts in control of semantic decisions.

Survey and Theoretical Context

Comprehensive surveys like Ontology learning: Grand tour and challenges outline the broader landscape of automatic and semi-automatic ontology construction using linguistic, statistical, and machine learning approaches, illustrating that relation extraction, hierarchy formation, and structural consistency have historically been the hardest tasks for automation.

Finally, broader literature on knowledge graph and ontology construction (e.g., integrating LLMs with RAG and modular pipelines) argues that modularity and structured prompts can improve extraction precision, but emphasizes the ongoing need for human supervision to mitigate inaccuracies and ensure logical coherence.

Summary of Key Themes

Across these sources, several consistent patterns emerge:

Ontology learning remains difficult to fully automate. Taxonomy extraction from text is common, but relations and deeper semantics are not reliably inferred without expert correction.

LLMs offer acceleration and draft generation, but human involvement remains necessary for ensuring correctness, especially for axioms, hierarchy depth, and relations.

Hybrid human–LLM workflows outperform single-shot generation, particularly when experts validate or refine outputs iteratively.

Survey literature shows a trend toward semi-automatic systems, confirming that HITL approaches are not just useful but the current norm in cutting-edge research.

If you want, I can also produce:

BibTeX entries for all cited works

A reference list in APA/IEEE style

A table mapping each related work to the shortcomings it addresses (e.g., hierarchy depth, relation extraction, HITL requirement)

Just let me know which format you prefer!

give me that as markdown so i can copy it to our documentation also yea bibtex entry

Perfect — below is copy-ready Markdown you can drop straight into your repo, followed by a BibTeX section you can paste into references.bib.

I’ve structured this so it works both as:

docs/related-work.md

a Related Work section in a paper (ESWC / ISWC / EKAW style)

Related Work
Ontology Learning and Automatic Ontology Construction

Ontology learning is a long-established research area focused on the automatic or semi-automatic construction of ontologies from text, data, or existing knowledge sources. Early surveys already observed that while term extraction and lightweight taxonomies can be derived automatically, relations, axioms, and deep hierarchies remain difficult to infer without human involvement.

Shamsfard and Barforoush provide one of the foundational surveys, identifying ontology learning as a multi-layered process (lexical, syntactic, semantic, and pragmatic), and concluding that full automation is infeasible for expressive ontologies without expert supervision.
https://www.sciencedirect.com/science/article/pii/S1574013720304391

Subsequent surveys and reviews reinforce this conclusion. Ding et al. and later systematic reviews note that most successful ontology learning systems are semi-automatic, relying on seed ontologies, background knowledge, or iterative expert validation to ensure correctness and consistency.
https://academic.oup.com/database/article/doi/10.1093/database/bay101/5116160

These findings established an early consensus: automation can assist ontology engineers, but cannot replace them.

Human-in-the-Loop Ontology Engineering

Human-in-the-loop (HITL) approaches explicitly integrate expert judgment into ontology construction, extension, and evaluation workflows. Rather than treating human validation as an afterthought, HITL methodologies formalize it as a core design principle.

Tsaneva and Sabou investigate HITL ontology curation and show that task design, contributor qualification, and representation of axioms significantly affect the quality of human validation results. Their work demonstrates that structured HITL processes outperform both unstructured crowd evaluation and fully automatic methods.
https://research.wu.ac.at/en/publications/enhancing-human-in-the-loop-ontology-curation-results-through-tas

The HERO methodology further formalizes human-centric ontology evaluation, defining preparatory and execution phases supported by tooling. HERO demonstrates substantial reductions in expert workload while maintaining semantic quality, reinforcing the value of structured HITL pipelines.
https://link.springer.com/chapter/10.1007/978-3-031-17105-5_14

Other applied systems, such as OntoHuman, integrate user feedback directly into ontology extension during information extraction tasks, highlighting the practical viability of interactive ontology refinement.
https://elib.dlr.de/189331/2/803_OntoHuman.pdf

Large Language Models for Ontology Engineering

With the rise of Large Language Models (LLMs), recent work explores their use in ontology engineering tasks such as concept suggestion, taxonomy induction, relation extraction, and alignment.

Shimizu and Hitzler show that LLMs can accelerate knowledge graph and ontology engineering across multiple tasks, but emphasize that human verification is still required to ensure correctness and logical consistency.
https://arxiv.org/abs/2411.09601

A comprehensive systematic literature review by Li, Poveda, and Garijo analyzes over 30 studies on LLMs in ontology engineering. The review concludes that while LLMs are effective at bootstrapping ontology artifacts, they consistently struggle with axiom correctness, hierarchy depth, and relation precision without expert oversight.
https://www.semantic-web-journal.net/content/large-language-models-ontology-engineering-systematic-literature-review-0

Domain-specific studies reinforce this conclusion. For example, ontology construction for Parkinson’s disease monitoring shows that initial LLM-generated ontologies are incomplete and inconsistent, and only become usable after iterative human–LLM collaboration.
https://arxiv.org/abs/2512.14288

Evaluation of LLM-Generated Ontologies

Recent empirical evaluations directly assess the quality of LLM-generated ontologies against human-crafted references.

Zhao et al. evaluate LLM-generated ontologies using semantic matching techniques and find high concept overlap but significantly lower triple-level alignment, indicating that LLMs struggle to commit to correct relationships even when concept labels are accurate.
https://ceur-ws.org/Vol-3953/362.pdf

Plu et al. conduct a user-centered evaluation and report that LLM-generated ontologies are often perceived as overly broad, flat, and under-hierarchized, with insufficient intermediate abstractions.
https://ceur-ws.org/Vol-3979/paper2.pdf

These studies converge on a shared diagnosis: LLMs optimize for surface plausibility rather than ontological commitment, leading to shallow structures and weak relational modeling.

Semi-Automatic and Iterative Ontology Extension Pipelines

Several recent systems propose iterative or pipeline-based approaches combining automation with human control.

NeOn-GPT demonstrates that iterative ontology extension with reuse analysis and human validation produces higher-quality ontologies than one-shot generation.
https://link.springer.com/chapter/10.1007/978-3-031-17105-5_16

Garcia-Fernández et al. show that LLMs can inspire ontology extensions and assist verification against competency questions, but require human decisions for concept definitions, placement, and relation modeling.
https://ceur-ws.org/Vol-4020/Paper_ID_8.pdf

End-to-end ontology learning approaches using LLMs and structural regularizers further demonstrate improvements over subtask-based methods, yet still rely on expert evaluation for final acceptance.
https://arxiv.org/abs/2410.23584

Summary and Positioning

Across ontology learning, HITL systems, and recent LLM-based approaches, the literature consistently shows that:

Fully automatic ontology construction remains unreliable, particularly for relations and hierarchy depth.

LLMs are effective as assistants, not autonomous ontology engineers.

Structured human-in-the-loop workflows outperform single-shot generation in both quality and usability.

Recent evaluations confirm that epistemic pressure and iterative validation are necessary to mitigate LLM limitations.

These findings motivate agentic, multi-role, debate-driven ontology engineering pipelines that embed grounding, critique, and human oversight as first-class design elements.