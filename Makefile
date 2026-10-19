PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin

SILERO_URL ?= https://github.com/snakers4/silero-vad/raw/v5.1.2/src/silero_vad/data/silero_vad.onnx

.PHONY: help install run test lint clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

$(BIN)/pip:
	$(PY) -m venv $(VENV)

models/silero_vad.onnx:
	mkdir -p models
	curl -fsSL -o $@.tmp $(SILERO_URL) && mv $@.tmp $@

install: $(BIN)/pip models/silero_vad.onnx  ## Create venv, install the project (+VAD deps) and fetch the Silero model
	$(BIN)/python -m pip install -e ".[dev,vad]"

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
