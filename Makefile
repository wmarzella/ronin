PYTHON := venv/bin/python3
PIP := $(PYTHON) -m pip
ARCH ?= builder

.PHONY: help install setup search apply apply-queue apply-batch apply-status apply-sync apply-review apply-ghosts apply-drift apply-versions run feedback-sync feedback-report feedback-review status worker worker-once test format lint check clean

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
	@echo "  make apply-queue   - Show queue grouped by archetype"
	@echo "  make apply-batch   - Apply one archetype batch (ARCH=builder)"
	@echo "  make apply-status  - Show funnel metrics"
	@echo "  make apply-sync    - Recompute queue + alignment"
	@echo "  make apply-review  - Review close-call selections"
	@echo "  make apply-ghosts  - List ghosted applications"
	@echo "  make apply-drift   - Show drift metrics"
	@echo "  make apply-versions - Show resume version performance"
	@echo "  make run        - Search then apply if jobs pending"
	@echo "  make feedback-sync   - Sync Gmail outcomes"
	@echo "  make feedback-report - Show conversion report"
	@echo "  make feedback-review - Resolve manual matches"
	@echo "  make status     - Show status dashboard"
	@echo "  make worker     - Start remote worker scheduler"
	@echo "  make worker-once - Run one worker cycle"
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

apply-queue:
	@$(PYTHON) -m ronin.cli.main apply queue

apply-batch:
	@$(PYTHON) -m ronin.cli.main apply batch $(ARCH)

apply-status:
	@$(PYTHON) -m ronin.cli.main apply status

apply-sync:
	@$(PYTHON) -m ronin.cli.main apply sync

apply-review:
	@$(PYTHON) -m ronin.cli.main apply review

apply-ghosts:
	@$(PYTHON) -m ronin.cli.main apply ghosts

apply-drift:
	@$(PYTHON) -m ronin.cli.main apply drift

apply-versions:
	@$(PYTHON) -m ronin.cli.main apply versions

run:
	@$(PYTHON) -m ronin.cli.main run

worker:
	@$(PYTHON) -m ronin.cli.main worker start

worker-once:
	@$(PYTHON) -m ronin.cli.main worker once

feedback-sync:
	@$(PYTHON) -m ronin.cli.main feedback sync

feedback-report:
	@$(PYTHON) -m ronin.cli.main feedback report

feedback-review:
	@$(PYTHON) -m ronin.cli.main feedback review

status:
	@$(PYTHON) -m ronin.cli.main status

test:
	@echo "Testing imports..."
	@$(PYTHON) -c "from ronin.config import load_config, get_ronin_home; from ronin.profile import load_profile, Profile; from ronin.scraper import SeekScraper; from ronin.analyzer import JobAnalyzerService; from ronin.applier import SeekApplier; from ronin.applier.base import BaseApplier, get_applier; from ronin.db import SQLiteManager; from ronin.ai import AIService; from ronin.prompts.generator import generate_job_analysis_prompt; from ronin.scheduler import get_schedule_status; print('All imports successful!')"
	@echo "Testing Python file parsing..."
	@$(PYTHON) -c "import ast, os; [ast.parse(open(os.path.join(r,f)).read()) for r,_,fs in os.walk('ronin') for f in fs if f.endswith('.py')]; print('All files parse OK!')"
	@echo "Running lightweight regression scripts..."
	@$(PYTHON) tests/test_archetype_classifier.py
	@$(PYTHON) tests/test_gmail_matching.py

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
