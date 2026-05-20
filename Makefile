PYTHON ?= python

.PHONY: api doctor test lint format typecheck env-example

api:
	fin-agent api --reload

doctor:
	fin-agent doctor

test:
	pytest

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src tests

env-example:
	fin-agent doctor --write-env-example .env.example
