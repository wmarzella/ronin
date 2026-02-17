"""Queue gating and resume variant alignment services."""

from __future__ import annotations

import json
from typing import Dict, Optional, Tuple

from loguru import logger

from ronin.analyzer.archetype_classifier import ArchetypeClassifier
from ronin.db import get_db_manager
from ronin.resume_variants import ARCHETYPES, ResumeVariantManager


class ApplicationQueueService:
    """Recompute queue gating and keep resume variant metadata in sync."""

    def __init__(self, config: Dict, db_manager: Optional[object] = None):
        self.config = config or {}
        self.db = db_manager or get_db_manager(config=self.config)
        self._owns_db = db_manager is None

        self.classifier = ArchetypeClassifier(
            enable_embeddings=bool(
                self.config.get("analysis", {}).get("enable_embeddings", True)
            ),
            embedding_model_name=self.config.get("analysis", {}).get(
                "embedding_model", "all-MiniLM-L6-v2"
            ),
        )
        self.resume_manager = ResumeVariantManager(self.config)

    def close(self) -> None:
        if self._owns_db:
            self.db.close()

    def refresh_resume_variants(self) -> Dict[str, Dict]:
        """Recompute alignment for all archetypes and persist in DB."""
        variants = self.resume_manager.refresh_variants(self.classifier)
        persisted: Dict[str, Dict] = {}
        for archetype, payload in variants.items():
            ok = self.db.upsert_resume_variant(
                archetype=archetype,
                file_path=payload["file_path"],
                commit_hash=payload["current_commit_hash"],
                alignment_score=payload["alignment_score"],
                embedding_vector=payload["embedding_vector"],
                last_rewritten=payload.get("last_rewritten"),
            )
            if ok:
                persisted[archetype] = payload
        return persisted

    def select_variant(self, jd_archetype_scores: Dict[str, float]) -> Tuple[str, bool]:
        """Return selected archetype and whether review is needed."""
        sorted_scores = sorted(
            jd_archetype_scores.items(),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        if not sorted_scores:
            return "builder", True

        top = sorted_scores[0]
        second = sorted_scores[1] if len(sorted_scores) > 1 else (top[0], 0.0)
        needs_review = (float(top[1]) - float(second[1])) < 0.10
        return top[0], needs_review

    def recompute_queue(self, limit: int = 0) -> Dict[str, int]:
        """Apply queue gating thresholds to discovered jobs."""
        self.refresh_resume_variants()
        threshold = float(
            self.config.get("application", {}).get("queue_threshold", 0.15)
        )

        candidates = self.db.get_queue_candidates(limit=limit)
        updated = 0
        market_intel = 0
        manual_review = 0

        for job in candidates:
            scores = self._get_job_scores(job)
            primary, needs_review = self.select_variant(scores)
            primary_score = float(scores.get(primary, 0.0))
            variant = self.db.get_resume_variant(primary)
            alignment = float(variant.get("alignment_score") or 0.5) if variant else 0.5
            combined_score = primary_score * alignment
            intel_only = 1 if combined_score < threshold else 0

            fields = {
                "archetype_scores": json.dumps(scores),
                "archetype_primary": primary,
                "selection_needs_review": 1 if needs_review else 0,
                "market_intelligence_only": intel_only,
                "resume_archetype": primary,
            }
            if self.db.update_record(job["id"], fields):
                updated += 1
                market_intel += intel_only
                manual_review += 1 if needs_review else 0

        return {
            "evaluated": len(candidates),
            "updated": updated,
            "market_intelligence": market_intel,
            "manual_review": manual_review,
        }

    def _get_job_scores(self, job: Dict) -> Dict[str, float]:
        raw_scores = self.db._safe_json_load(job.get("archetype_scores"), {})
        if isinstance(raw_scores, dict) and raw_scores:
            return {
                archetype: float(raw_scores.get(archetype, 0.0))
                for archetype in ARCHETYPES
            }

        try:
            classification = self.classifier.classify(
                jd_text=job.get("description", "") or "",
                job_title=job.get("title", "") or "",
            )
            update_fields = {
                "archetype_scores": json.dumps(classification["archetype_scores"]),
                "archetype_primary": classification["archetype_primary"],
                "embedding_vector": classification["embedding_vector"],
                "job_type": classification.get("job_type", "unknown"),
                "tech_stack_tags": json.dumps(
                    classification.get("tech_stack_tags", [])
                ),
                "seniority_level": classification.get("seniority_level", "unknown"),
            }
            self.db.update_record(job["id"], update_fields)
            return {
                archetype: float(classification["archetype_scores"].get(archetype, 0.0))
                for archetype in ARCHETYPES
            }
        except Exception as exc:
            logger.warning(f"Failed to classify job {job.get('job_id')}: {exc}")
            return {archetype: 0.25 for archetype in ARCHETYPES}
