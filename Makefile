.PHONY: install dev lint test format check docs docs-check gap proposals review export evaluate cycle

# Setup
install:
	pip install -e .

dev:
	pip install -e ".[dev]"

# Code quality
lint:
	ruff check src/ tests/ scripts/
	mypy src/

format:
	ruff format src/ tests/ scripts/
	ruff check --fix src/ tests/ scripts/

test:
	pytest tests/ -v --tb=short

check: lint test

# Documentation
docs:
	cd docs && make html

docs-check:
	cd docs && make clean && make html > /dev/null 2>&1 && echo "Docs build successful" || (echo "Docs build failed" && exit 1)

# Workflow steps
gap:
	python scripts/run_gap_analysis.py \
		--checkpoint $(CHECKPOINT) \
		--output data/iterations/$(V)/gap_report.json

proposals:
	python scripts/generate_proposals.py \
		--gap-report data/iterations/$(V)/gap_report.json \
		--output data/iterations/$(V)/proposals.json

review:
	python scripts/review_proposals.py \
		--proposals data/iterations/$(V)/proposals.json \
		--output data/iterations/$(V)/decisions.json

export:
	python scripts/export_ontology.py \
		--decisions data/iterations/$(V)/decisions.json \
		--proposals data/iterations/$(V)/proposals.json \
		--output-owl data/exports/ontology_$(V).owl \
		--output-cq data/exports/cq_$(V).json

evaluate:
	python scripts/evaluate_iteration.py \
		--before data/iterations/$(V)/metrics_before.json \
		--after data/iterations/$(V)/metrics_after.json \
		--output data/iterations/$(V)/evaluation_report.json

# Full cycle (set V=v1 and CHECKPOINT=path)
cycle: gap proposals review export
	@echo "Iteration $(V) complete. Now re-run KGB with exported ontology."
	@echo "  python scripts/full_kg_pipeline.py \\"
	@echo "    --ontology-path data/exports/ontology_$(V).owl \\"
	@echo "    --questions data/exports/cq_$(V).json"
