"""Service for analyzing job postings using Anthropic Claude."""

from typing import Dict, Optional

import anthropic
from loguru import logger

from ronin.ai import _parse_json_response
from ronin.analyzer.archetype_classifier import ArchetypeClassifier
from ronin.feedback.analysis import OutcomeAnalytics
from ronin.profile import Profile, load_profile
from ronin.prompts import JOB_ANALYSIS_PROMPT
from ronin.prompts.generator import generate_job_analysis_prompt


class JobAnalyzerService:
    """Service for analyzing job postings using Anthropic Claude."""

    def __init__(self, config: Dict, client=None):
        self.config = config
        self.client = client or anthropic.Anthropic()
        self.model = "claude-sonnet-4-20250514"
        self.profile: Optional[Profile] = None
        self._feedback_context = ""
        self.archetype_classifier = ArchetypeClassifier(
            enable_embeddings=bool(
                self.config.get("analysis", {}).get("enable_embeddings", True)
            ),
            embedding_model_name=self.config.get("analysis", {}).get(
                "embedding_model", "all-MiniLM-L6-v2"
            ),
        )

        try:
            self.profile = load_profile()
            self._system_prompt = generate_job_analysis_prompt(self.profile)
            # Use model from profile if configured
            if self.profile.ai.analysis_model:
                self.model = self.profile.ai.analysis_model
            logger.debug(f"Using dynamic prompt from profile (model: {self.model})")
        except FileNotFoundError:
            self._system_prompt = JOB_ANALYSIS_PROMPT
            logger.debug("No profile found, falling back to static prompt")
        except Exception as e:
            self._system_prompt = JOB_ANALYSIS_PROMPT
            logger.warning(f"Error loading profile, falling back to static prompt: {e}")

        self._feedback_context = self._load_feedback_context()
        if self._feedback_context:
            self._system_prompt = (
                f"{self._system_prompt}\n\n"
                "MARKET FEEDBACK SIGNALS (from historical outcomes):\n"
                f"{self._feedback_context}"
            )

    def _load_feedback_context(self) -> str:
        """Load compact outcome analytics context for prompt conditioning."""
        try:
            analytics = OutcomeAnalytics()
            context = analytics.build_prompt_context(
                max_lines=8,
                min_samples=self.config.get("analysis", {}).get(
                    "feedback_min_samples", 2
                ),
            )
            analytics.close()
            return context
        except Exception as e:
            logger.debug(f"Outcome feedback context unavailable: {e}")
            return ""

    def _rule_based_resume_hint(self, job_data: Dict) -> Optional[str]:
        if not self.profile:
            return None
        try:
            recommended = self.profile.recommend_resume_for_listing(
                job_title=job_data.get("title", ""),
                job_description=job_data.get("description", ""),
                work_type=job_data.get("work_type", ""),
            )
            return recommended.name
        except Exception as e:
            logger.debug(f"Rule-based resume hint unavailable: {e}")
            return None

    def _resolve_resume_profile(self, job_data: Dict, analysis: Dict) -> str:
        """Ensure resume_profile is valid and attach resume_archetype."""
        fallback_profile = analysis.get("resume_profile") or "default"
        if not self.profile or not self.profile.resumes:
            analysis["resume_archetype"] = analysis.get(
                "resume_archetype", "adaptation"
            )
            return fallback_profile

        valid_profiles = {resume.name for resume in self.profile.resumes}
        ai_selected = analysis.get("resume_profile")

        if ai_selected not in valid_profiles:
            suggested = self.profile.recommend_resume_for_listing(
                job_title=job_data.get("title", ""),
                job_description=job_data.get("description", ""),
                work_type=job_data.get("work_type", ""),
            )
            fallback_profile = suggested.name
            if ai_selected:
                logger.debug(
                    f"AI selected unknown resume profile '{ai_selected}', "
                    f"falling back to '{fallback_profile}'"
                )
        else:
            fallback_profile = ai_selected

        analysis["resume_profile"] = fallback_profile
        try:
            resume = self.profile.get_resume(fallback_profile)
            archetype = (
                resume.archetype.value
                if hasattr(resume.archetype, "value")
                else str(resume.archetype)
            )
            analysis["resume_archetype"] = archetype
        except Exception:
            analysis["resume_archetype"] = analysis.get(
                "resume_archetype", "adaptation"
            )

        return fallback_profile

    def _enrich_with_archetype_signals(self, job_data: Dict, analysis: Dict) -> None:
        """Attach deterministic archetype+metadata signals to the AI analysis blob."""
        jd_text = job_data.get("description", "")
        job_title = job_data.get("title", "")
        if not jd_text:
            return

        try:
            classification = self.archetype_classifier.classify(
                jd_text=jd_text,
                job_title=job_title,
            )
            analysis["archetype_scores"] = classification.get("archetype_scores", {})
            analysis["archetype_primary"] = classification.get("archetype_primary")
            analysis["embedding_vector"] = classification.get("embedding_vector")
            analysis["job_type"] = classification.get("job_type", "unknown")
            analysis["tech_stack_tags"] = classification.get("tech_stack_tags", [])
            analysis["seniority_level"] = classification.get(
                "seniority_level", "unknown"
            )
            analysis["archetype_prior"] = classification.get("archetype_prior", {})
            analysis["day_rate_or_salary"] = job_data.get("pay_rate", "")
        except Exception as exc:
            logger.warning(f"Archetype enrichment failed for {job_title}: {exc}")

    def analyze_job(self, job_data: Dict) -> Optional[Dict]:
        """
        Analyze a job posting using Anthropic Claude.

        Args:
            job_data: Dictionary containing job information with a description field

        Returns:
            Dictionary containing the enriched job data with analysis,
            or None if analysis fails
        """
        job_id = job_data.get("job_id", "unknown")
        job_title = job_data.get("title", "unknown")

        logger.info(f"Starting job analysis for '{job_title}' (ID: {job_id})")

        if not job_data.get("description"):
            logger.error(
                f"Job {job_id} ({job_title}) has no description. Skipping analysis."
            )
            return None

        try:
            logger.debug(
                f"Making Anthropic API call for job {job_id} ({job_title}) using model: {self.model}"
            )

            rule_based_resume = self._rule_based_resume_hint(job_data)
            user_prompt = [
                f"Job title: {job_title}",
                f"Work type: {job_data.get('work_type', '')}",
                "Analyze this job description:",
                job_data["description"],
            ]
            if rule_based_resume:
                user_prompt.append(
                    f"Rule-based resume recommendation (heuristic): {rule_based_resume}"
                )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._system_prompt
                + "\n\nIMPORTANT: Your response MUST be a valid JSON object only, no other text.",
                messages=[
                    {
                        "role": "user",
                        "content": "\n\n".join(user_prompt),
                    },
                ],
                temperature=0.7,
            )

            if not response:
                logger.error(
                    f"Failed to get analysis from Anthropic for job {job_id} ({job_title})"
                )
                return None

            content = response.content[0].text
            logger.debug(f"Received response from Anthropic for job {job_id}")

            try:
                analysis = _parse_json_response(content)
            except Exception as e:
                logger.error(f"Failed to parse JSON for job {job_id}: {e}")
                return None
            if analysis is None:
                return None

            resolved_resume_profile = self._resolve_resume_profile(job_data, analysis)
            self._enrich_with_archetype_signals(job_data, analysis)

            enriched_job = job_data.copy()
            enriched_job["analysis"] = analysis
            enriched_job["resume_profile"] = resolved_resume_profile

            min_score = self.config.get("analysis", {}).get("min_score", 0)
            job_score = analysis.get("score", 0)

            if job_score < min_score:
                logger.info(
                    f"Job {job_id} ({job_title}) score {job_score} below minimum {min_score}"
                )
                return None

            return enriched_job

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error for job {job_id}: {e}")
            return None
        except Exception as e:
            logger.exception(f"Error analyzing job {job_id} ({job_title}): {str(e)}")
            return None
