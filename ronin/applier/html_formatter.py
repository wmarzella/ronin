"""HTML form element extraction and formatting functionality."""

import time
from typing import Dict, List, Optional

from loguru import logger
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class HTMLFormatter:
    """Handles extraction and formatting of HTML form elements."""

    def __init__(self):
        """Initialize the HTML formatter."""
        pass

    def get_form_elements(self, driver: WebDriver) -> List[Dict]:
        """
        Get all form elements from the current page that need to be filled.

        Args:
            driver: Selenium WebDriver instance

        Returns:
            List of dictionaries containing information about form elements
        """
        start_time = time.time()
        elements = []

        # Use explicit wait instead of manipulating implicit wait
        wait = WebDriverWait(driver, 0.5)

        forms = driver.find_elements(By.TAG_NAME, "form")
        logger.debug(f"Found {len(forms)} forms on the page")

        for idx, form in enumerate(forms):
            try:
                # Check if we've been processing for too long (max 30 seconds)
                if time.time() - start_time > 30:
                    logger.warning(
                        f"Form processing timeout after {idx} forms, returning what we have"
                    )
                    break

                logger.debug(f"Processing form {idx + 1}/{len(forms)}")

                # Process checkbox groups
                checkbox_elements = self._extract_checkbox_groups(form)
                elements.extend(checkbox_elements)

                # Process radio groups
                radio_elements = self._extract_radio_groups(form)
                elements.extend(radio_elements)

                # Process other form elements (inputs, selects, textareas)
                other_elements = self._extract_other_elements(form)
                elements.extend(other_elements)

            except (NoSuchElementException, StaleElementReferenceException) as e:
                logger.warning(f"Error processing form {idx + 1}: {e}")
                continue

        elapsed = time.time() - start_time
        logger.info(f"Total form elements found: {len(elements)} (took {elapsed:.2f}s)")
        return elements

    def _extract_checkbox_groups(self, form: WebElement) -> List[Dict]:
        """Extract checkbox groups from a form using fast JS extraction."""
        start = time.time()

        # Get the driver from the form element
        driver = form.parent

        # Use JavaScript to extract all checkbox data in one call - much faster than XPath
        js_script = """
        const form = arguments[0];
        const checkboxes = form.querySelectorAll('input[type="checkbox"]');
        const groups = {};

        checkboxes.forEach(cb => {
            const name = cb.name;
            if (!name) return;

            if (!groups[name]) {
                // Find container (fieldset or div with strong)
                let container = cb.closest('fieldset');
                if (!container) {
                    container = cb.closest('div');
                    while (container && !container.querySelector('strong')) {
                        container = container.parentElement;
                        if (container === form) { container = null; break; }
                    }
                }

                if (!container) return;

                // Get question text
                let question = '';
                const legend = container.querySelector('legend strong') || container.querySelector('legend');
                if (legend) {
                    question = legend.textContent.trim();
                } else {
                    const strong = container.querySelector('strong');
                    if (strong) question = strong.textContent.trim();
                }

                if (!question) return;

                groups[name] = {
                    question: question,
                    options: []
                };
            }

            // Get label for this checkbox
            // The input and label are siblings within a container div
            // Walk up to find a div that contains both the input and a label for it
            let labelText = '';
            if (cb.id) {
                // Start from immediate parent and walk up until we find the label
                let searchContainer = cb.parentElement;
                for (let i = 0; i < 5 && searchContainer && !labelText; i++) {
                    const label = searchContainer.querySelector('label[for="' + cb.id + '"]');
                    if (label) {
                        labelText = label.textContent.trim();
                        break;
                    }
                    searchContainer = searchContainer.parentElement;
                }
            }

            groups[name].options.push({
                id: cb.id,
                label: labelText
            });
        });

        return groups;
        """

        try:
            js_groups = driver.execute_script(js_script, form)
        except Exception as e:
            logger.warning(
                f"JS checkbox extraction failed: {e}, falling back to slow method"
            )
            return self._extract_checkbox_groups_slow(form)

        if not js_groups:
            return []

        # Convert JS result to our format, attaching Selenium elements
        checkbox_groups = {}
        checkboxes = form.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')
        checkbox_by_name = {}
        for cb in checkboxes:
            name = cb.get_attribute("name")
            if name and name not in checkbox_by_name:
                checkbox_by_name[name] = cb

        for name, data in js_groups.items():
            if name in checkbox_by_name:
                checkbox_groups[name] = {
                    "element": checkbox_by_name[name],
                    "type": "checkbox",
                    "question": data["question"],
                    "options": data["options"],
                }

        elapsed = time.time() - start
        logger.debug(
            f"Processed {len(checkbox_groups)} checkbox groups in {elapsed:.3f}s"
        )
        return list(checkbox_groups.values())

    def _extract_checkbox_groups_slow(self, form: WebElement) -> List[Dict]:
        """Fallback slow method for checkbox extraction."""
        start = time.time()
        checkbox_groups = {}
        checkboxes = form.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')

        if not checkboxes:
            return []

        names_seen = set()
        for checkbox in checkboxes:
            try:
                name = checkbox.get_attribute("name")
                if not name or name in names_seen:
                    continue
                names_seen.add(name)

                container = self._find_checkbox_container(checkbox)
                if not container:
                    continue

                question = self._extract_question_from_container(container)
                if not question:
                    continue

                group_cbs = [
                    cb for cb in checkboxes if cb.get_attribute("name") == name
                ]
                checkbox_groups[name] = {
                    "element": checkbox,
                    "type": "checkbox",
                    "question": question,
                    "options": [],
                }

                for cb in group_cbs:
                    cb_id = cb.get_attribute("id")
                    label_text = ""
                    if cb_id:
                        try:
                            label = container.find_element(
                                By.CSS_SELECTOR, f'label[for="{cb_id}"]'
                            )
                            label_text = label.text.strip()
                        except NoSuchElementException:
                            pass
                    checkbox_groups[name]["options"].append(
                        {"id": cb_id, "label": label_text}
                    )
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        elapsed = time.time() - start
        logger.debug(
            f"Processed {len(checkbox_groups)} checkbox groups (slow) in {elapsed:.3f}s"
        )
        return list(checkbox_groups.values())

    def _find_checkbox_container(self, checkbox: WebElement) -> Optional[WebElement]:
        """Find the container element for a checkbox."""
        try:
            return checkbox.find_element(By.XPATH, "ancestor::fieldset[1]")
        except NoSuchElementException:
            pass

        try:
            return checkbox.find_element(By.XPATH, "ancestor::div[.//strong][1]")
        except NoSuchElementException:
            pass

        return None

    def _extract_radio_groups(self, form: WebElement) -> List[Dict]:
        """Extract radio groups from a form using fast JS extraction."""
        start = time.time()
        driver = form.parent

        js_script = """
        const form = arguments[0];
        const radios = form.querySelectorAll('input[type="radio"]');
        const groups = {};

        radios.forEach(radio => {
            const name = radio.name;
            if (!name) return;

            if (!groups[name]) {
                let container = radio.closest('fieldset');
                if (!container) {
                    container = radio.closest('div');
                    while (container && !container.querySelector('strong')) {
                        container = container.parentElement;
                        if (container === form) { container = null; break; }
                    }
                }

                if (!container) return;

                let question = '';
                const legend = container.querySelector('legend strong') || container.querySelector('legend');
                if (legend) {
                    question = legend.textContent.trim();
                } else {
                    const strong = container.querySelector('strong');
                    if (strong) question = strong.textContent.trim();
                }

                if (!question) return;

                groups[name] = { question: question, options: [] };
            }

            let labelText = '';
            if (radio.id) {
                const label = form.querySelector('label[for="' + radio.id + '"]');
                if (label) labelText = label.textContent.trim();
            }

            groups[name].options.push({ id: radio.id, label: labelText });
        });

        return groups;
        """

        try:
            js_groups = driver.execute_script(js_script, form)
        except Exception as e:
            logger.warning(f"JS radio extraction failed: {e}")
            return self._extract_radio_groups_slow(form)

        if not js_groups:
            return []

        radio_groups = {}
        radios = form.find_elements(By.CSS_SELECTOR, 'input[type="radio"]')
        radio_by_name = {}
        for r in radios:
            name = r.get_attribute("name")
            if name and name not in radio_by_name:
                radio_by_name[name] = r

        for name, data in js_groups.items():
            if name in radio_by_name:
                radio_groups[name] = {
                    "element": radio_by_name[name],
                    "type": "radio",
                    "question": data["question"],
                    "options": data["options"],
                }

        elapsed = time.time() - start
        logger.debug(f"Processed {len(radio_groups)} radio groups in {elapsed:.3f}s")
        return list(radio_groups.values())

    def _extract_radio_groups_slow(self, form: WebElement) -> List[Dict]:
        """Fallback slow method for radio extraction."""
        start = time.time()
        radio_groups = {}
        radios = form.find_elements(By.CSS_SELECTOR, 'input[type="radio"]')

        if not radios:
            return []

        for radio in radios:
            try:
                name = radio.get_attribute("name")
                if not name:
                    continue

                if name not in radio_groups:
                    question = self._extract_question_from_radio(radio)
                    if not question:
                        continue
                    radio_groups[name] = {
                        "element": radio,
                        "type": "radio",
                        "question": question,
                        "options": [],
                    }

                r_id = radio.get_attribute("id")
                label_text = ""
                if r_id:
                    try:
                        label = form.find_element(
                            By.CSS_SELECTOR, f'label[for="{r_id}"]'
                        )
                        label_text = label.text.strip()
                    except NoSuchElementException:
                        pass

                radio_groups[name]["options"].append({"id": r_id, "label": label_text})
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        elapsed = time.time() - start
        logger.debug(
            f"Processed {len(radio_groups)} radio groups (slow) in {elapsed:.3f}s"
        )
        return list(radio_groups.values())

    def _extract_other_elements(self, form: WebElement) -> List[Dict]:
        """Extract other form elements (inputs, selects, textareas) from a form."""
        start = time.time()
        elements = []

        other_elements = form.find_elements(
            By.CSS_SELECTOR,
            "input:not([type='checkbox']):not([type='radio']):not([type='hidden']):not([type='submit']):not([type='button']), select, textarea",
        )
        logger.debug(
            f"Found {len(other_elements)} other form elements in {time.time() - start:.3f}s"
        )

        for element in other_elements:
            try:
                element_type = element.get_attribute("type")
                if element_type == "select-one":
                    element_type = "select"

                label = self._find_element_label(form, element)
                if not label:
                    continue

                question_text = self._extract_question_text_from_label(label)
                if not question_text:
                    continue

                element_info = {
                    "element": element,
                    "type": element_type or element.tag_name,
                    "question": question_text,
                }

                if element.tag_name == "select":
                    options = self._extract_select_options(element)
                    element_info["options"] = options

                elements.append(element_info)
            except (NoSuchElementException, StaleElementReferenceException) as e:
                logger.debug(f"Error processing form element: {e}")
                continue

        elapsed = time.time() - start
        logger.debug(f"Processed {len(elements)} other elements in {elapsed:.3f}s")
        return elements

    def _extract_question_from_container(self, container: WebElement) -> str:
        """Extract question text from a container element."""
        # Try legend strong first (most common for fieldsets)
        try:
            return container.find_element(By.CSS_SELECTOR, "legend strong").text.strip()
        except NoSuchElementException:
            pass

        # Try any strong element
        try:
            return container.find_element(By.TAG_NAME, "strong").text.strip()
        except NoSuchElementException:
            pass

        # Try legend without strong
        try:
            return container.find_element(By.TAG_NAME, "legend").text.strip()
        except NoSuchElementException:
            pass

        return ""

    def _extract_question_from_radio(self, radio: WebElement) -> str:
        """Extract question text from a radio button element."""
        # Try to find ancestor fieldset (most common)
        try:
            fieldset = radio.find_element(By.XPATH, "ancestor::fieldset[1]")

            # Try legend strong first
            try:
                return fieldset.find_element(
                    By.CSS_SELECTOR, "legend strong"
                ).text.strip()
            except NoSuchElementException:
                pass

            # Try legend
            try:
                return fieldset.find_element(By.TAG_NAME, "legend").text.strip()
            except NoSuchElementException:
                pass

            # Try any strong
            try:
                return fieldset.find_element(By.TAG_NAME, "strong").text.strip()
            except NoSuchElementException:
                pass
        except NoSuchElementException:
            pass

        # Try parent div with strong
        try:
            parent_div = radio.find_element(By.XPATH, "ancestor::div[.//strong][1]")
            return parent_div.find_element(By.TAG_NAME, "strong").text.strip()
        except NoSuchElementException:
            pass

        return ""

    def _extract_label_for_checkbox(
        self, container: WebElement, checkbox: WebElement
    ) -> str:
        """Extract label text for a checkbox element."""
        checkbox_id = checkbox.get_attribute("id")
        if checkbox_id:
            try:
                label = container.find_element(
                    By.CSS_SELECTOR, f'label[for="{checkbox_id}"]'
                )
                return label.text.strip()
            except NoSuchElementException:
                pass

        # Try parent label
        try:
            label = checkbox.find_element(By.XPATH, "ancestor::label[1]")
            return label.text.strip()
        except NoSuchElementException:
            pass

        # Try sibling label
        try:
            label = checkbox.find_element(By.XPATH, "following-sibling::label[1]")
            return label.text.strip()
        except NoSuchElementException:
            pass

        return ""

    def _extract_label_for_radio(self, form: WebElement, radio: WebElement) -> str:
        """Extract label text for a radio button element."""
        radio_id = radio.get_attribute("id")
        if radio_id:
            try:
                label = form.find_element(By.CSS_SELECTOR, f'label[for="{radio_id}"]')
                return label.text.strip()
            except NoSuchElementException:
                pass

        # Try parent label
        try:
            label = radio.find_element(By.XPATH, "ancestor::label[1]")
            return label.text.strip()
        except NoSuchElementException:
            pass

        # Try following sibling label
        try:
            label = radio.find_element(By.XPATH, "following-sibling::label[1]")
            return label.text.strip()
        except NoSuchElementException:
            pass

        # Try parent's sibling label (common pattern)
        try:
            parent = radio.find_element(By.XPATH, "parent::*")
            label = parent.find_element(By.XPATH, "following-sibling::label[1]")
            text = label.text.strip()
            if text and len(text) < 100:
                return text
        except NoSuchElementException:
            pass

        return ""

    def _find_element_label(
        self, form: WebElement, element: WebElement
    ) -> Optional[WebElement]:
        """Find the label element for a form element."""
        element_id = element.get_attribute("id")
        if element_id:
            try:
                return form.find_element(By.CSS_SELECTOR, f'label[for="{element_id}"]')
            except NoSuchElementException:
                pass

        # Try ancestor label
        try:
            return element.find_element(By.XPATH, "ancestor::label[1]")
        except NoSuchElementException:
            pass

        # Try preceding sibling label
        try:
            return element.find_element(By.XPATH, "preceding-sibling::label[1]")
        except NoSuchElementException:
            pass

        # Try preceding strong or label
        try:
            return element.find_element(
                By.XPATH, "preceding::*[self::strong or self::label][1]"
            )
        except NoSuchElementException:
            pass

        return None

    def _extract_question_text_from_label(self, label: WebElement) -> str:
        """Extract question text from a label element."""
        try:
            strong_elements = label.find_elements(By.TAG_NAME, "strong")
            if strong_elements:
                return strong_elements[0].text.strip()
            return label.text.strip()
        except (NoSuchElementException, StaleElementReferenceException):
            return label.text.strip() if label else ""

    def _extract_select_options(self, select_element: WebElement) -> List[Dict]:
        """Extract options from a select element."""
        options = []
        for option in select_element.find_elements(By.TAG_NAME, "option"):
            value = option.get_attribute("value")
            if value:
                options.append(
                    {
                        "value": value,
                        "label": option.text.strip(),
                    }
                )
        return options
