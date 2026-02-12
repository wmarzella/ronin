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
        key_tools: str,
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
            key_tools: Primary tools, platforms, or domain area identified by AI.
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


def get_browser_driver():
    """Get the appropriate browser driver based on config.

    Returns ChromeDriver for local/desktop use, CamofoxDriver for
    headless server environments (ECS, VPS).

    Config:
        browser.mode = "system" | "testing" | "camofox"
        browser.camofox_url = "http://localhost:9377"

    Environment:
        CAMOFOX_URL overrides browser.camofox_url
        BROWSER_MODE overrides browser.mode
    """
    import os

    mode = os.environ.get("BROWSER_MODE", "").lower()

    if not mode:
        try:
            from ronin.config import load_config

            config = load_config()
            mode = config.get("browser", {}).get("mode", "system").lower()
        except Exception:
            mode = "system"

    if mode == "camofox":
        from ronin.applier.camofox import CamofoxDriver

        camofox_url = os.environ.get("CAMOFOX_URL")
        if not camofox_url:
            try:
                from ronin.config import load_config

                config = load_config()
                camofox_url = config.get("browser", {}).get("camofox_url")
            except Exception:
                pass

        return CamofoxDriver(camofox_url=camofox_url)

    # Default: local Chrome
    from ronin.applier.browser import ChromeDriver

    return ChromeDriver()
