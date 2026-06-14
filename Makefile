.DEFAULT_GOAL := help

.PHONY: help
help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Install dependencies with uv
	uv sync

.PHONY: test
test: ## Run tests, tee to logs/
	@mkdir -p logs
	uv run pytest 2>&1 | tee logs/test.log

.PHONY: lint
lint: ## Lint and type-check
	uv run ruff check .
	uv run ty check

.PHONY: fmt
fmt: ## Format code
	uv run ruff format .

.PHONY: demo
demo: ## Generate synthetic parquet, run baseline/check/chart end-to-end, tee to logs/
	@mkdir -p logs
	uv run python -m duck_spc.demo 2>&1 | tee logs/demo.log

.PHONY: run-deck
run-deck: ## Serve the slide deck at http://localhost:8042, tee to logs/
	@mkdir -p logs
	cd docs/deck && python3 -m http.server 8042 2>&1 | tee ../../logs/deck.log

.PHONY: edit-notebook
edit-notebook: ## Edit the story notebook live (marimo, discoverable for pairing)
	@mkdir -p logs
	uvx marimo edit --sandbox --no-token notebooks/trust_the_limits.py 2>&1 | tee logs/marimo.log

.PHONY: check-notebook
check-notebook: ## Lint the notebook and run it in script mode
	uvx marimo check notebooks/trust_the_limits.py
	uv run --with marimo,numpy,matplotlib python notebooks/trust_the_limits.py

# The brojonat-hugo site vendors this deck from the remote (its `make
# vendor-deck`); preview it locally with `make run-deck`.

.PHONY: skills
skills: ## (Re)install the pinned agent skills
	./install-skills.sh
