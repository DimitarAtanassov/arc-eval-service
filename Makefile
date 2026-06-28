.DEFAULT_GOAL := help

sources = src tests

APP ?= arc_eval_service
LOCAL_URL ?= http://127.0.0.1:8000

.PHONY: help
help:
	@grep -E '^\.PHONY: .*?## .*$$' $(MAKEFILE_LIST) | \
		sort | \
		awk 'BEGIN {FS = ".PHONY: |## "}; {printf "\033[36m%-19s\033[0m %s\n", $$2, $$3}'

.PHONY: prepare ## Install packages, prepare virtual environment
prepare:
	uv sync --all-groups --frozen

.PHONY: lintable ## Apply auto-formatting and auto-linting
lintable: prepare
	uv run ruff format $(sources)
	uv run ruff check --fix $(sources)

.PHONY: lint ## Run linting checks
lint: prepare
	uv lock --check
	uv run ruff format --check $(sources)
	uv run ruff check $(sources)
	uv run mypy $(sources)

.PHONY: openapi ## Export the OpenAPI schema to openapi.json
openapi: prepare
	uv run python -c "import json; from $(APP).api.main import app; \
print(json.dumps(app.openapi(), indent=2))" > openapi.json
	@echo "OpenAPI schema written to openapi.json"

.PHONY: test ## Run tests and coverage reports
test: prepare
	uv run coverage run -m pytest
	uv run coverage report

.PHONY: test-unit ## Run unit tests
test-unit: prepare
	uv run pytest -m unit

.PHONY: test-integration ## Run integration tests
test-integration: prepare
	uv run pytest -m integration

.PHONY: test-e2e ## Run E2E tests
test-e2e: prepare
	uv run pytest -m e2e

.PHONY: check ## Run lint and the full test suite (CI gate)
check: lint test

.PHONY: migrate ## Apply database migrations to head (needs ARC_EVAL_DATABASE_URL)
migrate: prepare
	uv run alembic upgrade head

.PHONY: migration ## Autogenerate a migration (NAME=description, needs ARC_EVAL_DATABASE_URL)
migration: prepare
	uv run alembic revision --autogenerate -m "$(or $(NAME),change)"

.PHONY: downgrade ## Roll back the last migration (needs ARC_EVAL_DATABASE_URL)
downgrade: prepare
	uv run alembic downgrade -1

.PHONY: run ## Run the main application locally with auto-reload
run: prepare
	uv run uvicorn $(APP).api.main:app --reload --reload-dir src --host 0.0.0.0 --port 8000

.PHONY: clean ## Remove all temporary files
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]'`
	rm -f `find . -type f -name '*~'`
	rm -f `find . -type f -name '.*~'`
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .ruff_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -rf dist
	rm -rf coverage.xml
	rm -f openapi.json

.PHONY: package ## Build a python package
package: prepare
	uv build

.PHONY: docker ## Build the application as a docker container
docker:
	docker build -t arc-eval-service:latest . $(ARGS)

.PHONY: docker-run ## Build and run the application as a docker container
docker-run: docker
	docker run -p 8000:8000 -it arc-eval-service:latest

.PHONY: bump-version-major ## Bump the major version in pyproject.toml and uv.lock
bump-version-major:
	@echo "Bumping major version..."
	@current_version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current_version"; \
	new_version="$$((major + 1)).0.0"; \
	echo "Updating version from $$current_version to $$new_version"; \
	sed -i '' "s/^version = \"$$current_version\"/version = \"$$new_version\"/" pyproject.toml; \
	uv lock; \
	echo "Version bumped successfully to $$new_version"

.PHONY: bump-version-minor ## Bump the minor version in pyproject.toml and uv.lock
bump-version-minor:
	@echo "Bumping minor version..."
	@current_version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current_version"; \
	new_version="$$major.$$((minor + 1)).0"; \
	echo "Updating version from $$current_version to $$new_version"; \
	sed -i '' "s/^version = \"$$current_version\"/version = \"$$new_version\"/" pyproject.toml; \
	uv lock; \
	echo "Version bumped successfully to $$new_version"

.PHONY: bump-version-patch ## Bump the patch version in pyproject.toml and uv.lock
bump-version-patch:
	@echo "Bumping patch version..."
	@current_version=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	IFS='.' read -r major minor patch <<< "$$current_version"; \
	new_version="$$major.$$minor.$$((patch + 1))"; \
	echo "Updating version from $$current_version to $$new_version"; \
	sed -i '' "s/^version = \"$$current_version\"/version = \"$$new_version\"/" pyproject.toml; \
	uv lock; \
	echo "Version bumped successfully to $$new_version"
