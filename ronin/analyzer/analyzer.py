"""Service for analyzing job postings using Anthropic Claude."""

from typing import Dict, Optional

import anthropic
from loguru import logger

from ronin.ai import _parse_json_response
from ronin.profile import load_profile
from ronin.prompts import JOB_ANALYSIS_PROMPT
from ronin.prompts.generator import generate_job_analysis_prompt


class JobAnalyzerService:
    """Service for analyzing job postings using Anthropic Claude."""

    def __init__(self, config: Dict, client=None):
        self.config = config
        self.client = client or anthropic.Anthropic()
        self.model = "claude-sonnet-4-20250514"

        try:
            profile = load_profile()
            self._system_prompt = generate_job_analysis_prompt(profile)
            # Use model from profile if configured
            if profile.ai.analysis_model:
                self.model = profile.ai.analysis_model
            logger.debug(f"Using dynamic prompt from profile (model: {self.model})")
        except FileNotFoundError:
            self._system_prompt = JOB_ANALYSIS_PROMPT
            logger.debug("No profile found, falling back to static prompt")
        except Exception as e:
            self._system_prompt = JOB_ANALYSIS_PROMPT
            logger.warning(f"Error loading profile, falling back to static prompt: {e}")

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

            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._system_prompt
                + "\n\nIMPORTANT: Your response MUST be a valid JSON object only, no other text.",
                messages=[
                    {
                        "role": "user",
                        "content": f"Analyze this job description:\n\n{job_data['description']}",
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

            enriched_job = job_data.copy()
            enriched_job["analysis"] = analysis
            enriched_job["resume_profile"] = analysis.get("resume_profile")

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
