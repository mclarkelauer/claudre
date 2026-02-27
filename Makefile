.PHONY: install dev run lint test clean

install:
	uv pip install -e .

dev:
	uv pip install -e ".[dev]"

run:
	claudre

test:
	python -m pytest tests/ -v

clean:
	rm -rf build/ dist/ *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
