"""Prompts for AI services."""

from ronin.prompts.cover_letter import (
    COVER_LETTER_CONTRACT_CONTEXT,
    COVER_LETTER_FULLTIME_CONTEXT,
    COVER_LETTER_SYSTEM_PROMPT,
)
from ronin.prompts.form_fields import FORM_FIELD_SYSTEM_PROMPT
from ronin.prompts.job_analysis import JOB_ANALYSIS_PROMPT

__all__ = [
    "JOB_ANALYSIS_PROMPT",
    "COVER_LETTER_SYSTEM_PROMPT",
    "COVER_LETTER_CONTRACT_CONTEXT",
    "COVER_LETTER_FULLTIME_CONTEXT",
    "FORM_FIELD_SYSTEM_PROMPT",
]
