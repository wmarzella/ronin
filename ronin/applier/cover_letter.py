"""Cover letter generation functionality for job applications."""

from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from ronin.ai import AnthropicService
from ronin.prompts import (
    COVER_LETTER_CONTRACT_CONTEXT,
    COVER_LETTER_FULLTIME_CONTEXT,
    COVER_LETTER_SYSTEM_PROMPT,
)


class CoverLetterGenerator:
    """Handles the generation of cover letters for job applications."""

    def __init__(self, ai_service: Optional[AnthropicService] = None):
        """
        Initialize the cover letter generator.

        Args:
            ai_service: An instance of AnthropicService. If None, a new instance will be created.
        """
        self.ai_service = ai_service or AnthropicService()

    def generate_cover_letter(
        self,
        job_description: str,
        title: str,
        company_name: str,
        tech_stack: str,
        resume_text: str = None,
        work_type: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a cover letter for a job application.

        Args:
            job_description: The full job description text
            title: The job title
            company_name: The company name
            tech_stack: The tech stack for the job
            resume_text: Optional resume text to include. If None, will be loaded from appropriate files.
            work_type: The work type (e.g., "Contract/Temp", "Full time")

        Returns:
            Dictionary containing the generated cover letter or None if generation failed.
        """
        try:
            # Load example cover letter
            with open("assets/cover_letter_example.txt", "r") as f:
                example = f.read()

            # Load condensed highlights for cover letter context
            highlights_path = (
                Path(__file__).parent.parent.parent / "assets" / "highlights.txt"
            )
            if highlights_path.exists():
                resume_text = highlights_path.read_text()
            else:
                # Fallback to full resume if highlights doesn't exist
                resume_text = (
                    self._get_resume_text(tech_stack)
                    if resume_text is None
                    else resume_text
                )

            # Determine engagement type and appropriate framing
            is_contract = work_type and "contract" in work_type.lower()

            engagement_type = "CONTRACT/TEMP" if is_contract else "FULL-TIME/PERMANENT"
            engagement_context = (
                COVER_LETTER_CONTRACT_CONTEXT
                if is_contract
                else COVER_LETTER_FULLTIME_CONTEXT
            )

            system_prompt = COVER_LETTER_SYSTEM_PROMPT.format(
                engagement_type=engagement_type,
                engagement_context=engagement_context,
                example=example,
                resume_text=resume_text,
            )

            user_message = f"Write a cover letter for the {'contract' if is_contract else 'full-time'} role of {title} at {company_name}: {job_description}"

            return self.ai_service.chat_completion(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.7,
                max_tokens=8192,
            )

        except Exception as e:
            logger.error(f"Failed to generate cover letter: {e}")
            return None

    def _get_resume_text(self, tech_stack: str) -> str:
        """Get the resume text based on tech stack or job classification."""
        tech_stack = tech_stack.lower() if tech_stack else "c"
        base_path = Path(__file__).parent.parent.parent / "assets" / "cv"

        # Try exact match first
        cv_path = base_path / f"{tech_stack}.txt"
        if cv_path.exists():
            logger.debug(f"Using resume: {cv_path.name}")
            return cv_path.read_text()

        # Default to C resume
        default_path = base_path / "c.txt"
        if default_path.exists():
            logger.debug("Using default C resume")
            return default_path.read_text()

        logger.error("No resume file found!")
        return "Resume information not available."
