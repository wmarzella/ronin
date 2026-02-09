"""AI response generation and processing functionality."""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from ronin.ai import AIService
from ronin.prompts import FORM_FIELD_SYSTEM_PROMPT

try:
    from ronin.profile import load_profile
    from ronin.prompts.generator import generate_form_field_prompt
except ImportError:
    load_profile = None  # type: ignore[assignment,misc]
    generate_form_field_prompt = None  # type: ignore[assignment,misc]


class AIResponseHandler:
    """Handles AI response generation and processing for form elements."""

    # Class-level cache for resume text
    _resume_cache: Dict[str, str] = {}

    def __init__(
        self, ai_service: Optional[AIService] = None, config: Optional[Dict] = None
    ):
        """Initialize the AI response handler."""
        self.ai_service = ai_service or AIService()

        if config is None:
            from ronin.config import load_config

            self.config = load_config()
        else:
            self.config = config

        self.profile = None
        if load_profile is not None:
            try:
                self.profile = load_profile()
                logger.debug("Loaded user profile for form field responses")
            except Exception as e:
                logger.debug(f"Profile not available, using legacy prompts: {e}")

        # Pre-cache system prompt since it doesn't change per-request
        self._system_prompt = self._build_system_prompt()

    def get_ai_form_response(
        self, element_info: Dict, tech_stack, job_description: Optional[str] = None
    ) -> Optional[Dict]:
        """Get AI-generated response for a form element."""
        try:
            tech_stack = self._normalize_tech_stack(tech_stack)

            import time

            prompt_start = time.time()

            resume_text = self._get_resume_text(tech_stack)
            system_prompt = f"{self._system_prompt}\n\nMy resume: {resume_text}"
            user_message = self._build_user_message(element_info, job_description)
            logger.debug(f"Built prompts in {time.time() - prompt_start:.3f}s")

            # Log checkbox questions with their options for debugging
            if element_info["type"] == "checkbox":
                logger.debug(f"Checkbox question: {element_info['question']}")
                for opt in element_info.get("options", []):
                    logger.debug(f"  Option: {opt['label']} (id: {opt['id']})")

            api_start = time.time()
            response = self.ai_service.chat_completion(
                system_prompt=system_prompt, user_message=user_message, temperature=0.3
            )
            logger.debug(f"OpenAI API call took {time.time() - api_start:.3f}s")

            if not response:
                logger.error("No response received from OpenAI")
                return None

            logger.debug(f"AI response for {element_info['type']}: {response}")
            return self._process_ai_response(response, element_info)

        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            return None

    def _normalize_tech_stack(self, tech_stack) -> str:
        """Normalize tech_stack to a lowercase string."""
        if isinstance(tech_stack, list):
            return " ".join(tech_stack).lower() if tech_stack else ""
        elif isinstance(tech_stack, str):
            return tech_stack.lower()
        return ""

    def _build_system_prompt(self) -> str:
        """Build the system prompt for AI responses."""
        keywords = self.config["search"]["keywords"]

        if self.profile is not None and generate_form_field_prompt is not None:
            return generate_form_field_prompt(self.profile, keywords)

        # Legacy fallback
        salary_config = self.config.get("application", {})
        salary_min = salary_config.get("salary_min", 150000)
        salary_max = salary_config.get("salary_max", 200000)

        return FORM_FIELD_SYSTEM_PROMPT.format(
            keywords=keywords,
            salary_min=salary_min,
            salary_max=salary_max,
        )

    def _build_user_message(
        self,
        element_info: Dict,
        job_description: Optional[str] = None,
        has_validation_error: bool = False,
    ) -> str:
        """Build the user message for AI responses."""
        parts = [
            f"Question: {element_info['question']}",
            f"Input type: {element_info['type']}",
        ]

        if has_validation_error:
            parts.append("\n⚠️ VALIDATION ERROR: You MUST select at least one option.")

        if element_info["type"] == "select":
            options_str = "\n".join(
                f"- {opt['label']} (value: {opt['value']})"
                for opt in element_info["options"]
            )
            parts.append(f"\nAvailable options:\n{options_str}")
            parts.append("\nReturn ONLY the exact value, not the label.")

        elif element_info["type"] in ["radio", "checkbox"]:
            options_str = "\n".join(
                f"- {opt['label']} (id: {opt['id']})" for opt in element_info["options"]
            )
            parts.append(f"\nAvailable options:\n{options_str}")
            parts.append("\nReturn ONLY the exact ID, not the label.")

            if element_info["type"] == "checkbox":
                parts.append(
                    "\nIMPORTANT: This is 'select all that apply'. Return ALL IDs that match my skills. Be AGGRESSIVE - if I have equivalent/transferable experience, include it."
                )

        elif element_info["type"] == "textarea":
            parts.append("\nKeep response under 100 words.")

        if job_description:
            parts.append(
                f"\nJob Context: {job_description[:500]}"
            )  # Limit context size

        return "\n".join(parts)

    def _process_ai_response(
        self, response: Dict, element_info: Dict, has_validation_error: bool = False
    ) -> Optional[Dict]:
        """Process and validate the AI response."""
        # Handle string responses
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                response = self._create_fallback_response(response, element_info)

        # Fix checkbox type mismatch
        if (
            element_info["type"] == "checkbox"
            and "selected_option" in response
            and "selected_options" not in response
        ):
            response["selected_options"] = [response["selected_option"]]
            del response["selected_option"]

        # Handle validation errors
        if has_validation_error and element_info["type"] == "checkbox":
            if "selected_options" in response and not response["selected_options"]:
                if element_info.get("options"):
                    response["selected_options"] = [element_info["options"][0]["id"]]
                    logger.warning(
                        "Validation error: forcing selection of first option"
                    )

        if not self._validate_response_fields(response, element_info):
            return None

        return response

    def _create_fallback_response(self, response_str: str, element_info: Dict) -> Dict:
        """Create a fallback response when JSON parsing fails."""
        type_mapping = {
            "select": {"selected_option": response_str},
            "textarea": {"response": response_str},
            "radio": {"selected_option": response_str},
            "checkbox": {"selected_options": [response_str]},
        }
        return type_mapping.get(element_info["type"], {"response": response_str})

    def _validate_response_fields(self, response: Dict, element_info: Dict) -> bool:
        """Validate that the response has the expected fields."""
        required_fields = {
            "textarea": "response",
            "radio": "selected_option",
            "checkbox": "selected_options",
            "select": "selected_option",
        }

        required = required_fields.get(element_info["type"])
        if required and required not in response:
            logger.error(
                f"Missing '{required}' field in {element_info['type']} response"
            )
            return False
        return True

    def _get_resume_text(self, tech_stack: str) -> str:
        """Get resume text, using cache to avoid repeated file reads."""
        tech_stack = tech_stack.lower() if tech_stack else "c"

        # Check cache first
        if tech_stack in self._resume_cache:
            return self._resume_cache[tech_stack]

        # Profile-based lookup
        if self.profile is not None:
            try:
                text = self.profile.get_resume_text(tech_stack)
                self._resume_cache[tech_stack] = text
                logger.debug(f"Loaded resume from profile: {tech_stack}")
                return text
            except (KeyError, FileNotFoundError) as e:
                logger.debug(f"Profile resume lookup failed, using legacy path: {e}")

        # Legacy hardcoded path
        base_path = Path(__file__).parent.parent.parent / "assets" / "cv"

        # Try exact match first
        cv_path = base_path / f"{tech_stack}.txt"
        if cv_path.exists():
            text = cv_path.read_text()
            self._resume_cache[tech_stack] = text
            logger.debug(f"Loaded and cached resume: {cv_path.name}")
            return text

        # Try default resume
        default_path = base_path / "c.txt"
        if default_path.exists():
            text = default_path.read_text()
            self._resume_cache[tech_stack] = text  # Cache under original key too
            self._resume_cache["c"] = text
            logger.debug("Using default C resume")
            return text

        logger.error("No resume file found!")
        return "Resume information not available."
