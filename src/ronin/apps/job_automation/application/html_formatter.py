"""HTML form element extraction and formatting functionality."""

import logging
from typing import Dict, List

from selenium.webdriver.common.by import By


class HTMLFormatter:
    """Handles extraction and formatting of HTML form elements."""

    def __init__(self):
        """Initialize the HTML formatter."""
        pass

    def get_form_elements(self, driver) -> List[Dict]:
        """
        Get all form elements from the current page that need to be filled.

        Args:
            driver: Selenium WebDriver instance

        Returns:
            List of dictionaries containing information about form elements
        """
        import time

        start_time = time.time()
        elements = []

        # Temporarily reduce implicit wait to speed up searches for non-existent elements
        driver.implicitly_wait(0.5)

        forms = driver.find_elements(By.TAG_NAME, "form")
        logging.info(f"Found {len(forms)} forms on the page")

        for idx, form in enumerate(forms):
            try:
                # Check if we've been processing for too long (max 30 seconds)
                if time.time() - start_time > 30:
                    logging.warning(
                        f"Form processing timeout after {idx} forms, returning what we have"
                    )
                    break

                logging.info(f"Processing form {idx + 1}/{len(forms)}")

                # Process checkbox groups
                checkbox_elements = self._extract_checkbox_groups(form)
                elements.extend(checkbox_elements)
                logging.debug(
                    f"Found {len(checkbox_elements)} checkbox groups in form {idx + 1}"
                )

                # Process radio groups
                radio_elements = self._extract_radio_groups(form)
                elements.extend(radio_elements)
                logging.debug(
                    f"Found {len(radio_elements)} radio groups in form {idx + 1}"
                )

                # Process other form elements (inputs, selects, textareas)
                other_elements = self._extract_other_elements(form)
                elements.extend(other_elements)
                logging.debug(
                    f"Found {len(other_elements)} other elements in form {idx + 1}"
                )

            except Exception as e:
                logging.warning(f"Error processing form {idx + 1}: {str(e)}")
                continue

        # Restore implicit wait to default
        driver.implicitly_wait(10)

        elapsed = time.time() - start_time
        logging.info(
            f"Total form elements found: {len(elements)} (took {elapsed:.2f}s)"
        )
        return elements

    def _extract_checkbox_groups(self, form) -> List[Dict]:
        """Extract checkbox groups from a form."""
        import time

        start = time.time()
        checkbox_groups = {}

        # Get all checkboxes at once (faster than XPath)
        checkboxes = form.find_elements(By.CSS_SELECTOR, 'input[type="checkbox"]')
        print(f"⏱️  Found {len(checkboxes)} checkboxes in {time.time() - start:.3f}s")

        if not checkboxes:
            return []

        for checkbox in checkboxes:
            try:
                name = checkbox.get_attribute("name")
                if not name or name in checkbox_groups:
                    continue

                # Try to find the parent fieldset or container
                try:
                    container = checkbox.find_element(By.XPATH, "ancestor::fieldset[1]")
                except:
                    try:
                        container = checkbox.find_element(
                            By.XPATH, "ancestor::div[.//strong][1]"
                        )
                    except:
                        continue

                question = self._extract_question_from_container(container)
                if not question:
                    continue

                # Get all checkboxes with the same name
                group_checkboxes = [
                    cb for cb in checkboxes if cb.get_attribute("name") == name
                ]

                checkbox_groups[name] = {
                    "element": checkbox,
                    "type": "checkbox",
                    "question": question,
                    "options": [],
                }

                for cb in group_checkboxes:
                    label_text = self._extract_label_for_checkbox(container, cb)
                    checkbox_groups[name]["options"].append(
                        {
                            "id": cb.get_attribute("id"),
                            "label": label_text,
                        }
                    )
            except Exception as e:
                logging.debug(f"Error processing checkbox: {e}")
                continue

        elapsed = time.time() - start
        print(f"⏱️  Processed {len(checkbox_groups)} checkbox groups in {elapsed:.3f}s")
        return list(checkbox_groups.values())

    def _extract_radio_groups(self, form) -> List[Dict]:
        """Extract radio groups from a form."""
        import time

        start = time.time()
        radio_groups = {}
        radios = form.find_elements(By.CSS_SELECTOR, 'input[type="radio"]')
        print(f"⏱️  Found {len(radios)} radio buttons in {time.time() - start:.3f}s")

        if not radios:
            return []

        logging.debug(f"Found {len(radios)} radio buttons in form")

        for radio in radios:
            try:
                name = radio.get_attribute("name")
                if not name:
                    continue

                # Only extract question once per group
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

                label_text = self._extract_label_for_radio(form, radio)
                radio_groups[name]["options"].append(
                    {
                        "id": radio.get_attribute("id"),
                        "label": label_text,
                    }
                )
                logging.debug(
                    f"Added radio option: {label_text} (ID: {radio.get_attribute('id')})"
                )
            except Exception as e:
                logging.debug(f"Error processing radio button: {e}")
                continue

        elapsed = time.time() - start
        print(f"⏱️  Processed {len(radio_groups)} radio groups in {elapsed:.3f}s")
        return list(radio_groups.values())

    def _extract_other_elements(self, form) -> List[Dict]:
        """Extract other form elements (inputs, selects, textareas) from a form."""
        import time

        start = time.time()
        elements = []

        other_elements = form.find_elements(
            By.CSS_SELECTOR,
            "input:not([type='checkbox']):not([type='radio']):not([type='hidden']):not([type='submit']):not([type='button']), select, textarea",
        )
        print(
            f"⏱️  Found {len(other_elements)} other form elements in {time.time() - start:.3f}s"
        )

        for element in other_elements:
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
            logging.debug(
                f"Added form element: {element_info['type']} - {element_info['question'][:50]}..."
            )

        elapsed = time.time() - start
        print(f"⏱️  Processed {len(elements)} other elements in {elapsed:.3f}s")
        return elements

    def _extract_question_from_container(self, container) -> str:
        """Extract question text from a container element."""
        try:
            # Try legend strong first (most common for fieldsets)
            try:
                return container.find_element(
                    By.CSS_SELECTOR, "legend strong"
                ).text.strip()
            except:
                pass

            # Try any strong element
            try:
                return container.find_element(By.TAG_NAME, "strong").text.strip()
            except:
                pass

            # Try legend without strong
            try:
                return container.find_element(By.TAG_NAME, "legend").text.strip()
            except:
                pass

        except Exception:
            pass

        return ""

    def _extract_question_from_radio(self, radio) -> str:
        """Extract question text from a radio button element."""
        try:
            # Try to find ancestor fieldset (most common)
            try:
                fieldset = radio.find_element(By.XPATH, "ancestor::fieldset[1]")

                # Try legend strong first
                try:
                    return fieldset.find_element(
                        By.CSS_SELECTOR, "legend strong"
                    ).text.strip()
                except:
                    pass

                # Try legend
                try:
                    return fieldset.find_element(By.TAG_NAME, "legend").text.strip()
                except:
                    pass

                # Try any strong
                try:
                    return fieldset.find_element(By.TAG_NAME, "strong").text.strip()
                except:
                    pass
            except:
                pass

            # Try parent div with strong
            try:
                parent_div = radio.find_element(By.XPATH, "ancestor::div[.//strong][1]")
                return parent_div.find_element(By.TAG_NAME, "strong").text.strip()
            except:
                pass

        except Exception:
            pass

        return ""

    def _extract_label_for_checkbox(self, container, checkbox) -> str:
        """Extract label text for a checkbox element."""
        try:
            checkbox_id = checkbox.get_attribute("id")
            if checkbox_id:
                # Try CSS selector first (fastest)
                try:
                    label = container.find_element(
                        By.CSS_SELECTOR, f'label[for="{checkbox_id}"]'
                    )
                    return label.text.strip()
                except:
                    pass

            # Try parent label
            try:
                label = checkbox.find_element(By.XPATH, "ancestor::label[1]")
                return label.text.strip()
            except:
                pass

            # Try sibling label
            try:
                label = checkbox.find_element(By.XPATH, "following-sibling::label[1]")
                return label.text.strip()
            except:
                pass

        except Exception:
            pass

        return ""

    def _extract_label_for_radio(self, form, radio) -> str:
        """Extract label text for a radio button element."""
        try:
            radio_id = radio.get_attribute("id")
            if radio_id:
                # Try CSS selector first (fastest)
                try:
                    label = form.find_element(
                        By.CSS_SELECTOR, f'label[for="{radio_id}"]'
                    )
                    return label.text.strip()
                except:
                    pass

            # Try parent label
            try:
                label = radio.find_element(By.XPATH, "ancestor::label[1]")
                return label.text.strip()
            except:
                pass

            # Try following sibling label
            try:
                label = radio.find_element(By.XPATH, "following-sibling::label[1]")
                return label.text.strip()
            except:
                pass

            # Try parent's sibling label (common pattern)
            try:
                parent = radio.find_element(By.XPATH, "parent::*")
                label = parent.find_element(By.XPATH, "following-sibling::label[1]")
                text = label.text.strip()
                # Only use if reasonable length
                if text and len(text) < 100:
                    return text
            except:
                pass

        except Exception:
            pass

        return ""

    def _find_element_label(self, form, element) -> object:
        """Find the label element for a form element."""
        try:
            element_id = element.get_attribute("id")
            if element_id:
                # Try CSS selector first (fastest)
                try:
                    return form.find_element(
                        By.CSS_SELECTOR, f'label[for="{element_id}"]'
                    )
                except:
                    pass

            # Try ancestor label
            try:
                return element.find_element(By.XPATH, "ancestor::label[1]")
            except:
                pass

            # Try preceding sibling label
            try:
                return element.find_element(By.XPATH, "preceding-sibling::label[1]")
            except:
                pass

            # Try preceding strong or label
            try:
                return element.find_element(
                    By.XPATH, "preceding::*[self::strong or self::label][1]"
                )
            except:
                pass

        except Exception:
            pass

        return None

    def _extract_question_text_from_label(self, label) -> str:
        """Extract question text from a label element."""
        try:
            # First try to find strong elements within the label
            strong_elements = label.find_elements(By.TAG_NAME, "strong")
            if strong_elements:
                return strong_elements[0].text.strip()
            else:
                # Fall back to the full label text
                return label.text.strip()
        except Exception:
            return label.text.strip() if label else ""

    def _extract_select_options(self, select_element) -> List[Dict]:
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
