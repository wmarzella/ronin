#!/usr/bin/env python3
"""Migrate personal data from main branch to ~/.ronin/ structure.

This script reads William Marzella's personal data from the main branch
git history and creates the full ~/.ronin/ directory structure with a
properly populated profile.yaml, config.yaml, .env, and all asset files.

Usage:
    python scripts/migrate.py [--dry-run] [--ronin-home PATH]

This is a ONE-TIME migration script. Run it once after checking out
the feat/configurable branch to set up your personal ~/.ronin/ config.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def get_ronin_home(override: str = None) -> Path:
    """Get the target ronin home directory."""
    if override:
        return Path(override).expanduser()
    return Path(os.environ.get("RONIN_HOME", Path.home() / ".ronin"))


def git_show(ref: str) -> str:
    """Read a file from a git ref."""
    try:
        result = subprocess.run(
            ["git", "show", ref],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def extract_env_vars() -> dict:
    """Extract API keys from the local .env file if it exists."""
    env_path = Path(".env")
    env_vars = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def build_profile() -> dict:
    """Build the profile.yaml content from known personal data."""
    return {
        # Personal Information
        "personal": {
            "name": "William Marzella",
            "email": "williampmarzella@gmail.com",
            "phone": "0413414869",
            "location": "Mont Albert North, VIC, Australia",
        },
        # Work Rights
        "work_rights": {
            "citizenship": "Australian citizen",
            "visa_status": "Full working rights",
            "has_drivers_license": True,
            "security_clearances": [],
            "willing_to_obtain_clearance": True,
            "willing_to_relocate": False,
            "willing_to_travel": True,
            "police_check": "Willing to undergo",
            "notice_period": "Immediately",
        },
        # Professional Profile
        "professional": {
            "title": "Senior Data Engineer",
            "years_experience": 7,
            "salary_min": 150000,
            "salary_max": 200000,
            "salary_currency": "AUD",
            "skills": {
                "cloud": ["AWS", "Azure", "Databricks", "Snowflake"],
                "languages": ["Python", "PySpark", "SQL"],
                "infrastructure": [
                    "Terraform",
                    "Docker",
                    "Kubernetes",
                    "CI/CD (GitHub Actions)",
                ],
                "data": [
                    "ETL/ELT pipelines",
                    "Data modelling",
                    "Lakehouse architecture",
                    "Delta Lake",
                    "Medallion architecture (Bronze/Silver/Gold)",
                    "Kimball dimensional modelling",
                    "SCD Type 2",
                    "dbt",
                    "Airflow",
                    "Kafka",
                ],
                "frameworks": [],
                "tools": [
                    "dbt",
                    "Airflow",
                    "EMR",
                    "ECS/EKS",
                    "Lambda",
                    "Step Functions",
                    "CloudWatch",
                    "Prometheus",
                    "Grafana",
                    "Tableau",
                    "Power BI",
                ],
                "compliance": [
                    "HIPAA",
                    "PCI DSS",
                    "Data governance frameworks",
                    "APRA regulatory compliance",
                ],
            },
            "preferences": {
                "high_value_signals": [
                    "Distributed engines: PySpark, Trino, Flink",
                    "Cloud platforms: Databricks, AWS, Snowflake",
                    "Modern orchestration: Mage, Prefect, Dagster",
                    "Architecture decision-making authority",
                    "Cost optimisation / FinOps responsibilities",
                    "Platform-specific certifications valued",
                    "Cross-functional collaboration or executive interaction",
                    "Legacy-to-lakehouse migration projects",
                ],
                "red_flags": [
                    "Legacy Microsoft stack: SSIS, SSAS, Azure Data Factory",
                    "Vague or buzzword-heavy descriptions",
                    "Mishmashed tech stacks suggesting no clear direction",
                    "Signs of understaffing ('wear many hats', 'flexible role')",
                    "Purely compliance or reporting focused",
                    "Early-stage startup hype without substance",
                    "SSIS + Azure Data Factory (failing cloud migration)",
                    "Consultancy-driven transformation (no-code tools over programming)",
                    "Multiple orchestration tools from different eras",
                    "Lift and shift cloud migration without modernisation",
                ],
                "preferred_work_types": ["contract", "full-time"],
                "preferred_arrangements": ["remote", "hybrid"],
            },
        },
        # Resume Profiles
        "resumes": [
            {
                "name": "growth_honest",
                "file": "b.txt",
                "seek_resume_id": "832e3e14-4cc6-4d12-a5e1-27f0d3a1a8cb",
                "use_when": {
                    "job_types": ["permanent", "full-time"],
                    "description": "Honest/growth resume for permanent roles where authenticity and willingness to learn matter more than inflated achievements",
                },
            },
            {
                "name": "contract_aggressive",
                "file": "c.txt",
                "seek_resume_id": "aa9db8fe-e608-4193-aef7-13cc130da44b",
                "use_when": {
                    "job_types": ["contract", "consulting"],
                    "description": "Aggressive/impressive resume for contract roles where demonstrated results, cost savings metrics, and enterprise-scale experience matter",
                },
            },
        ],
        # Cover Letter Configuration
        "cover_letter": {
            "tone": "casual professional",
            "max_words": 150,
            "spelling": "Australian English",
            "example_file": "cover_letter_example.txt",
            "highlights_file": "highlights.txt",
            "anti_slop_rules": [
                "Never use: 'passionate about', 'leverage my skills', 'drive value'",
                "No AI vocabulary: 'Additionally', 'delve', 'enhance', 'fostering', 'interplay', 'intricate', 'landscape', 'tapestry', 'underscore'",
                "No em dashes",
                "No dramatic reframes: 'That's not failure. That's data.'",
                "No inflated significance: 'stands as', 'testament to', 'pivotal', 'crucial moment'",
                "No superficial -ing phrases: 'highlighting...', 'ensuring...', 'showcasing...'",
                "No promotional language: 'boasts', 'vibrant', 'rich', 'profound', 'renowned'",
                "No negative parallelisms: 'It's not just X, it's Y'",
                "No rule of three: 'innovation, inspiration, and insights'",
                "No hollow phrases: 'leverage my skills', 'drive value', 'passionate about'",
            ],
            "contract_framing": "Problem-first. What's broken? You've seen it before. Emphasise speed to impact. You ship working solutions, not roadmaps. Show you can operate independently. Pragmatic, not precious. Hint at knowledge transfer.",
            "fulltime_framing": "Future-oriented. Where are they going? You want to help get there. Show you think about systems, not just tasks. Mention collaboration, team growth. Balance: not just a pair of hands, but not above the work either.",
        },
        # AI Provider Configuration
        "ai": {
            "analysis_provider": "anthropic",
            "analysis_model": "claude-sonnet-4-20250514",
            "cover_letter_provider": "anthropic",
            "cover_letter_model": "claude-sonnet-4-20250514",
            "form_filling_provider": "openai",
            "form_filling_model": "gpt-4o",
        },
    }


def build_config() -> dict:
    """Build the config.yaml from the original main branch config."""
    return {
        "search": {
            "keywords": [
                '"Data engineer"-or-"data engineers"',
                '"Senior data engineer"-or-"Senior data engineers"',
                '"Lead data engineer"-or-"Lead data engineers"',
                '"platform engineer"-or-"platform engineers"',
                '"data consultant"-or-"data consultants"',
                '"data architect"-or-"data architects"',
            ],
            "location": "All-Australia",
            "date_range": 2,
            "salary": {"min": 0, "max": 400000},
        },
        "application": {
            "salary_min": 150000,
            "salary_max": 200000,
            "batch_limit": 100,
        },
        "scraping": {
            "max_jobs": 0,
            "delay_seconds": 1,
            "timeout_seconds": 10,
            "quick_apply_only": True,
        },
        "analysis": {"min_score": 0},
        "proxy": {"enabled": False, "http_url": "", "https_url": ""},
        "notifications": {
            "slack": {
                "webhook_url": "",
                "notify_on_error": True,
                "notify_on_warning": True,
                "notify_on_success": False,
            }
        },
        "boards": {"seek": {"enabled": True}},
        "browser": {"mode": "system", "chrome_path": ""},
        "schedule": {"enabled": False, "interval_hours": 2},
        "timeouts": {
            "http_request": 30,
            "page_load": 45,
            "element_wait": 10,
            "implicit_wait": 10,
        },
        "retry": {
            "max_attempts": 3,
            "backoff_multiplier": 2.0,
            "jitter": True,
        },
    }


def build_env(env_vars: dict) -> str:
    """Build the .env file content."""
    lines = [
        "# Ronin - Environment Variables",
        "# Migrated from project .env",
        "",
        "# AI Providers",
        f"ANTHROPIC_API_KEY={env_vars.get('ANTHROPIC_API_KEY', 'sk-ant-api03-your-key-here')}",
        f"OPENAI_API_KEY={env_vars.get('OPENAI_API_KEY', 'sk-your-key-here')}",
        "",
        "# Google (for Seek login)",
        f"GOOGLE_EMAIL={env_vars.get('GOOGLE_EMAIL', '')}",
        f"GOOGLE_PASSWORD={env_vars.get('GOOGLE_PASSWORD', '')}",
        "",
        "# Notifications",
        f"SLACK_WEBHOOK_URL={env_vars.get('SLACK_WEBHOOK_URL', '')}",
        "",
        "# Browser (auto-detected if not set)",
        f"# CHROME_BINARY_PATH={env_vars.get('CHROME_BINARY_PATH', '')}",
    ]

    # Include any other env vars not already handled
    handled = {
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_EMAIL",
        "GOOGLE_PASSWORD",
        "SLACK_WEBHOOK_URL",
        "CHROME_BINARY_PATH",
    }
    extras = {k: v for k, v in env_vars.items() if k not in handled}
    if extras:
        lines.append("")
        lines.append("# Other (migrated from original .env)")
        for k, v in extras.items():
            lines.append(f"{k}={v}")

    return "\n".join(lines) + "\n"


def migrate(ronin_home: Path, dry_run: bool = False):
    """Run the full migration."""
    print(f"Ronin Migration: main -> {ronin_home}")
    print("=" * 60)

    # 1. Create directory structure
    dirs = [
        ronin_home,
        ronin_home / "resumes",
        ronin_home / "assets",
        ronin_home / "data",
        ronin_home / "logs",
    ]

    print("\n[1/6] Creating directories...")
    for d in dirs:
        if dry_run:
            print(f"  Would create: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {d}")

    # 2. Write resume files from main branch
    print("\n[2/6] Migrating resumes...")
    resume_files = {
        "b.txt": "main:assets/cv/b.txt",
        "c.txt": "main:assets/cv/c.txt",
    }
    for filename, git_ref in resume_files.items():
        content = git_show(git_ref)
        dest = ronin_home / "resumes" / filename
        if content:
            if dry_run:
                print(f"  Would write: {dest} ({len(content)} chars)")
            else:
                dest.write_text(content)
                print(f"  Wrote: {dest} ({len(content)} chars)")
        else:
            print(f"  WARNING: Could not read {git_ref}")

    # 3. Write asset files from main branch
    print("\n[3/6] Migrating assets...")
    asset_files = {
        "highlights.txt": "main:assets/highlights.txt",
        "philosophy.txt": "main:assets/philosophy.txt",
        "cover_letter_example.txt": "main:assets/cover_letter_example.txt",
    }
    for filename, git_ref in asset_files.items():
        content = git_show(git_ref)
        dest = ronin_home / "assets" / filename
        if content:
            if dry_run:
                print(f"  Would write: {dest} ({len(content)} chars)")
            else:
                dest.write_text(content)
                print(f"  Wrote: {dest} ({len(content)} chars)")
        else:
            print(f"  WARNING: Could not read {git_ref}")

    # 4. Write profile.yaml
    print("\n[4/6] Building profile.yaml...")
    profile = build_profile()
    profile_path = ronin_home / "profile.yaml"
    profile_yaml = yaml.dump(
        profile, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    # Add header comment
    profile_content = (
        "# Ronin Profile - William Marzella\n"
        "# Migrated from main branch on feat/configurable\n"
        "# Edit with: ronin setup --step <section>\n"
        "#\n"
        "# Sections: personal, work_rights, professional, resumes,\n"
        "#           cover_letter, ai\n"
        "\n" + profile_yaml
    )

    if dry_run:
        print(f"  Would write: {profile_path}")
        print(f"  Preview (first 20 lines):")
        for line in profile_content.split("\n")[:20]:
            print(f"    {line}")
    else:
        profile_path.write_text(profile_content)
        print(f"  Wrote: {profile_path}")

    # 5. Write config.yaml
    print("\n[5/6] Building config.yaml...")
    config = build_config()
    config_path = ronin_home / "config.yaml"
    config_yaml = yaml.dump(
        config, default_flow_style=False, sort_keys=False, allow_unicode=True
    )

    config_content = (
        "# Ronin Runtime Configuration\n"
        "# Migrated from main branch\n"
        "# Controls search parameters, scraping, timeouts, etc.\n"
        "\n" + config_yaml
    )

    if dry_run:
        print(f"  Would write: {config_path}")
    else:
        config_path.write_text(config_content)
        print(f"  Wrote: {config_path}")

    # 6. Write .env
    print("\n[6/6] Migrating .env...")
    env_vars = extract_env_vars()
    env_content = build_env(env_vars)
    env_path = ronin_home / ".env"

    if dry_run:
        if env_vars:
            print(f"  Would write: {env_path} ({len(env_vars)} vars found)")
            # Don't print actual keys in dry run
            for k in env_vars:
                masked = env_vars[k][:8] + "..." if len(env_vars[k]) > 8 else "***"
                print(f"    {k}={masked}")
        else:
            print(f"  Would write: {env_path} (no .env found, template only)")
    else:
        env_path.write_text(env_content)
        print(f"  Wrote: {env_path}")
        if env_vars:
            print(f"  Migrated {len(env_vars)} environment variables")
        else:
            print("  No .env found in project root - template written")

    # 7. Copy existing database if present
    existing_db = Path("data/ronin.db")
    dest_db = ronin_home / "data" / "ronin.db"
    if existing_db.exists() and not dest_db.exists():
        print(f"\n[bonus] Copying existing database...")
        if dry_run:
            print(f"  Would copy: {existing_db} -> {dest_db}")
        else:
            shutil.copy2(existing_db, dest_db)
            print(f"  Copied: {existing_db} -> {dest_db}")

    # Summary
    print("\n" + "=" * 60)
    print("Migration complete!")
    print()
    print(f"Your personal configuration is now at: {ronin_home}")
    print()
    print("Directory structure:")
    if not dry_run:
        for root, dirs_list, files in os.walk(ronin_home):
            level = len(Path(root).relative_to(ronin_home).parts)
            indent = "  " * level
            dirname = Path(root).name
            if level == 0:
                print(f"  {ronin_home}/")
            else:
                print(f"  {indent}{dirname}/")
            for f in sorted(files):
                print(f"  {indent}  {f}")
    else:
        print("  (dry run - no files written)")

    print()
    print("Next steps:")
    print("  1. Review profile.yaml:  cat ~/.ronin/profile.yaml")
    print("  2. Review config.yaml:   cat ~/.ronin/config.yaml")
    print("  3. Verify .env:          cat ~/.ronin/.env")
    print("  4. Test the system:      python -m ronin.cli.main status")
    print("  5. Search for jobs:      python -m ronin.cli.main search")
    print("  6. Apply to jobs:        python -m ronin.cli.main apply")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate personal data from main branch to ~/.ronin/"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    parser.add_argument(
        "--ronin-home",
        type=str,
        default=None,
        help="Override target directory (default: ~/.ronin/)",
    )
    args = parser.parse_args()

    ronin_home = get_ronin_home(args.ronin_home)

    # Safety check
    if (ronin_home / "profile.yaml").exists() and not args.dry_run:
        print(f"WARNING: {ronin_home / 'profile.yaml'} already exists!")
        response = input("Overwrite? [y/N] ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(0)

    migrate(ronin_home, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
