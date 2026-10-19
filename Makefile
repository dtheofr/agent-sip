PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

.PHONY: help install run test lint clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

$(BIN)/python:
	$(PY) -m venv $(VENV)

install: $(BIN)/python  ## Create venv and install the project (editable)
	$(BIN)/pip install -e ".[dev]"

config.toml:
	cp config.example.toml config.toml
	@echo "Created config.toml - edit it for your network."

run: install config.toml  ## Start the SIP server (waits for a handset pickup)
	$(BIN)/agent-sip --config config.toml

test:  ## Run unit tests (no install needed)
	PYTHONPATH=src $(PY) -m unittest discover -s tests -v

lint: install  ## Run ruff
	$(BIN)/ruff check src tests

clean:  ## Remove venv and caches
	rm -rf $(VENV) build *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
