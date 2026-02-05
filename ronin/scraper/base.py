"""Base scraper class for job boards."""

import functools
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from loguru import logger


def rate_limited(func):
    """Decorator to implement rate limiting and error handling for requests."""

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            time.sleep(self.delay)
            return func(self, *args, **kwargs)
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error in {func.__name__}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            return None

    return wrapper


class BaseScraper(ABC):
    """Base class for all job board scrapers."""

    def __init__(self, config: Dict, session: Optional[requests.Session] = None):
        self.config = config
        self.session = session or requests.Session()
        self.delay = config.get("scraping", {}).get("delay_seconds", 2)
        self.max_jobs = config.get("scraping", {}).get("max_jobs", None)
        self.timeout = config.get("scraping", {}).get("timeout_seconds", 10)
        self.quick_apply_only = config.get("scraping", {}).get("quick_apply_only", True)

        # Configure proxy if available
        proxy_config = self._get_proxy_config()
        if proxy_config:
            self.session.proxies.update(proxy_config)

        # Set up common headers
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    def _get_proxy_config(self) -> Optional[Dict[str, str]]:
        """Get proxy configuration from environment variables or config."""
        import os

        http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
        https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")

        if http_proxy or https_proxy:
            proxy_config = {}
            if http_proxy:
                proxy_config["http"] = http_proxy
            if https_proxy:
                proxy_config["https"] = https_proxy
            return proxy_config

        proxy_config = self.config.get("proxy", {})
        if proxy_config.get("enabled", False):
            return {
                "http": proxy_config.get("http_url"),
                "https": proxy_config.get("https_url"),
            }

        return None

    @rate_limited
    def make_request(self, url: str) -> Optional[BeautifulSoup]:
        """Make an HTTP request and return BeautifulSoup object."""
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    @abstractmethod
    def get_job_previews(self) -> List[Dict[str, Any]]:
        """Get job previews with minimal information."""
        pass

    @abstractmethod
    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed job information."""
        pass

    def scrape_jobs(self) -> List[Dict[str, Any]]:
        """Scrape all jobs with full details."""
        job_previews = self.get_job_previews()
        if not job_previews:
            return []

        jobs_data = []
        for preview in job_previews:
            job_details = self.get_job_details(preview["job_id"])
            if job_details:
                if self.quick_apply_only and not job_details.get("quick_apply", False):
                    logger.debug(
                        f"Skipping job without quick apply: {preview['title']} (ID: {preview['job_id']})"
                    )
                    continue

                full_job = {**preview, **job_details}
                jobs_data.append(full_job)
                logger.debug(
                    f"Scraped details for: {preview['title']} (ID: {preview['job_id']})"
                )

        if self.quick_apply_only:
            logger.debug(f"Found {len(jobs_data)} jobs with quick apply option")
        return jobs_data
