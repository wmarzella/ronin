.PHONY: help install search apply format lint check clean setup test

# Ronin - Job Search Automation

help:
	@echo "Ronin - Job Search Automation"
	@echo "=============================="
	@echo ""
	@echo "Commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make search     - Search for jobs"
	@echo "  make apply      - Apply to jobs"
	@echo ""
	@echo "Development:"
	@echo "  make format     - Format code with Black"
	@echo "  make lint       - Lint code with Flake8"
	@echo "  make check      - Run both formatting and linting"
	@echo "  make clean      - Clean up temporary files"

install:
	@echo "Installing dependencies..."
	@pip install -r requirements.txt
	@echo "Done!"

setup: install

search:
	@echo "Searching for jobs..."
	@source venv/bin/activate && python -m ronin.cli.search

apply:
	@echo "Applying to jobs..."
	@source venv/bin/activate && python -m ronin.cli.apply

test:
	@echo "Testing imports..."
	@source venv/bin/activate && python -c "from ronin.config import load_config; from ronin.scraper import SeekScraper; from ronin.analyzer import JobAnalyzerService; from ronin.applier import SeekApplier; from ronin.db import SQLiteManager; from ronin.ai import AIService; print('All imports successful!')"

format:
	@echo "Formatting code..."
	@black --line-length 88 ronin/
	@echo "Done!"

lint:
	@echo "Linting code..."
	@flake8 --max-line-length 88 --extend-ignore E203,W503 ronin/
	@echo "Done!"

check: format lint

clean:
	@echo "Cleaning up..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@find . -type f -name "*.log" -delete
	@echo "Done!"
