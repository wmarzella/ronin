"""Camofox browser adapter for headless server environments (ECS, VPS, etc).

Wraps the camofox-browser REST API to provide a Selenium-compatible interface
so existing applier code can work with minimal changes.

camofox-browser is a headless browser server built on Camoufox (a Firefox fork
that spoofs browser fingerprints at the C++ level). This gives it a higher
probability of passing detection systems than standard headless Chrome.

Usage:
    Set browser.mode = "camofox" in config.yaml and provide the server URL:

    browser:
      mode: "camofox"
      camofox_url: "http://localhost:9377"

    Or via environment variable:
      CAMOFOX_URL=http://localhost:9377
"""

import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


class CamofoxElement:
    """Mimics a Selenium WebElement using camofox element refs.

    The camofox accessibility snapshot returns elements with refs like e1, e2, e3.
    This class wraps those refs so existing code that calls element.click(),
    element.send_keys(), etc. can work through the REST API.
    """

    def __init__(self, driver: "CamofoxBrowserDriver", ref: str, attrs: Dict[str, Any]):
        self._driver = driver
        self._ref = ref
        self._attrs = attrs
        self.tag_name = attrs.get("tag", attrs.get("role", "unknown"))
        self.text = attrs.get("text", attrs.get("name", ""))

    def click(self):
        """Click this element via the camofox REST API."""
        self._driver._click(self._ref)

    def send_keys(self, text: str):
        """Type text into this element via the camofox REST API."""
        self._driver._type(self._ref, text)

    def clear(self):
        """Clear the element's text content.

        Camofox doesn't have a native clear, so we select all then
        type empty.
        """
        self._driver._type(self._ref, "", clear_first=True)

    def get_attribute(self, name: str) -> Optional[str]:
        """Get an attribute value from the cached element data."""
        return self._attrs.get(name)

    def is_selected(self) -> bool:
        """Check if element is selected (checkbox/radio)."""
        return self._attrs.get("checked", False) or self._attrs.get("selected", False)

    def is_displayed(self) -> bool:
        """Elements returned from accessibility snapshot are visible by definition."""
        return True

    def is_enabled(self) -> bool:
        """Check if element is enabled."""
        return not self._attrs.get("disabled", False)

    def find_element(self, by: str, value: str) -> "CamofoxElement":
        """Find a child element. Delegates to driver with scope hint."""
        results = self._driver._find_elements_in_snapshot(
            by, value, scope_ref=self._ref
        )
        if not results:
            raise CamofoxNoSuchElementException(
                f"No element found: {by}={value} within {self._ref}"
            )
        return results[0]

    def find_elements(self, by: str, value: str) -> List["CamofoxElement"]:
        """Find child elements. Delegates to driver with scope hint."""
        return self._driver._find_elements_in_snapshot(by, value, scope_ref=self._ref)


class CamofoxNoSuchElementException(Exception):
    """Raised when an element cannot be found."""

    pass


class CamofoxTimeoutException(Exception):
    """Raised when a wait times out."""

    pass


class CamofoxBrowserDriver:
    """REST API client for camofox-browser that mimics Selenium WebDriver.

    Provides the subset of the Selenium WebDriver API that ronin's applier
    code actually uses, translating each call into camofox REST requests.
    """

    def __init__(self, base_url: str = "http://localhost:9377"):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.tab_id: Optional[str] = None
        self.user_id: str = f"ronin-{uuid.uuid4().hex[:8]}"
        self.session_key: str = f"session-{uuid.uuid4().hex[:8]}"
        self._current_url: str = ""
        self._snapshot_cache: Optional[Dict] = None
        self._snapshot_elements: Dict[str, CamofoxElement] = {}
        self._implicit_wait: int = 10

    # ── Lifecycle ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check if camofox-browser server is reachable."""
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def create_tab(self, url: str = "about:blank") -> str:
        """Create a new browser tab and return the tab ID."""
        resp = self.session.post(
            f"{self.base_url}/tabs",
            json={
                "userId": self.user_id,
                "sessionKey": self.session_key,
                "url": url,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self.tab_id = data.get("tabId") or data.get("id")
        self._current_url = url
        self._invalidate_snapshot()
        logger.debug(f"Camofox tab created: {self.tab_id}")
        return self.tab_id

    def close_tab(self):
        """Close the current tab."""
        if not self.tab_id:
            return
        try:
            self.session.delete(
                f"{self.base_url}/tabs/{self.tab_id}",
                params={"userId": self.user_id},
                timeout=10,
            )
        except requests.RequestException as e:
            logger.warning(f"Error closing camofox tab: {e}")
        self.tab_id = None

    # ── Navigation (Selenium-compatible interface) ─────────────────────

    def get(self, url: str):
        """Navigate to a URL (Selenium WebDriver.get equivalent)."""
        if not self.tab_id:
            self.create_tab(url)
            return

        resp = self.session.post(
            f"{self.base_url}/tabs/{self.tab_id}/navigate",
            json={"userId": self.user_id, "url": url},
            timeout=60,
        )
        resp.raise_for_status()
        self._current_url = url
        self._invalidate_snapshot()

    @property
    def current_url(self) -> str:
        """Get current URL."""
        # Refresh from snapshot if available
        snapshot = self._get_snapshot()
        if snapshot and "url" in snapshot:
            self._current_url = snapshot["url"]
        return self._current_url

    @property
    def page_source(self) -> str:
        """Get page content as text (from accessibility snapshot).

        Note: This returns the accessibility tree text, not raw HTML.
        For detection of text content (stale indicators, success messages),
        this works fine. For actual HTML parsing, use get_snapshot().
        """
        snapshot = self._get_snapshot()
        if snapshot:
            return snapshot.get("text", "") or json.dumps(snapshot)
        return ""

    # ── Snapshot ──────────────────────────────────────────────────────

    def _get_snapshot(self, force: bool = False) -> Optional[Dict]:
        """Get the accessibility snapshot for the current tab."""
        if not self.tab_id:
            return None

        if self._snapshot_cache and not force:
            return self._snapshot_cache

        try:
            resp = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}/snapshot",
                params={"userId": self.user_id},
                timeout=30,
            )
            resp.raise_for_status()
            self._snapshot_cache = resp.json()
            self._build_element_index()
            return self._snapshot_cache
        except requests.RequestException as e:
            logger.warning(f"Failed to get camofox snapshot: {e}")
            return None

    def _invalidate_snapshot(self):
        """Clear the cached snapshot so the next access fetches fresh data."""
        self._snapshot_cache = None
        self._snapshot_elements.clear()

    def _build_element_index(self):
        """Build a lookup index from the snapshot's element tree."""
        self._snapshot_elements.clear()
        if not self._snapshot_cache:
            return

        elements = self._snapshot_cache.get("elements", [])
        for elem_data in elements:
            ref = elem_data.get("ref")
            if ref:
                self._snapshot_elements[ref] = CamofoxElement(
                    driver=self, ref=ref, attrs=elem_data
                )

    # ── Element interaction (via REST) ─────────────────────────────────

    def _click(self, ref: str):
        """Click an element by its ref."""
        resp = self.session.post(
            f"{self.base_url}/tabs/{self.tab_id}/click",
            json={"userId": self.user_id, "ref": ref},
            timeout=15,
        )
        resp.raise_for_status()
        self._invalidate_snapshot()

    def _type(self, ref: str, text: str, clear_first: bool = False):
        """Type text into an element by its ref."""
        payload = {"userId": self.user_id, "ref": ref, "text": text}
        if clear_first:
            payload["clearFirst"] = True

        resp = self.session.post(
            f"{self.base_url}/tabs/{self.tab_id}/type",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        self._invalidate_snapshot()

    def _scroll(self, direction: str = "down", amount: int = 300):
        """Scroll the page."""
        resp = self.session.post(
            f"{self.base_url}/tabs/{self.tab_id}/scroll",
            json={
                "userId": self.user_id,
                "direction": direction,
                "amount": amount,
            },
            timeout=10,
        )
        resp.raise_for_status()
        self._invalidate_snapshot()

    # ── Element finding (Selenium-compatible) ──────────────────────────

    def find_element(self, by: str, value: str) -> CamofoxElement:
        """Find a single element (Selenium WebDriver.find_element equivalent)."""
        results = self._find_elements_in_snapshot(by, value)
        if not results:
            raise CamofoxNoSuchElementException(f"No element found: {by}={value}")
        return results[0]

    def find_elements(self, by: str, value: str) -> List[CamofoxElement]:
        """Find elements (Selenium WebDriver.find_elements equivalent)."""
        return self._find_elements_in_snapshot(by, value)

    def _find_elements_in_snapshot(
        self, by: str, value: str, scope_ref: Optional[str] = None
    ) -> List[CamofoxElement]:
        """Search the accessibility snapshot for elements matching the selector.

        This is an approximation -- camofox's accessibility tree doesn't map 1:1
        to CSS selectors. We do best-effort matching on common patterns used by
        ronin's applier code.
        """
        # Refresh snapshot
        self._get_snapshot(force=True)

        if not self._snapshot_elements:
            return []

        matches = []
        for ref, elem in self._snapshot_elements.items():
            if self._element_matches(elem, by, value):
                matches.append(elem)

        return matches

    def _element_matches(self, elem: CamofoxElement, by: str, value: str) -> bool:
        """Check if an element matches a Selenium-style selector.

        Handles the common patterns used by ronin:
        - By.CSS_SELECTOR with data-testid, data-automation, name, id, type
        - By.TAG_NAME
        - By.ID
        - By.XPATH (basic text contains)
        """
        attrs = elem._attrs

        # By.ID
        if by == "id":
            return attrs.get("id") == value

        # By.TAG_NAME
        if by == "tag name":
            return attrs.get("tag", "").lower() == value.lower()

        # By.CSS_SELECTOR -- parse common patterns
        if by == "css selector":
            return self._match_css_selector(attrs, value)

        # By.XPATH -- basic text matching
        if by == "xpath":
            if "contains(text()" in value or "contains(normalize-space" in value:
                # Extract the search text from the XPath
                import re

                match = re.search(r"contains\([^,]+,\s*['\"]([^'\"]+)['\"]\)", value)
                if match:
                    search_text = match.group(1).lower()
                    elem_text = (attrs.get("text", "") or "").lower()
                    return search_text in elem_text
            if "ancestor::" in value:
                # Parent traversal -- not directly supported in flat snapshot
                return False

        return False

    def _match_css_selector(self, attrs: Dict, selector: str) -> bool:
        """Match a CSS selector against element attributes.

        Handles patterns like:
        - [data-testid='continue-button']
        - input[name='coverLetter-method']
        - [data-automation='job-detail-apply']
        - #elementId
        - .className
        - tag[attr=val]
        """
        import re

        selector = selector.strip()

        # ID selector: #foo
        if selector.startswith("#"):
            return attrs.get("id") == selector[1:]

        # Attribute selector: [attr=val] or tag[attr=val]
        attr_match = re.search(r"\[([a-zA-Z_-]+)=['\"]?([^'\"\]]+)['\"]?\]", selector)
        if attr_match:
            attr_name = attr_match.group(1)
            attr_value = attr_match.group(2)

            # Check tag prefix if present
            tag_prefix = selector.split("[")[0].strip()
            if tag_prefix and attrs.get("tag", "").lower() != tag_prefix.lower():
                if tag_prefix not in ("*", ""):
                    return False

            return attrs.get(attr_name) == attr_value

        # Tag only: input, select, textarea, etc.
        if re.match(r"^[a-z]+$", selector):
            return attrs.get("tag", "").lower() == selector

        return False

    # ── JavaScript execution (limited compatibility) ──────────────────

    def execute_script(self, script: str, *args) -> Any:
        """Execute JavaScript in the browser tab.

        Camofox-browser may not support arbitrary JS execution via REST.
        For common patterns used by ronin (readyState check, innerText, etc.),
        we return sensible defaults from the snapshot data.
        """
        # document.readyState -- always "complete" since snapshot implies loaded page
        if "document.readyState" in script:
            return "complete"

        # document.body.innerText
        if "document.body.innerText" in script or "document.body.innerHTML" in script:
            return self.page_source

        # Element click via JS: arguments[0].click()
        if "arguments[0].click()" in script and args:
            elem = args[0]
            if isinstance(elem, CamofoxElement):
                elem.click()
                return None

        # For complex JS (like form extraction), return empty/None
        # The calling code should fall back to non-JS methods
        logger.debug(f"Camofox: JS execution not fully supported: {script[:80]}...")
        return None

    # ── Waits & configuration ─────────────────────────────────────────

    def implicitly_wait(self, seconds: int):
        """Set implicit wait time."""
        self._implicit_wait = seconds

    def set_window_size(self, width: int, height: int):
        """No-op for headless camofox."""
        pass

    def refresh(self):
        """Refresh the current page."""
        if self._current_url:
            self.get(self._current_url)

    def quit(self):
        """Close all tabs and clean up."""
        self.close_tab()
        logger.info("Camofox browser session closed")

    # ── Screenshot (for debugging) ────────────────────────────────────

    def take_screenshot(self, path: str) -> bool:
        """Take a screenshot and save to path."""
        if not self.tab_id:
            return False

        try:
            resp = self.session.get(
                f"{self.base_url}/tabs/{self.tab_id}/screenshot",
                params={"userId": self.user_id},
                timeout=15,
            )
            resp.raise_for_status()
            with open(path, "wb") as f:
                f.write(resp.content)
            return True
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return False


class CamofoxDriver:
    """Drop-in replacement for ChromeDriver that uses camofox-browser.

    Provides the same public interface as ronin.applier.browser.ChromeDriver
    so that SeekApplier can use it without modification.
    """

    def __init__(self, camofox_url: Optional[str] = None):
        """Initialize the CamofoxDriver.

        Args:
            camofox_url: URL of the camofox-browser server.
                         Defaults to CAMOFOX_URL env var or http://localhost:9377.
        """
        self.camofox_url = (
            camofox_url or os.environ.get("CAMOFOX_URL") or "http://localhost:9377"
        )
        self.driver: Optional[CamofoxBrowserDriver] = None
        self.is_logged_in = False
        self.user_data_dir = None
        self._login_state_file = None

    def initialize(self) -> CamofoxBrowserDriver:
        """Initialize the camofox browser driver."""
        if self.driver:
            return self.driver

        self.driver = CamofoxBrowserDriver(base_url=self.camofox_url)

        # Health check
        if not self.driver.health_check():
            raise ConnectionError(
                f"Cannot reach camofox-browser at {self.camofox_url}. "
                "Make sure the server is running: npm start (in camofox-browser dir)"
            )

        # Create initial tab
        self.driver.create_tab()
        logger.info(f"Camofox browser initialized at {self.camofox_url}")
        return self.driver

    def navigate_to(self, url: str):
        """Navigate the browser to a specific URL."""
        if not self.driver:
            self.initialize()

        logger.debug(f"Navigating to: {url}")
        self.driver.get(url)

        # Wait for page to settle (camofox handles loading internally)
        time.sleep(2)

    def wait_for_element(
        self, selector: str, by: str = "css selector", timeout: int = 10
    ):
        """Wait for an element to be present and return it."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                elements = self.driver.find_elements(by, selector)
                if elements:
                    return elements[0]
            except Exception:
                pass
            time.sleep(0.5)

        raise CamofoxTimeoutException(
            f"Element not found within {timeout}s: {by}={selector}"
        )

    def wait_for_clickable(
        self, selector: str, by: str = "css selector", timeout: int = 10
    ):
        """Wait for an element to be clickable and return it."""
        return self.wait_for_element(selector, by, timeout)

    def find_element(self, selector: str, by: str = "css selector"):
        """Find an element using the specified selector."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")
        return self.driver.find_element(by, selector)

    def find_elements(self, selector: str, by: str = "css selector"):
        """Find elements using the specified selector."""
        if not self.driver:
            raise Exception("Driver not initialized. Call initialize() first.")
        return self.driver.find_elements(by, selector)

    @property
    def current_url(self) -> str:
        """Get the current URL."""
        if not self.driver:
            raise Exception("Driver not initialized.")
        return self.driver.current_url

    @property
    def page_source(self) -> str:
        """Get the current page content."""
        if not self.driver:
            raise Exception("Driver not initialized.")
        return self.driver.page_source

    def login_seek(self):
        """Handle Seek.com.au login for headless environments.

        In ECS/headless mode, login must be handled via pre-loaded cookies
        or session tokens, not interactive browser login.
        """
        if self.is_logged_in:
            logger.debug("Already logged in (headless mode)")
            return

        # Navigate to Seek and check if cookies give us a session
        self.driver.get("https://www.seek.com.au")
        time.sleep(3)

        # Check page content for logged-in indicators
        page_text = self.driver.page_source.lower()
        logged_in_indicators = ["sign out", "account", "my activity"]

        if any(indicator in page_text for indicator in logged_in_indicators):
            self.is_logged_in = True
            logger.info("Seek login verified via camofox session")
            return

        logger.warning(
            "Camofox headless login: no active session detected. "
            "For ECS deployment, configure Seek session cookies via "
            "SEEK_SESSION_COOKIE env var or use API-based auth."
        )
        # In headless mode we can't do interactive login.
        # The caller should handle this appropriately.
        self.is_logged_in = False

    def save_login_state(self):
        """No-op for headless/ECS environments (no persistent local state)."""
        pass

    def load_login_state(self):
        """No-op for headless/ECS environments."""
        pass

    def reset_profile(self):
        """Reset browser state."""
        if self.driver:
            self.driver.close_tab()
            self.driver.create_tab()

    def cleanup(self, preserve_session: bool = True):
        """Clean up browser resources."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Camofox browser closed")
            except Exception as e:
                logger.warning(f"Error closing camofox: {e}")
            self.driver = None
