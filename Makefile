# Bratislava Open Data LLM — task runner
#
#   make help            list targets
#   make setup           install Python dependencies
#   make model           download the generation model (resumable)
#   make build           run the full data pipeline
#
# Override any variable, e.g. `make build CONFIG=config.yaml` or `make serve PORT=9000`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

PY ?= uv run
CONFIG ?= config.yaml
PORT ?= 8000
MODEL_REPO ?= mlx-community/EuroLLM-22B-Instruct-2512-mlx-4bit
MODEL_DIR ?= models/EuroLLM-22B-4bit
EXTRAS ?= dev,rerank,mlx,api,mcp
PACK_OUT ?= release
FULL ?= 0
DOCS_PORT ?= 3000
DOCS_LOCALE ?= en
EVAL_TYPE ?= all

.PHONY: help setup model ingest download graph index data geo build \
	ask search serve mcp eval pack restore test lint typecheck docs docs-serve \
	docs-dev docs-clean clean clean-data clean-model

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python dependencies (uv)
	uv sync --extra $(EXTRAS)

model: ## Download the generation model (resumable, skipped if present)
	@if [ -f "$(MODEL_DIR)/config.json" ]; then \
		echo "model already present at $(MODEL_DIR)"; \
	else \
		echo "downloading $(MODEL_REPO) -> $(MODEL_DIR)"; \
		HF_HUB_DISABLE_XET=1 $(PY) python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('$(MODEL_REPO)', local_dir='$(MODEL_DIR)')"; \
	fi

ingest: ## Fetch DCAT + Hub search + ArcGIS layer schemas
	$(PY) bdata ingest catalog --config $(CONFIG)
	$(PY) bdata ingest features --config $(CONFIG)

download: ## Download distribution files (25 MB per-file cap)
	$(PY) bdata download --config $(CONFIG)

graph: ## Build the semantic knowledge graph
	$(PY) bdata graph build --with-related --config $(CONFIG)

index: ## Build dataset cards, embeddings and the BM25 index
	$(PY) bdata index build --config $(CONFIG)

data: ## Expose downloaded CSVs as DuckDB views and profile column values
	$(PY) bdata data load --config $(CONFIG)
	$(PY) bdata data profile --config $(CONFIG)

geo: ## Build the district gazetteer and load spatial layers
	$(PY) bdata geo build --config $(CONFIG)
	$(PY) bdata geo load --config $(CONFIG)

build: ## Run the full data pipeline (does not download the model)
	$(MAKE) ingest
	$(MAKE) download
	$(MAKE) graph
	$(MAKE) data
	$(MAKE) index
	$(MAKE) geo

ask: ## Ask a question:  make ask Q="..."
	@test -n "$(Q)" || { echo 'usage: make ask Q="..."'; exit 1; }
	$(PY) bdata ask "$(Q)" --config $(CONFIG)

search: ## Search datasets:  make search Q="..."
	@test -n "$(Q)" || { echo 'usage: make search Q="..."'; exit 1; }
	$(PY) bdata search "$(Q)" --config $(CONFIG)

serve: ## Start the web API (see PORT)
	$(PY) bdata serve --config $(CONFIG) --port $(PORT)

mcp: ## Run the MCP server over stdio
	$(PY) bdata mcp --config $(CONFIG)

eval: ## Evaluate typed cases (EVAL_TYPE=all|discovery|data|geo|abstain|followup)
	$(PY) bdata eval --type $(EVAL_TYPE) --config $(CONFIG)

pack: ## Build a shareable knowledge pack (FULL=1 to include downloads)
	$(PY) python scripts/pack.py --config $(CONFIG) --out $(PACK_OUT) \
		$(if $(filter 1,$(FULL)),--full,)

restore: ## Restore a pack:  make restore PACK=release/bdata-pack-....tar.gz
	@test -n "$(PACK)" || { echo 'usage: make restore PACK=release/bdata-pack-....tar.gz'; exit 1; }
	$(PY) python scripts/pack.py --restore "$(PACK)"

test: ## Run the test suite
	$(PY) pytest -q

lint: ## Lint with ruff
	uv run ruff check .

typecheck: ## Type-check with mypy
	uv run mypy src

docs: ## Build the Docusaurus site (EN + SK)
	cd docs && npm run build

docs-serve: ## Build all locales and serve them (language switch works)
	cd docs && npm run serve -- --build --port $(DOCS_PORT) --no-open

docs-dev: ## Hot-reload dev server, one locale (DOCS_LOCALE=en)
	cd docs && npm start -- --port $(DOCS_PORT) --locale $(DOCS_LOCALE) --no-open

docs-clean: ## Clear the Docusaurus cache and build output
	cd docs && npm run clear

clean: ## Remove tool caches and __pycache__
	rm -rf .pytest_cache .ruff_cache .mypy_cache
	find src tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-data: ## Remove downloaded data, raw snapshots and the catalog DB
	rm -rf data/downloads data/raw
	rm -f data/catalog.duckdb

clean-model: ## Remove the local generation model
	rm -rf $(MODEL_DIR)
