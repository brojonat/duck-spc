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

.PHONY: skills
skills: ## (Re)install the pinned agent skills
	./install-skills.sh
