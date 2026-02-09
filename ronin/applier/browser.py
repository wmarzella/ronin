"""Chrome WebDriver manager for browser automation tasks."""

import glob
import json
import os
import platform
import shutil
import time
import uuid
from pathlib import Path

from loguru import logger
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from filelock import FileLock
except ImportError:
    # No-op fallback when filelock is not installed
    class FileLock:
        """No-op file lock for platforms without filelock."""

        def __init__(self, lock_file, timeout=-1):
            self._lock_file = lock_file

        def acquire(self, timeout=None):
            pass

        def release(self):
            pass

        def __enter__(self):
            self.acquire()
            return self

        def __exit__(self, *args):
            self.release()


def _get_chrome_binary_candidates() -> list[str]:
    """Return platform-specific Chrome binary search paths."""
    system = platform.system()
    home = str(Path.home())
    candidates = []

    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        ]
        # Scan ~/chrome/ for Chrome for Testing bundles
        chrome_testing_base = Path(home) / "chrome"
        if chrome_testing_base.is_dir():
            for app_bundle in sorted(
                chrome_testing_base.rglob("Google Chrome for Testing.app"), reverse=True
            ):
                candidates.append(
                    str(app_bundle / "Contents" / "MacOS" / "Google Chrome for Testing")
                )
    elif system == "Windows":
        prog = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog_x86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        candidates = [
            os.path.join(prog, "Google", "Chrome", "Application", "chrome.exe"),
            os.path.join(prog_x86, "Google", "Chrome", "Application", "chrome.exe"),
        ]
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
        ]

    return candidates


USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"


class ChromeDriver:
    """Manages Chrome WebDriver sessions for browser automation."""

    def __init__(self):
        """Initialize the ChromeDriver."""
        self.driver = None
        self.is_logged_in = False
        self.user_data_dir = None
        self._profile_lock = None
        ronin_dir = Path.home() / ".ronin"
        ronin_dir.mkdir(parents=True, exist_ok=True)
        self.login_state_file = str(ronin_dir / "login_state.json")

    def _find_chrome_binary(self) -> str:
        """Find Chrome binary location.

        Search order:
        1. CHROME_BINARY_PATH environment variable
        2. browser.chrome_path from config.yaml
        3. Platform-specific default locations
        """
        # 1. Environment variable
        chrome_env_path = os.environ.get("CHROME_BINARY_PATH")
        if chrome_env_path and os.path.exists(chrome_env_path):
            logger.info(f"Using Chrome from environment: {chrome_env_path}")
            return chrome_env_path

        # 2. Config file
        try:
            from ronin.config import load_config

            config = load_config()
            config_path = config.get("browser", {}).get("chrome_path", "")
            if config_path and os.path.exists(config_path):
                logger.info(f"Using Chrome from config: {config_path}")
                return config_path
        except Exception:
            pass

        # 3. Platform-specific candidates
        for location in _get_chrome_binary_candidates():
            if os.path.exists(location):
                logger.info(f"Found Chrome at: {location}")
                return location

        logger.warning(
            "Chrome binary not found. Set CHROME_BINARY_PATH env var or browser.chrome_path in config.yaml"
        )
        return None

    def _configure_chrome_options(
        self, chrome_binary: str = None
    ) -> webdriver.ChromeOptions:
        """Configure Chrome options with all required flags."""
        options = webdriver.ChromeOptions()

        if chrome_binary:
            options.binary_location = chrome_binary

        # Basic options
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-default-apps")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("detach", True)

        # Stability options
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-browser-side-navigation")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--disable-renderer-backgrounding")

        # Additional feature disables
        options.add_argument("--disable-web-security")
        options.add_argument("--allow-running-insecure-content")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-sync")
        options.add_argument("--mute-audio")
        options.add_argument("--disable-notifications")

        # Performance optimizations
        options.add_argument("--memory-pressure-off")
        options.add_argument("--disable-background-networking")

        # User agent and window settings
        options.add_argument(f"--user-agent={USER_AGENT}")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")

        return options

    def _setup_profile_directory(self) -> str:
        """Set up Chrome profile directory with cross-platform file locking."""
        ronin_dir = Path.home() / ".ronin"
        base_profile_dir = ronin_dir / "chrome_profile"
        lock_file_path = str(ronin_dir / "chrome_profile.lock")

        try:
            self._profile_lock = FileLock(lock_file_path, timeout=0)
            self._profile_lock.acquire()

            # Got the lock, use shared profile
            self.user_data_dir = str(base_profile_dir)
            base_profile_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Using shared Chrome profile for login persistence")
        except Exception:
            # Lock failed (Timeout or other), use unique session directory
            session_id = str(uuid.uuid4())[:8]
            session_dir = ronin_dir / f"chrome_profile_{session_id}"
            self.user_data_dir = str(session_dir)
            session_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Using session-specific profile: {session_id}")

            if self._profile_lock:
                try:
                    self._profile_lock.release()
                except Exception:
                    pass
                self._profile_lock = None

        # Clear cache to prevent blank page issues
        cache_dir = Path(self.user_data_dir) / "Default" / "Cache"
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
                logger.debug("Cleared Chrome cache")
            except OSError as e:
                logger.warning(f"Could not clear cache: {e}")

        return self.user_data_dir

    def _test_browser_functionality(self) -> bool:
        """Test if browser can render basic content."""
        if not self.driver:
            return False

        try:
            self.driver.get("data:text/html,<html><body><h1>Test</h1></body></html>")
            time.sleep(1)
            if "Test" not in self.driver.page_source:
                logger.warning("Browser failed rendering test")
                return False
            logger.debug("Browser passed functionality test")
            return True
        except WebDriverException as e:
            logger.warning(f"Browser test failed: {e}")
            return False

    def initialize(self) -> webdriver.Chrome:
        """Initialize Chrome WebDriver with local browser."""
        if self.driver:
            return self.driver

        self.load_login_state()

        chrome_binary = self._find_chrome_binary()
        options = self._configure_chrome_options(chrome_binary)
        profile_dir = self._setup_profile_directory()
        options.add_argument(f"--user-data-dir={profile_dir}")

        # Attempt initialization with retries
        max_retries = 3
        for retry_count in range(max_retries):
            try:
                self.driver = webdriver.Chrome(options=options)
                self.driver.implicitly_wait(10)
                self.driver.set_window_size(1920, 1080)

                if not self._test_browser_functionality():
                    self.driver.quit()
                    raise WebDriverException("Browser failed initialization test")

                logger.info("Chrome WebDriver initialized successfully")
                return self.driver
            except WebDriverException as e:
                logger.warning(f"Attempt {retry_count + 1}/{max_retries} failed: {e}")
                time.sleep(2)

                if retry_count >= max_retries - 1:
                    logger.error(f"Failed after {max_retries} attempts: {e}")
                    raise

    def navigate_to(self, url: str):
        """Navigate the browser to a specific URL."""
        if not self.driver:
            self.initialize()

        try:
            logger.debug(f"Navigating to: {url}")
            self.driver.get(url)

            # Wait for page to load and verify it's not blank
            max_wait_time = 45  # Increased wait time for slow loading sites
            wait_time = 0

            while wait_time < max_wait_time:
                try:
                    # Check if page has loaded (not blank/white screen)
                    ready_state = self.driver.execute_script(
                        "return document.readyState"
                    )

                    if ready_state == "complete":
                        # Multiple checks to ensure content is actually loaded
                        body_text = self.driver.execute_script(
                            "return document.body.innerText || ''"
                        )
                        page_html = self.driver.execute_script(
                            "return document.body.innerHTML || ''"
                        )
                        has_inputs = (
                            len(self.driver.find_elements(By.TAG_NAME, "input")) > 0
                        )
                        has_buttons = (
                            len(self.driver.find_elements(By.TAG_NAME, "button")) > 0
                        )
                        has_links = len(self.driver.find_elements(By.TAG_NAME, "a")) > 0

                        # Check for specific Workforce Australia elements
                        if "workforceaustralia" in url.lower():
                            has_wa_content = any(
                                [
                                    "workforce" in body_text.lower(),
                                    "job" in body_text.lower(),
                                    "search" in body_text.lower(),
                                    len(page_html)
                                    > 1000,  # Page has substantial content
                                    has_inputs or has_buttons or has_links,
                                ]
                            )

                            if has_wa_content:
                                logger.info(
                                    "Workforce Australia page loaded successfully"
                                )
                                break
                        else:
                            # Generic content check
                            if (
                                body_text.strip()
                                or has_inputs
                                or has_buttons
                                or len(page_html) > 100
                            ):
                                logger.info("Page loaded successfully")
                                break

                    time.sleep(2)  # Increased sleep time for slower loading
                    wait_time += 2

                    # Log progress every 10 seconds
                    if wait_time % 10 == 0:
                        logger.info(f"Still waiting for page to load... ({wait_time}s)")

                except Exception as check_error:
                    logger.warning(f"Error checking page state: {check_error}")
                    time.sleep(2)
                    wait_time += 2

            if wait_time >= max_wait_time:
                logger.warning(
                    f"Page may not have loaded properly after {max_wait_time}s"
                )
                # Try a refresh as last resort
                try:
                    logger.info("Attempting page refresh...")
                    self.driver.refresh()
                    time.sleep(5)
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error navigating to {url}: {str(e)}")
            raise

    def wait_for_element(
        self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10
    ):
        """Wait for an element to be present and return it."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def wait_for_clickable(
        self, selector: str, by: By = By.CSS_SELECTOR, timeout: int = 10
    ):
        """Wait for an element to be clickable and return it."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, selector))
        )

    def find_element(self, selector: str, by: By = By.CSS_SELECTOR):
        """Find an element using the specified selector."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return self.driver.find_element(by, selector)

    def find_elements(self, selector: str, by: By = By.CSS_SELECTOR):
        """Find elements using the specified selector."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return self.driver.find_elements(by, selector)

    def _check_logged_in_indicators(self) -> bool:
        """Quick check for logged-in indicators. Returns True if logged in."""
        # Use JS for instant check - much faster than XPath queries
        js_check = """
        return !!(
            document.querySelector('a[href*="/account"]') ||
            document.querySelector('[data-automation="account-menu"]') ||
            document.querySelector('button[aria-label*="Account"]') ||
            document.body.innerText.includes('Sign out')
        );
        """
        try:
            return self.driver.execute_script(js_check)
        except Exception:
            return False

    def login_seek(self):
        """Handle Seek.com.au login process."""
        if self.is_logged_in:
            logger.debug("Already logged in (from saved state), skipping login check")
            return

        try:
            # Quick navigation to check login status
            logger.debug("Checking Seek login status...")
            self.driver.get("https://www.seek.com.au")

            # Quick wait for page to minimally load
            WebDriverWait(self.driver, 5).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )

            # Check if already logged in
            if self._check_logged_in_indicators():
                self.is_logged_in = True
                logger.debug("User is already logged in to Seek")
                self.save_login_state()
                return

            # If no logged-in indicators found, proceed with manual login
            from rich.console import Console

            console = Console()
            console.print("\n[bold yellow]Login Required[/bold yellow]")
            console.print(
                "[dim]1. Please sign in with Google in the browser window[/dim]"
            )
            console.print("[dim]2. Make sure you're fully logged in[/dim]")
            console.print("[dim]3. Press Enter when ready to continue...[/dim]")
            input()

            # Verify login was successful
            if self._check_logged_in_indicators():
                self.is_logged_in = True
                logger.debug("Successfully logged into Seek")
                self.save_login_state()
                return

            # If we get here, login verification failed but continue anyway
            logger.warning("Could not verify login status, but continuing...")
            self.is_logged_in = True
            self.save_login_state()

        except Exception as e:
            raise Exception(f"Failed to login to Seek: {str(e)}")

    def save_login_state(self):
        """Save login state to file."""
        try:
            login_state = {"is_logged_in": self.is_logged_in, "timestamp": time.time()}

            # Ensure the directory exists
            os.makedirs(os.path.dirname(self.login_state_file), exist_ok=True)

            with open(self.login_state_file, "w") as f:
                json.dump(login_state, f)

            logger.debug("Login state saved")
        except Exception as e:
            logger.warning(f"Failed to save login state: {e}")

    def load_login_state(self):
        """Load login state from file."""
        try:
            if os.path.exists(self.login_state_file):
                with open(self.login_state_file, "r") as f:
                    login_state = json.load(f)

                # Check if login state is recent (within last 24 hours)
                current_time = time.time()
                if current_time - login_state.get("timestamp", 0) < 24 * 3600:
                    self.is_logged_in = login_state.get("is_logged_in", False)
                    logger.info(f"Loaded login state: {self.is_logged_in}")
                else:
                    logger.info("Login state expired, will re-check")
                    self.is_logged_in = False
            else:
                logger.info("No saved login state found")
                self.is_logged_in = False
        except Exception as e:
            logger.warning(f"Failed to load login state: {e}")
            self.is_logged_in = False

    @property
    def current_url(self) -> str:
        """Get the current URL."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return self.driver.current_url

    @property
    def page_source(self) -> str:
        """Get the current page source."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        return self.driver.page_source

    def reset_profile(self):
        """Reset Chrome profile to fix persistent issues."""
        import glob
        import shutil

        if self.driver:
            self.driver.quit()
            self.driver = None
            self.is_logged_in = False

        # Clean up all chrome session profiles under ~/.ronin/
        ronin_dir = Path.home() / ".ronin"
        profile_pattern = str(ronin_dir / "chrome_profile_*")
        for profile_dir in glob.glob(profile_pattern):
            if os.path.exists(profile_dir):
                try:
                    shutil.rmtree(profile_dir)
                    logger.info(f"Chrome profile {profile_dir} reset successfully")
                except Exception as e:
                    logger.error(f"Failed to reset Chrome profile {profile_dir}: {e}")

    def cleanup(self, preserve_session: bool = True):
        """Clean up resources.

        Args:
            preserve_session: If True, keeps the Chrome profile so cookies/login
                            persist for next run. If False, deletes everything.
        """
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Chrome browser closed")
            except Exception as e:
                logger.warning(f"Error closing Chrome: {e}")
            self.driver = None

        # Release the profile lock if we have one
        if self._profile_lock:
            try:
                self._profile_lock.release()
                self._profile_lock = None
            except Exception:
                pass

        # Only delete profile if explicitly requested (for troubleshooting)
        if not preserve_session and self.user_data_dir:
            # Only delete session-specific profiles, never the shared one
            base_profile = str(Path.home() / ".ronin" / "chrome_profile")
            if self.user_data_dir != base_profile and os.path.exists(
                self.user_data_dir
            ):
                try:
                    shutil.rmtree(self.user_data_dir)
                    logger.info(f"Cleaned up Chrome profile: {self.user_data_dir}")
                except Exception as e:
                    logger.warning(f"Could not clean up Chrome profile: {e}")

        self.user_data_dir = None
