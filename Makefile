.PHONY: all test lint format check clean

# Default target
all: test lint

# Run tests from tests directory to avoid __init__.py import issues
test:
	@echo "Running tests..."
	@cd tests && python3 -m pytest -v --tb=short

# Format with black
format:
	@echo "Formatting code with black..."
	@python3 -m black adapter.py setup.py __init__.py tests/ docs/ skills/

# Lint with flake8
lint:
	@echo "Running flake8..."
	@python3 -m flake8 adapter.py setup.py __init__.py tests/ --max-line-length=100 --extend-ignore=E203,W503,F401

# Check formatting (black --check)
check: format
	@echo "Checking code formatting..."
	@python3 -m black --check adapter.py setup.py __init__.py tests/ docs/ skills/

# Clean
clean:
	@rm -rf __pycache__ */__pycache__ */*/__pycache__ .pytest_cache .mypy_cache
	@find . -name "*.pyc" -delete
