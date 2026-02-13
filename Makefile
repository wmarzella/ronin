PYTHON := venv/bin/python3
PIP := venv/bin/pip

.PHONY: help install setup search apply status test format lint check clean

# Ronin - AI-Powered Job Application Automation

help:
	@echo "Ronin - AI-Powered Job Application Automation"
	@echo "==============================================="
	@echo ""
	@echo "Getting Started:"
	@echo "  make install    - Install dependencies"
	@echo "  make setup      - Run interactive setup wizard"
	@echo ""
	@echo "Usage:"
	@echo "  make search     - Search for jobs"
	@echo "  make apply      - Apply to discovered jobs"
	@echo "  make status     - Show status dashboard"
	@echo ""
	@echo "Development:"
	@echo "  make test       - Test all imports"
	@echo "  make format     - Format code with Black"
	@echo "  make lint       - Lint code with Flake8"
	@echo "  make check      - Run both formatting and linting"
	@echo "  make clean      - Clean up temporary files"

install:
	@echo "Installing dependencies..."
	@$(PIP) install -r requirements.txt
	@echo ""
	@echo "Done! Run 'make setup' to configure Ronin."

setup:
	@$(PYTHON) -m ronin.cli.main setup

search:
	@$(PYTHON) -m ronin.cli.main search

apply:
	@$(PYTHON) -m ronin.cli.main apply

status:
	@$(PYTHON) -m ronin.cli.main status

test:
	@echo "Testing imports..."
	@$(PYTHON) -c "from ronin.config import load_config, get_ronin_home; from ronin.profile import load_profile, Profile; from ronin.scraper import SeekScraper; from ronin.analyzer import JobAnalyzerService; from ronin.applier import SeekApplier; from ronin.applier.base import BaseApplier, get_applier; from ronin.db import SQLiteManager; from ronin.ai import AIService; from ronin.prompts.generator import generate_job_analysis_prompt; from ronin.scheduler import get_schedule_status; print('All imports successful!')"
	@echo "Testing Python file parsing..."
	@$(PYTHON) -c "import ast, os; [ast.parse(open(os.path.join(r,f)).read()) for r,_,fs in os.walk('ronin') for f in fs if f.endswith('.py')]; print('All files parse OK!')"

format:
	@echo "Formatting code..."
	@venv/bin/black --line-length 88 ronin/
	@echo "Done!"

lint:
	@echo "Linting code..."
	@venv/bin/flake8 --max-line-length 88 --extend-ignore E203,W503,E231,E221,E222,E501 ronin/
	@echo "Done!"

check: format lint

clean:
	@echo "Cleaning up..."
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -delete
	@echo "Done!"
