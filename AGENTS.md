# AGENTS.md — Market Intelligence System

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

Market Intelligence System is a **signal aggregation and alerting system** designed to surface contract opportunities before they appear on job boards. The system monitors leadership changes, funding events, hiring patterns, and government tenders to generate actionable outreach triggers for a data engineering contractor targeting midmarket and enterprise clients.

**Primary goal:** Eliminate reactive job applications. Become aware of opportunities 2-8 weeks before they reach recruiters or job boards.

### Reference Documents

- `docs/prd-backend.md` — Backend PRD: data model, ingestion specs, scoring logic, trigger rules
- `docs/prd-ui.md` — UI PRD: design system, pages, components, API contract

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER                          │
├─────────────┬─────────────┬──────────────┬─────────────────────┤
│  LinkedIn   │ Crunchbase  │   Adzuna     │     AusTender       │
│  (Apollo)   │    API      │    API       │       API           │
└──────┬──────┴──────┬──────┴───────┬──────┴──────────┬──────────┘
       │             │              │                 │
       ▼             ▼              ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RAW STORAGE (Postgres)                     │
│                   signals table (append-only)                   │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TRANSFORM LAYER                           │
│         - Keyword filtering                                     │
│         - Score calculation with decay                          │
│         - Trigger rule evaluation                               │
└─────────────────────────────────────┬───────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ALERT LAYER                              │
│              - Daily digest (email/Slack)                       │
│              - Action queue generation                          │
└─────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                         WEB UI                                  │
│           Next.js 14 + Tailwind + Radix UI                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Repo Layout

```
market-intel/
├── README.md
├── AGENTS.md
├── docs/
│   ├── prd-backend.md          # Backend PRD (data model, ingestion, scoring)
│   └── prd-ui.md               # UI PRD (design system, pages, components)
├── packages/
│   ├── db/                     # Database schema, migrations, seeds
│   │   ├── schema.sql          # Full DDL
│   │   ├── migrations/         # Incremental migrations
│   │   └── seeds/              # Sample data for development
│   ├── ingestion/              # Python ingestion scripts
│   │   ├── src/
│   │   │   ├── sources/        # Per-source modules
│   │   │   │   ├── crunchbase.py
│   │   │   │   ├── adzuna.py
│   │   │   │   ├── austender.py
│   │   │   │   └── apollo.py
│   │   │   ├── transform.py    # Scoring, decay, trigger rules
│   │   │   └── alerts.py       # Digest generation, delivery
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── web/                    # Next.js web application
│       ├── src/
│       │   ├── app/            # App Router pages
│       │   ├── components/     # UI components
│       │   │   ├── ui/         # Base components (Button, Input, Badge)
│       │   │   ├── layout/     # Sidebar, Header, CommandPalette
│       │   │   ├── tables/     # CompanyTable, SignalTable, etc.
│       │   │   └── modals/     # CompanyModal, OutcomeModal
│       │   └── lib/            # API client, hooks, utils
│       ├── package.json
│       └── tailwind.config.ts
├── scripts/                    # Operational scripts
│   ├── setup-db.sh
│   └── run-ingestion.sh
├── .beads/                     # Issue tracking (bd)
└── .env.example
```

---

## Tech Stack

### Backend (Ingestion & Transform)

| Component | Technology | Notes |
|-----------|------------|-------|
| Language | Python 3.11+ | Use `uv` for package management |
| Database | PostgreSQL 15+ | JSONB for raw_payload, extracted_fields |
| Scheduler | Cron or Dagster/Prefect | Start with cron, migrate if complexity grows |
| HTTP | `httpx` | Async HTTP client |
| Scraping | `playwright` | For sources without APIs |
| Alerting | SendGrid or Slack webhook | Email/Slack digest delivery |

### Frontend (Web UI)

| Component | Technology | Notes |
|-----------|------------|-------|
| Framework | Next.js 14 (App Router) | SSR for initial load |
| Styling | Tailwind CSS | Custom config per design system |
| Components | Radix UI | Accessible, unstyled primitives |
| State | Zustand | Lightweight state management |
| Data fetching | TanStack Query | Caching, background refresh |
| Tables | TanStack Table | Headless, sortable, filterable |
| Charts | Recharts | Minimal, customizable |
| Forms | React Hook Form + Zod | Validation |
| Icons | Lucide | Consistent iconography |
| Command palette | cmdk | Linear-style command menu |
| Keyboard | react-hotkeys-hook | Global shortcuts |

### Infrastructure

| Component | Technology | Notes |
|-----------|------------|-------|
| Hosting (Web) | Vercel or Railway | Simple deployment |
| Hosting (DB) | Railway or Supabase | Managed Postgres |
| Secrets | Environment variables or Doppler | Never hardcode API keys |

---

## Package Managers & Tooling

### JavaScript/TypeScript

- Use **bun** for everything JS/TS in `packages/web/`.
- ❌ Never use `npm`, `yarn`, or `pnpm`.
- Lockfiles: only `bun.lock`. Do not introduce any other lockfile.

### Python

- Use **uv** for everything Python in `packages/ingestion/`.
- ❌ Never use `pip` directly (use `uv pip` if needed).
- Virtual environments: `uv venv` creates `.venv/`.

---

## Database Conventions

### Schema

- All tables use `UUID` primary keys with `gen_random_uuid()`.
- Timestamps: `created_at`, `updated_at` with `DEFAULT NOW()`.
- Soft deletes: Not used. Hard delete with explicit permission only.
- JSONB columns: `raw_payload` (immutable), `extracted_fields` (normalized).

### Migrations

- Use numbered files: `001_initial.sql`, `002_add_contacts.sql`.
- Each migration is idempotent where possible.
- Never modify existing migrations after they've been applied to production.

### Naming

- Tables: lowercase plural (`companies`, `signals`, `actions`).
- Columns: lowercase snake_case (`signal_type`, `company_id`).
- Indexes: `idx_{table}_{column}` (e.g., `idx_signals_company`).
- Foreign keys: `{table}_{column}_fkey`.
- Enums: singular (`signal_type`, `company_type`).

---

## Code Style

### Python (packages/ingestion/)

- Formatter: `ruff format`
- Linter: `ruff check`
- Type hints: Required for all function signatures
- Docstrings: Google style for public functions
- Imports: `ruff` handles sorting

### TypeScript (packages/web/)

- Formatter: `prettier` via `bun run format`
- Linter: `eslint` via `bun run lint`
- Strict mode: `"strict": true` in tsconfig
- Prefer `const` over `let`
- Prefer named exports over default exports

---

## Data Model Quick Reference

**Causal chain:** Signal → Action → Outcome

| Table | Purpose |
|-------|---------|
| `companies` | Anchor entity (targets, channel partners, government agencies) |
| `contacts` | People at companies |
| `signals` | Append-only event log (leadership, funding, tenders, jobs) |
| `signal_weights` | Configurable weights per signal type |
| `company_scores` | Daily derived scores with decay |
| `actions` | Triggered outreach actions |
| `outcomes` | Results of actions (meeting, proposal, contract) |

See `docs/prd-backend.md` for full schema DDL.

---

## Ingestion Development

### Adding a New Source

1. Create `packages/ingestion/src/sources/{source_name}.py`
2. Implement required interface:
   ```python
   async def fetch_signals(companies: list[Company]) -> list[Signal]:
       """Fetch signals for the given companies."""
       ...
   ```
3. Add to scheduler in `packages/ingestion/src/main.py`
4. Add API key to `.env.example`
5. Document rate limits and access method in PRD

### Testing Ingestion

```bash
cd packages/ingestion
uv run pytest tests/ -v
uv run python -m src.sources.crunchbase --dry-run  # Test single source
```

### Running Ingestion Locally

```bash
cd packages/ingestion
cp .env.example .env  # Fill in API keys
uv run python -m src.main
```

---

## Web Development

### Setup

```bash
cd packages/web
bun install
cp .env.example .env.local  # Fill in DATABASE_URL
bun run dev
```

### Commands

```bash
bun run dev       # Dev server (http://localhost:3000)
bun run build     # Production build
bun run lint      # ESLint
bun run format    # Prettier
bun run test      # Vitest
```

### Component Development

- Base components in `src/components/ui/` (Button, Input, Badge, etc.)
- Compose into feature components (CompanyTable, SignalCard, etc.)
- Use Radix primitives for accessibility
- Follow design system in `docs/prd-ui.md`

### API Routes

All API routes in `src/app/api/v1/`:

```
GET    /api/v1/companies
GET    /api/v1/companies/:id
POST   /api/v1/companies
PATCH  /api/v1/companies/:id
DELETE /api/v1/companies/:id

GET    /api/v1/signals
GET    /api/v1/actions
PATCH  /api/v1/actions/:id
POST   /api/v1/actions/:id/outcome

GET    /api/v1/dashboard/summary
GET    /api/v1/search
```

---

## Environment Variables

### Required (Backend)

```bash
DATABASE_URL=postgresql://user:pass@host:5432/market_intel

# Ingestion sources
CRUNCHBASE_API_KEY=
APOLLO_API_KEY=
ADZUNA_APP_ID=
ADZUNA_API_KEY=

# Alerting
SENDGRID_API_KEY=
SLACK_WEBHOOK_URL=
```

### Required (Frontend)

```bash
DATABASE_URL=postgresql://user:pass@host:5432/market_intel
# Or use connection pooler for serverless:
# DATABASE_URL=postgresql://user:pass@pooler.host:6543/market_intel
```

---

## Quality Gates

### Before Committing

```bash
# Python
cd packages/ingestion
uv run ruff check .
uv run ruff format --check .
uv run pytest

# TypeScript
cd packages/web
bun run lint
bun run build
bun run test
```

### CI Pipeline

1. Lint (ruff, eslint)
2. Type check (pyright, tsc)
3. Unit tests (pytest, vitest)
4. Build (next build)
5. Schema validation (compare against expected DDL)

---

## Deployment

### Database

1. Provision PostgreSQL 15+ instance
2. Run `packages/db/schema.sql`
3. Run any pending migrations in order
4. Seed with `packages/db/seeds/companies.sql` (optional)

### Ingestion

1. Deploy to server with cron or container with scheduler
2. Set environment variables
3. Schedule: daily at 06:00 UTC (before workday in AU)

### Web

1. Connect Vercel/Railway to repo
2. Set root directory to `packages/web`
3. Set environment variables
4. Deploy on push to main

---

## Operational Runbooks

### Manual Signal Insertion

```sql
INSERT INTO signals (company_id, signal_type, signal_date, source, raw_payload, extracted_fields)
VALUES (
  'uuid-here',
  'leadership_change',
  CURRENT_DATE,
  'manual',
  '{"note": "Saw on LinkedIn"}',
  '{"person_name": "Jane Smith", "new_role": "CDO"}'
);
```

### Force Score Recalculation

```bash
cd packages/ingestion
uv run python -m src.transform --recalculate-scores
```

### Check Ingestion Health

```sql
SELECT source, signal_type, COUNT(*), MAX(ingested_at) as last_ingested
FROM signals
WHERE ingested_at > NOW() - INTERVAL '7 days'
GROUP BY source, signal_type
ORDER BY last_ingested DESC;
```

---

## Code Editing Discipline

- Do **not** run scripts that bulk-modify code (codemods, invented one-off scripts, giant `sed`/regex refactors).
- Large mechanical changes: break into smaller, explicit edits and review diffs.
- Subtle/complex changes: edit by hand, file-by-file, with careful reasoning.

---

## Backwards Compatibility & File Sprawl

We optimize for a clean architecture now, not backwards compatibility.

- No "compat shims" or "v2" file clones.
- When changing behavior, migrate callers and remove old code (with permission).
- New files are only for genuinely new domains that don't fit existing modules.
- The bar for adding files is high.

---

## Console Output

- Prefer **structured, minimal logs** (avoid spammy debug output).
- Use Python's `logging` module with appropriate levels.
- Production: INFO and above. Development: DEBUG available.
- Format: `%(asctime)s %(levelname)s %(name)s: %(message)s`

---

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** — Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) — Tests, linters, builds
3. **Update issue status** — Close finished work, update in-progress items
4. **PUSH TO REMOTE** — This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** — Clear stashes, prune remote branches
6. **Verify** — All changes committed AND pushed
7. **Hand off** — Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing — that leaves work stranded locally
- NEVER say "ready to push when you are" — YOU must push
- If push fails, resolve and retry until it succeeds

---

## Tooling Assumptions (Recommended)

This section is a **developer toolbelt** reference.

### Shell & Terminal UX
- **zsh** + **oh-my-zsh** + **powerlevel10k**
- **lsd** — Modern ls
- **fzf** — Fuzzy finder
- **zoxide** — Better cd
- **direnv** — Directory-specific env vars

### Languages & Package Managers
- **bun** — JS/TS runtime + package manager
- **uv** — Fast Python tooling

### Dev Tools
- **ripgrep** (`rg`) — Fast search
- **lazygit** — Git TUI
- **bat** — Better cat

### Database
- **pgcli** — Better psql with autocomplete
- **dbmate** — Database migrations (alternative to raw SQL files)

---

## Useful Queries

### Top 10 Companies by Score

```sql
SELECT c.name, cs.weighted_score, cs.latest_signal_type, cs.days_since_last_signal
FROM company_scores cs
JOIN companies c ON cs.company_id = c.company_id
WHERE cs.score_date = CURRENT_DATE
ORDER BY cs.weighted_score DESC
LIMIT 10;
```

### Full Funnel Trace

```sql
SELECT
  s.signal_type,
  s.signal_date,
  c.name AS company_name,
  a.trigger_rule,
  o.outcome_type,
  o.value
FROM outcomes o
JOIN actions a ON o.action_id = a.action_id
LEFT JOIN signals s ON a.signal_id = s.signal_id
JOIN companies c ON a.company_id = c.company_id
ORDER BY o.outcome_date DESC;
```

### Signal Effectiveness

```sql
SELECT
  s.signal_type,
  COUNT(DISTINCT s.signal_id) AS total_signals,
  COUNT(DISTINCT o.outcome_id) FILTER (WHERE o.outcome_type = 'meeting') AS meetings,
  COUNT(DISTINCT o.outcome_id) FILTER (WHERE o.outcome_type = 'contract_won') AS contracts,
  SUM(o.value) FILTER (WHERE o.outcome_type = 'contract_won') AS total_value
FROM signals s
LEFT JOIN actions a ON s.signal_id = a.signal_id
LEFT JOIN outcomes o ON a.action_id = o.action_id
GROUP BY s.signal_type
ORDER BY contracts DESC;
```

---

## MCP Agent Mail — Multi-Agent Coordination

Agent Mail is available as an MCP server for coordinating work across agents.

### CRITICAL: How Agents Access Agent Mail

**Coding agents (Claude Code, Codex, Gemini CLI) access Agent Mail NATIVELY via MCP tools.**

- You do NOT need to implement HTTP wrappers, client classes, or JSON-RPC handling
- MCP tools are available directly in your environment (e.g., `macro_start_session`, `send_message`, `fetch_inbox`)
- If MCP tools aren't available, flag it to the user — they may need to start the Agent Mail server

What Agent Mail gives:
- Identities, inbox/outbox, searchable threads.
- Advisory file reservations (leases) to avoid agents clobbering each other.
- Persistent artifacts in git (human-auditable).

Core patterns:

1. **Same repo**
   - Register identity:
     - `ensure_project` then `register_agent` with the repo's absolute path as `project_key`.
   - Reserve files before editing:
     - `file_reservation_paths(project_key, agent_name, ["src/**"], ttl_seconds=3600, exclusive=true)`.
   - Communicate:
     - `send_message(..., thread_id="FEAT-123")`.
     - `fetch_inbox`, then `acknowledge_message`.
   - Fast reads:
     - `resource://inbox/{Agent}?project=<abs-path>&limit=20`.
     - `resource://thread/{id}?project=<abs-path>&include_bodies=true`.

2. **Macros vs granular:**
   - Prefer macros when speed is more important than fine-grained control:
     - `macro_start_session`, `macro_prepare_thread`, `macro_file_reservation_cycle`, `macro_contact_handshake`.
   - Use granular tools when you need explicit behavior.

Common pitfalls:
- "from_agent not registered" → call `register_agent` with correct `project_key`.
- `FILE_RESERVATION_CONFLICT` → adjust patterns, wait for expiry, or use non-exclusive reservation.

---

## Issue Tracking with bd (beads)

All issue tracking goes through **bd**. No other TODO systems.

Key invariants:

- `.beads/` is authoritative state and **must always be committed** with code changes.
- Do not edit `.beads/*.jsonl` directly; only via `bd`.

### Basics

Check ready work:

```bash
bd ready --json
```

Create issues:

```bash
bd create "Issue title" -t bug|feature|task -p 0-4 --json
bd create "Issue title" -p 1 --deps discovered-from:bd-123 --json
```

Update:

```bash
bd update bd-42 --status in_progress --json
bd update bd-42 --priority 1 --json
```

Complete:

```bash
bd close bd-42 --reason "Completed" --json
```

Types:

- `bug`, `feature`, `task`, `epic`, `chore`

Priorities:

- `0` critical (security, data loss, broken builds)
- `1` high
- `2` medium (default)
- `3` low
- `4` backlog

Agent workflow:

1. `bd ready` to find unblocked work.
2. Claim: `bd update <id> --status in_progress`.
3. Implement + test.
4. If you discover new work, create a new bead with `discovered-from:<parent-id>`.
5. Close when done.
6. Commit `.beads/` in the same commit as code changes.

Auto-sync:

- bd exports to `.beads/issues.jsonl` after changes (debounced).
- It imports from JSONL when newer (e.g. after `git pull`).

Never:

- Use markdown TODO lists.
- Use other trackers.
- Duplicate tracking.

---

### Using bv as an AI sidecar

bv is a graph-aware triage engine for Beads projects (.beads/beads.jsonl). Instead of parsing JSONL or hallucinating graph traversal, use robot flags for deterministic, dependency-aware outputs with precomputed metrics (PageRank, betweenness, critical path, cycles, HITS, eigenvector, k-core).

**Scope boundary:** bv handles *what to work on* (triage, priority, planning). For agent-to-agent coordination (messaging, work claiming, file reservations), use MCP Agent Mail.

**⚠️ CRITICAL: Use ONLY `--robot-*` flags. Bare `bv` launches an interactive TUI that blocks your session.**

#### The Workflow: Start With Triage

**`bv --robot-triage` is your single entry point.** It returns everything you need in one call:
- `quick_ref`: at-a-glance counts + top 3 picks
- `recommendations`: ranked actionable items with scores, reasons, unblock info
- `quick_wins`: low-effort high-impact items
- `blockers_to_clear`: items that unblock the most downstream work
- `project_health`: status/type/priority distributions, graph metrics
- `commands`: copy-paste shell commands for next steps

```bash
bv --robot-triage        # THE MEGA-COMMAND: start here
bv --robot-next          # Minimal: just the single top pick + claim command
```

#### Other bv Commands

**Planning:**
| Command | Returns |
|---------|---------|
| `--robot-plan` | Parallel execution tracks with `unblocks` lists |
| `--robot-priority` | Priority misalignment detection with confidence |

**Graph Analysis:**
| Command | Returns |
|---------|---------|
| `--robot-insights` | Full metrics: PageRank, betweenness, HITS, eigenvector, critical path, cycles |
| `--robot-label-health` | Per-label health: `health_level`, `velocity_score`, `staleness`, `blocked_count` |
| `--robot-label-flow` | Cross-label dependency: `flow_matrix`, `dependencies`, `bottleneck_labels` |

**History & Change Tracking:**
| Command | Returns |
|---------|---------|
| `--robot-history` | Bead-to-commit correlations |
| `--robot-diff --diff-since <ref>` | Changes since ref: new/closed/modified issues |

**Other Commands:**
| Command | Returns |
|---------|---------|
| `--robot-burndown <sprint>` | Sprint burndown, scope changes, at-risk items |
| `--robot-forecast <id\|all>` | ETA predictions with dependency-aware scheduling |
| `--robot-alerts` | Stale issues, blocking cascades, priority mismatches |
| `--robot-suggest` | Hygiene: duplicates, missing deps, label suggestions |
| `--robot-graph [--graph-format=json\|dot\|mermaid]` | Dependency graph export |

#### Scoping & Filtering

```bash
bv --robot-plan --label backend              # Scope to label's subgraph
bv --robot-insights --as-of HEAD~30          # Historical point-in-time
bv --recipe actionable --robot-plan          # Pre-filter: ready to work
bv --recipe high-impact --robot-triage       # Pre-filter: top PageRank scores
```

#### jq Quick Reference

```bash
bv --robot-triage | jq '.quick_ref'                        # At-a-glance summary
bv --robot-triage | jq '.recommendations[0]'               # Top recommendation
bv --robot-plan | jq '.plan.summary.highest_impact'        # Best unblock target
bv --robot-insights | jq '.Cycles'                         # Circular deps (must fix!)
```

Use bv instead of parsing beads.jsonl—it computes PageRank, critical paths, cycles, and parallel tracks deterministically.

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-04 | — | Initial AGENTS.md |
