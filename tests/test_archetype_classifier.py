#!/usr/bin/env python3
"""Lightweight regression checks for the archetype classifier.

These tests are intentionally dependency-light (no sentence-transformers required)
and run as a standalone script.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def test_primary_archetypes() -> None:
    from ronin.analyzer.archetype_classifier import ArchetypeClassifier

    classifier = ArchetypeClassifier(enable_embeddings=False)

    samples = {
        "builder": (
            "We will design and implement a new platform from the ground up. "
            "You will establish standards and build out cloud-native pipelines in AWS."
        ),
        "fixer": (
            "This role will migrate from Redshift to Snowflake and modernise legacy ETL. "
            "You will refactor existing workflows and reduce technical debt."
        ),
        "operator": (
            "Provide production support and incident response for our data platform. "
            "Maintain SLAs, monitor pipelines, and participate in on-call rotation."
        ),
        "translator": (
            "Partner with stakeholders to gather requirements and enable self-serve analytics. "
            "Improve data literacy and translate business needs into technical deliverables."
        ),
    }

    for expected, jd_text in samples.items():
        result = classifier.classify(jd_text=jd_text, job_title="Data Engineer")
        predicted = result.get("archetype_primary")
        _assert(
            predicted == expected,
            f"Expected {expected}, got {predicted} (scores={result.get('archetype_scores')})",
        )


def test_metadata_extraction() -> None:
    from ronin.analyzer.archetype_classifier import ArchetypeClassifier

    classifier = ArchetypeClassifier(enable_embeddings=False)
    meta = classifier.extract_metadata(
        jd_text="6 month contract role supporting production systems. Maintain SLAs.",
        job_title="Senior Data Engineer",
    )
    _assert(meta.get("job_type") == "contract", f"Unexpected job_type: {meta}")
    _assert(meta.get("seniority_level") == "senior", f"Unexpected seniority: {meta}")


def test_fixture_regressions() -> None:
    from ronin.analyzer.archetype_classifier import ArchetypeClassifier

    classifier = ArchetypeClassifier(enable_embeddings=False)
    fixture_path = Path(__file__).parent / "fixtures" / "archetype_jds.jsonl"
    rows = fixture_path.read_text(encoding="utf-8").splitlines()
    _assert(rows, "Fixture file is empty")

    for line in rows:
        payload = json.loads(line)
        expected = str(payload.get("expected") or "").strip().lower()
        title = str(payload.get("title") or "")
        jd_text = str(payload.get("jd_text") or "")
        name = payload.get("name")

        result = classifier.classify(jd_text=jd_text, job_title=title)
        predicted = result.get("archetype_primary")
        _assert(
            predicted == expected,
            f"Fixture {name}: expected {expected}, got {predicted} (scores={result.get('archetype_scores')})",
        )


def main() -> int:
    try:
        test_primary_archetypes()
        test_metadata_extraction()
        test_fixture_regressions()
        print("PASS: archetype classifier")
        return 0
    except Exception as exc:
        print(f"FAIL: archetype classifier -- {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
