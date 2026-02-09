"""Form validation checking functionality."""

from loguru import logger
from selenium.webdriver.common.by import By


class ValidationChecker:
    """Handles checking for form validation errors."""

    def __init__(self):
        """Initialize the validation checker."""
        pass

    def has_validation_errors(self, driver) -> bool:
        """
        Check if the current form has validation errors.

        Args:
            driver: Selenium WebDriver instance

        Returns:
            True if validation errors are present, False otherwise
        """
        try:
            # Fast approach: check page source directly instead of DOM queries
            page_source = driver.page_source.lower()

            # Look for common validation error messages
            error_messages = [
                "please make a selection",
                "this field is required",
                "please select an option",
                "required field",
                "please choose",
            ]

            for message in error_messages:
                if message in page_source:
                    logger.warning(f"Found validation error: {message}")
                    return True

            return False
        except Exception as e:
            logger.error(f"Error checking for validation errors: {str(e)}")
            return False

    def _check_for_error_message(self, driver, message: str) -> bool:
        """
        Check for a specific error message on the page.

        Args:
            driver: Selenium WebDriver instance
            message: The error message to search for

        Returns:
            True if the error message is found, False otherwise
        """
        try:
            # Escape special characters in the message for XPATH
            escaped_message = message.replace("'", "\\'")

            # Try multiple selector strategies
            selectors = [
                f"//*[contains(text(), '{escaped_message}')]",
                f"//*[contains(normalize-space(text()), '{escaped_message}')]",
                f"//span[contains(text(), '{escaped_message}')]",
                f"//div[contains(text(), '{escaped_message}')]",
                f"//p[contains(text(), '{escaped_message}')]",
            ]

            for selector in selectors:
                try:
                    error_elements = driver.find_elements(By.XPATH, selector)
                    if error_elements:
                        return True
                except Exception as selector_error:
                    # Log the specific selector that failed but continue with others
                    logger.debug(
                        f"Selector failed: {selector}, error: {selector_error}"
                    )
                    continue

            return False
        except Exception as message_error:
            logger.debug(f"Error processing message '{message}': {message_error}")
            return False
