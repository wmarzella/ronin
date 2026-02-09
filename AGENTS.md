# AGENTS.md — Ronin Job Application Automation

## RULE 1 – ABSOLUTE (DO NOT EVER VIOLATE THIS)

You may NOT delete any file or directory unless I explicitly give the exact command **in this session**.

- This includes files you just created (tests, tmp files, scripts, etc.).
- You do not get to decide that something is "safe" to remove.
- If you think something should be removed, stop and ask. You must receive clear written approval **before** any deletion command is even proposed.

Treat "never delete files without permission" as a hard invariant.

---

## IRREVERSIBLE GIT & FILESYSTEM ACTIONS

Absolutely forbidden unless I give the **exact command and explicit approval** in the same message:

- `git reset --hard`
- `git clean -fd`
- `rm -rf`
- Any command that can delete or overwrite code/data

Rules:

1. If you are not 100% sure what a command will delete, do not propose or run it. Ask first.
2. Prefer safe tools: `git status`, `git diff`, `git stash`, copying to backups, etc.
3. After approval, restate the command verbatim, list what it will affect, and wait for confirmation.
4. When a destructive command is run, record in your response:
   - The exact user text authorizing it
   - The command run
   - When you ran it

If that audit trail is missing, then you must act as if the operation never happened.

---

## Project Overview

Ronin is an **AI-powered job application automation platform**. It scrapes job boards, scores listings using AI, automatically selects the best resume for each role, generates tailored cover letters, answers screening questions, and submits applications via browser automation.

**Primary goal:** Automate the entire job search and application pipeline so users can set it up once and have applications submitted on autopilot.

**Target users:** Anyone looking for work. The system is fully configurable -- no hardcoded personal data. Users configure their profile (skills, resumes, preferences) via an interactive TUI wizard.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER CONFIG                              │
│              ~/.ronin/profile.yaml + config.yaml                 │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        SEARCH LAYER                              │
│               Scrape job boards (Seek.com.au)                    │
│           ronin/scraper/base.py → ronin/scraper/seek.py          │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       ANALYSIS LAYER                             │
│         AI scores jobs (0-100) from user's profile               │
│         Picks resume_profile per job, classifies type            │
│             ronin/analyzer/analyzer.py                            │
│             ronin/prompts/generator.py (dynamic prompts)         │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       STORAGE LAYER                              │
│              SQLite database (~/.ronin/data/ronin.db)             │
│           Jobs stored with score, resume_profile, status         │
│                       ronin/db.py                                │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER                           │
│         Chrome automation via Selenium                            │
│         Cover letter generation (AI)                             │
│         Screening question answers (AI)                          │
│         Resume selection from DB (no config lookup)              │
│             ronin/applier/applier.py                              │
│             ronin/applier/cover_letter.py                         │
│             ronin/applier/ai_handler.py                          │
│             ronin/applier/browser.py                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## Repo Layout

```
ronin/
├── AGENTS.md                    # This file
├── README.md                    # User-facing documentation
├── pyproject.toml               # Package config, entry points, deps
├── requirements.txt             # Pinned dependencies
├── Makefile                     # Dev shortcuts
├── .env.example                 # Environment variable template
├── profile.example.yaml         # Profile template for new users
├── config.yaml                  # Runtime config (search params, scraping, etc.)
├── assets/                      # Example template files
│   ├── cv/
│   │   ├── b.txt                # Example resume (growth/honest)
│   │   └── c.txt                # Example resume (contract/aggressive)
│   ├── highlights.txt           # Example condensed highlights
│   ├── philosophy.txt           # Example engineering philosophy
│   └── cover_letter_example.txt # Example cover letter
├── ronin/                       # Main package
│   ├── __init__.py              # Logging setup
│   ├── config.py                # Config loader (supports ~/.ronin/ and project root)
│   ├── profile.py               # Pydantic profile loader/validator
│   ├── db.py                    # SQLite database manager
│   ├── ai.py                    # AI service wrappers (OpenAI, Anthropic)
│   ├── scheduler.py             # Cross-platform OS scheduling
│   ├── cli/                     # CLI commands
│   │   ├── main.py              # Entry point: ronin {setup,search,apply,status,schedule}
│   │   ├── setup.py             # Textual TUI setup wizard (13 screens)
│   │   ├── search.py            # Job search command
│   │   ├── apply.py             # Job application command
│   │   └── status.py            # Status dashboard
│   ├── scraper/                 # Job board scrapers
│   │   ├── base.py              # Abstract BaseScraper
│   │   └── seek.py              # Seek.com.au implementation
│   ├── analyzer/                # Job analysis
│   │   └── analyzer.py          # AI job scoring + resume selection
│   ├── applier/                 # Job application automation
│   │   ├── base.py              # Abstract BaseApplier + factory
│   │   ├── applier.py           # SeekApplier (Seek.com.au)
│   │   ├── browser.py           # ChromeDriver manager (cross-platform)
│   │   ├── cover_letter.py      # AI cover letter generation
│   │   ├── ai_handler.py        # AI screening question answers
│   │   ├── form_applier.py      # Form detection and filling
│   │   ├── forms.py             # Form field models
│   │   ├── html_formatter.py    # HTML to structured form data
│   │   └── validation.py        # Field validation
│   └── prompts/                 # AI prompt templates
│       ├── generator.py         # Dynamic prompt generation from profile
│       ├── job_analysis.py      # Static analysis prompt (legacy fallback)
│       ├── form_fields.py       # Static form prompt (legacy fallback)
│       └── cover_letter.py      # Static cover letter prompt (legacy fallback)
└── scripts/
    └── migrate.py               # Migration script for existing users
```

### User Data Directory (not in repo)

```
~/.ronin/                        # Created by `ronin setup`
├── profile.yaml                 # User's personal profile
├── config.yaml                  # Runtime configuration
├── .env                         # API keys
├── resumes/                     # Resume text files
├── assets/                      # Cover letter examples, highlights
├── data/
│   └── ronin.db                 # SQLite job database
└── logs/
    └── ronin.log
```

---

## Tech Stack

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python 3.11+ | Single language for everything |
| Database | SQLite | Local, zero-config, in `~/.ronin/data/` |
| AI (Analysis) | Anthropic Claude | Job scoring, resume selection, classification |
| AI (Forms) | OpenAI GPT | Screening question answers |
| AI (Cover Letters) | Anthropic Claude | Tailored cover letter generation |
| Browser Automation | Selenium + ChromeDriver | Fills forms, submits applications |
| TUI | Textual | Interactive setup wizard |
| Console | Rich | Status dashboard, progress bars |
| Config Validation | Pydantic v2 | Profile schema validation |
| Scheduling | OS-native | launchd (macOS), Task Scheduler (Windows), cron (Linux) |
| File Locking | filelock | Cross-platform (replaces fcntl) |

---

## Package Manager

- Use **pip** for everything. The project is pip-installable via `pip install .`
- Virtual environments: `python3 -m venv venv`
- Entry point: `ronin` command (defined in pyproject.toml `[project.scripts]`)
- Never use `npm`, `yarn`, `bun`, `uv`, or other package managers for this project.

---

## Key Concepts

### Profile-Driven Architecture

**Zero hardcoded personal data.** All AI prompts are generated dynamically from `~/.ronin/profile.yaml`:

- `ronin/prompts/generator.py` builds prompts from profile fields
- `ronin/profile.py` loads and validates the profile with Pydantic
- Legacy static prompts in `ronin/prompts/` exist only as fallbacks

### Resume Auto-Selection

Resume selection happens at **search time**, not apply time:

1. During `ronin search`, the AI analyzer receives the user's resume profiles and their `use_when` rules
2. The AI picks the best `resume_profile` name for each job
3. `resume_profile` is stored in the SQLite `jobs` table
4. During `ronin apply`, the applier reads `resume_profile` directly from the DB record -- no config lookup needed

### Pluggable Job Boards

Job boards are abstracted behind two interfaces:

- `ronin/scraper/base.py` -- `BaseScraper` with `get_job_previews()` and `get_job_details()`
- `ronin/applier/base.py` -- `BaseApplier` with `apply_to_job()`, `login()`, `cleanup()`
- Factory: `get_applier("seek")` returns a `SeekApplier` instance
- Currently only Seek.com.au is implemented

### Config Resolution Order

Both `config.py` and `profile.py` check locations in order:

1. `~/.ronin/` (or `RONIN_HOME` env var) -- preferred
2. Project root -- fallback for development
3. If neither exists, raise `FileNotFoundError` directing user to `ronin setup`

---

## CLI Commands

```
ronin setup [--step STEP]              # Interactive TUI setup wizard
ronin search                           # Scrape + analyze + store jobs
ronin apply                            # Apply to discovered jobs via Chrome
ronin status                           # Show dashboard (config, DB stats, schedule)
ronin schedule install [--interval N]  # Install OS-native scheduled search
ronin schedule uninstall               # Remove scheduled search
ronin schedule status                  # Check if schedule is active
ronin --version                        # Show version
```

---

## Database Schema

SQLite database at `~/.ronin/data/ronin.db`. Key tables:

### `companies`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Company name |
| domain | TEXT | Company domain |

### `jobs`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | Auto-increment |
| job_id | TEXT UNIQUE | Job board's ID |
| title | TEXT | Job title |
| description | TEXT | Full description |
| score | INTEGER | AI score 0-100 |
| tech_stack | TEXT | Primary tech stack |
| recommendation | TEXT | AI recommendation |
| job_classification | TEXT | CASH_FLOW or LONG_TERM |
| **resume_profile** | TEXT | **AI-selected resume profile name** |
| status | TEXT | DISCOVERED, APPLIED, STALE, APP_ERROR |
| url | TEXT | Job listing URL |
| source | TEXT | e.g. "seek" |
| quick_apply | INTEGER | 1 if quick apply available |
| company_id | INTEGER FK | References companies.id |

---

## Environment Variables

Stored in `~/.ronin/.env` (created by `ronin setup`):

```bash
# AI Providers (at least one required)
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-...

# Notifications (optional)
SLACK_WEBHOOK_URL=

# Browser (optional, auto-detected if not set)
# CHROME_BINARY_PATH=/path/to/chrome
```

---

## Code Style

- Formatter: `black` (line-length 88)
- Linter: `flake8` (line-length 88, extends E203,W503)
- Type hints: Required for all function signatures
- Docstrings: Google style for public functions
- Imports: `isort` (profile: black)
- Logging: `loguru` (not stdlib `logging`)
- Console output: `rich` for user-facing displays
- Prefer `const`-style: use immutable data structures where practical
- Prefer named exports

---

## Development

### Setup

```bash
git clone https://github.com/automationchad/ronin.git
cd ronin
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### Commands

```bash
make help       # Show all targets
make test       # Test all imports
make format     # Black formatting
make lint       # Flake8 linting
make check      # Format + lint
make search     # Run job search
make apply      # Run job applications
make status     # Show status dashboard
make setup      # Run setup wizard
```

### Before Committing

```bash
make check      # Format + lint
make test       # Verify imports
```

---

## Adding a New Job Board

1. Create `ronin/scraper/{board}.py` implementing `BaseScraper`:
   ```python
   class NewBoardScraper(BaseScraper):
       def get_job_previews(self) -> List[Dict[str, Any]]:
           ...
       def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
           ...
   ```

2. Create applier logic in `ronin/applier/{board}_applier.py` implementing `BaseApplier`:
   ```python
   class NewBoardApplier(BaseApplier):
       @property
       def board_name(self) -> str:
           return "newboard"
       def apply_to_job(self, job_id, ...) -> str:
           ...
       def login(self) -> bool:
           ...
       def cleanup(self) -> None:
           ...
   ```

3. Register in `ronin/applier/base.py` `get_applier()` factory

4. Add board config section in `config.yaml`:
   ```yaml
   boards:
     newboard:
       enabled: true
   ```

5. Add any API keys to `.env.example`

---

## Code Editing Discipline

- Do **not** run scripts that bulk-modify code (codemods, invented one-off scripts, giant `sed`/regex refactors).
- Large mechanical changes: break into smaller, explicit edits and review diffs.
- Subtle/complex changes: edit by hand, file-by-file, with careful reasoning.
- **Never modify `~/.ronin/` contents directly** -- that's user data. Only the setup wizard and CLI commands should write there.

---

## Backwards Compatibility & File Sprawl

We optimize for a clean architecture now, not backwards compatibility.

- No "compat shims" or "v2" file clones.
- When changing behavior, migrate callers and remove old code (with permission).
- New files are only for genuinely new domains that don't fit existing modules.
- The bar for adding files is high.
- Legacy static prompts in `ronin/prompts/` are kept only as fallbacks. New prompt logic goes in `generator.py`.

---

## Console Output

- Use **loguru** for all logging (not stdlib `logging`)
- Use **Rich** for user-facing console output (tables, progress bars, panels)
- Log file: `~/.ronin/logs/ronin.log` (DEBUG level, rotated at 10MB)
- Console: WARNING and above (routed through Rich)
- Production runs (scheduled search) log to `~/.ronin/logs/launchd_search.log`

---

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **Run quality gates** (if code changed):
   ```bash
   make check      # Format + lint
   make test       # Verify imports
   ```
2. **Verify all Python files parse**:
   ```bash
   python3 -c "import ast, os; [ast.parse(open(f).read()) for root, _, files in os.walk('ronin') for f in files if f.endswith('.py')]"
   ```
3. **PUSH TO REMOTE** -- this is MANDATORY:
   ```bash
   git add -A
   git commit -m "descriptive message"
   git push origin main
   git status  # MUST show "up to date with origin"
   ```
4. **Verify** -- all changes committed AND pushed
5. **Hand off** -- provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing -- that leaves work stranded locally
- NEVER say "ready to push when you are" -- YOU must push
- If push fails, resolve and retry until it succeeds

---

## Important File Relationships

Understanding these dependencies prevents breaking changes:

```
profile.yaml ──→ ronin/profile.py ──→ ronin/prompts/generator.py
                                   ──→ ronin/analyzer/analyzer.py
                                   ──→ ronin/applier/cover_letter.py
                                   ──→ ronin/applier/ai_handler.py
                                   ──→ ronin/applier/applier.py

config.yaml  ──→ ronin/config.py  ──→ ronin/scraper/seek.py
                                   ──→ ronin/applier/browser.py
                                   ──→ ronin/cli/search.py
                                   ──→ ronin/cli/apply.py

ronin/cli/setup.py ──writes──→ ~/.ronin/profile.yaml
                    ──writes──→ ~/.ronin/config.yaml
                    ──writes──→ ~/.ronin/.env
                    ──writes──→ ~/.ronin/resumes/*.txt
                    ──calls──→  ronin/scheduler.py (if schedule enabled)

ronin/db.py (jobs.resume_profile) ──set by──→ analyzer.py (search time)
                                  ──read by──→ applier.py (apply time)
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-04 | -- | Initial AGENTS.md (Market Intelligence System) |
| 2.0 | 2026-02-09 | -- | Rewritten for Ronin job automation platform |
