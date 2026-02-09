from abc import ABC, abstractmethod
from typing import Optional


class BaseApplier(ABC):
    """Abstract base class for job board application automation."""

    @abstractmethod
    def apply_to_job(
        self,
        job_id: str,
        job_description: str,
        score: int,
        tech_stack: str,
        company_name: str,
        title: str,
        resume_profile: str = "default",
        work_type: Optional[str] = None,
    ) -> str:
        """Apply to a specific job.

        Args:
            job_id: The job board's unique identifier for this job.
            job_description: Full job description text.
            score: AI-assigned relevance score (0-100).
            tech_stack: Primary tech stack identified by AI.
            company_name: Name of the hiring company.
            title: Job title.
            resume_profile: Name of the resume profile to use (from profile.yaml).
            work_type: Type of work (e.g. "Contract/Temp", "Full time").

        Returns:
            Status string: "APPLIED", "STALE", "APP_ERROR", "COVER_LETTER_FAILED".
        """
        ...

    @abstractmethod
    def login(self) -> bool:
        """Log in to the job board.

        Returns:
            True if login successful.
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up resources (close browser, release locks, etc.)."""
        ...

    @property
    @abstractmethod
    def board_name(self) -> str:
        """Return the name of the job board (e.g. 'seek', 'linkedin')."""
        ...


def get_applier(board_name: str) -> BaseApplier:
    """Get an applier instance for the given job board.

    Currently supported: "seek"

    Args:
        board_name: Name of the job board.

    Returns:
        An applier instance for the specified board.

    Raises:
        ValueError: If board_name is not supported.
    """
    # Import here to avoid circular imports
    if board_name == "seek":
        from ronin.applier.applier import SeekApplier

        return SeekApplier()
    raise ValueError(f"Unsupported job board: {board_name}. Supported: seek")
