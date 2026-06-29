.PHONY: all test lint format check clean

# Project source files (excluding vendored code)
SRC := adapter.py call_handler.py chat_tokens.py media.py rpc_tools.py setup.py __init__.py
TEST := tests/
BLACK := black
BLACK_OPTS := --line-length 120
FLAKE8 := flake8

# Default target
all: test lint

# Run tests from tests directory to avoid __init__.py import issues
test:
	@echo "Running tests..."
	@cd tests && python3 -m pytest -v --tb=short

# Format with black
format:
	@echo "Formatting code with black..."
	@$(BLACK) $(BLACK_OPTS) $(SRC) $(TEST) docs/ skills/

# Lint with flake8
lint:
	@echo "Running flake8..."
	@$(FLAKE8) $(SRC) $(TEST) --max-line-length=120 --extend-ignore=E203,W503,F401,E402

# Check formatting (black --check)
check:
	@echo "Checking code formatting..."
	@$(BLACK) --check $(BLACK_OPTS) $(SRC) $(TEST) docs/ skills/

# Clean
clean:
	@rm -rf __pycache__ */__pycache__ */*/__pycache__ .pytest_cache .mypy_cache
	@find . -name "*.pyc" -delete
