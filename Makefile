# Override tools on the command line, e.g. make lint PYTHON=python3.
ifeq ($(OS),Windows_NT)
# Keep recipe quoting consistent when GNU Make is supplied by MSYS2.
ifneq ($(wildcard C:/msys64/usr/bin/sh.exe),)
SHELL := C:/msys64/usr/bin/sh.exe
.SHELLFLAGS := -c
endif
endif
PYTHON ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python3))
NODE ?= node
CPPCHECK ?= $(if $(wildcard C:/msys64/ucrt64/bin/cppcheck.exe),C:/msys64/ucrt64/bin/cppcheck.exe,cppcheck)
POWERSHELL ?= powershell.exe
REQUIREMENTS_PYTHON ?= $(if $(wildcard build_tools/runtime/doorstop/Scripts/python.exe),build_tools/runtime/doorstop/Scripts/python.exe,$(PYTHON))

.PHONY: help clean lint lint-js lint-types lint-python lint-shell lint-native lint-powershell lint-format lint-generated test test-llt test-hlt test-adhoc requirements requirements-check
.DEFAULT_GOAL := help

help:
	@$(NODE) -e "console.log('make lint: JavaScript/Python/native lint, shell syntax, formatting and generated assets\nmake lint-powershell: parse Windows scripts without executing them\nmake test: server and platform-independent terminal tests\nSee README.md for tool installation and overrides.')"
	@echo "make clean: remove caches, scratch files and build outputs (preview: make clean CLEAN_FLAGS=--dry-run)"
	@echo "make requirements: validate coverage and publish requirements/output/index.html"
	@echo "make requirements-check: validate requirements without publishing"

requirements:
	$(REQUIREMENTS_PYTHON) build_tools/requirements.py

requirements-check:
	$(REQUIREMENTS_PYTHON) build_tools/requirements.py --check

clean:
	$(PYTHON) build_tools/clean.py $(CLEAN_FLAGS)

lint: lint-js lint-types lint-python lint-shell lint-native lint-format lint-generated
ifeq ($(OS),Windows_NT)
lint: lint-powershell
endif

lint-js:
	$(NODE) node_modules/eslint/bin/eslint.js .

lint-types:
	$(NODE) node_modules/typescript/bin/tsc -p zmala_server/tsconfig.json
	$(NODE) node_modules/typescript/bin/tsc -p zmala_server/tsconfig.admin.json

lint-python:
	$(PYTHON) -m ruff check .

lint-shell:
	$(NODE) build_tools/lint-sources.cjs shell

lint-native:
	$(NODE) build_tools/lint-sources.cjs native "$(CPPCHECK)"

lint-powershell:
	$(POWERSHELL) -NoProfile -File build_tools/lint-powershell.ps1

lint-format:
	$(NODE) node_modules/prettier/bin/prettier.cjs --check "zmala_server/**/*.{js,cjs,ts,css,html}" "tests/**/*.{js,cjs}" "build_tools/*.{js,cjs}" "requirements/product/template/*.{js,css}" eslint.config.cjs "zmala_server/tsconfig*.json"

lint-generated:
	$(NODE) build_tools/build-admin.cjs --check

test: test-llt test-hlt

test-llt:
	$(NODE) build_tools/build-admin.cjs
	$(NODE) build_tools/run-tests.cjs LLT
	$(PYTHON) -m unittest discover -s tests/server/LLT -t . -p "test_*.py"
	$(PYTHON) -m unittest discover -s tests/terminal/LLT -t . -p "test_*.py"

test-hlt:
	$(NODE) build_tools/build-admin.cjs
	$(NODE) build_tools/run-tests.cjs HLT
	$(PYTHON) -m unittest discover -s tests/server/HLT -t . -p "test_*.py"
	$(PYTHON) -m unittest discover -s tests/terminal/HLT -t . -p "test_*.py"

# Toolchain/Windows compatibility checks are not Pi product requirement coverage.
# Do not discover manual or live scenarios here.
test-adhoc:
	$(NODE) build_tools/run-tests.cjs adhoc
	$(PYTHON) -m unittest discover -s tests/adhoc -t . -p "test_*.py"
