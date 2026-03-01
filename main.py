"""
Naukri Resume Headline Toggler

- All config driven by environment variables (with CLI arg fallback).
- Runs once, updates the headline, then exits cleanly (container stops itself).
- Docker-compatible: headless Chrome with anti-bot fingerprint spoofing.
"""

import logging
import os
import sys
import time
import random
import argparse

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── Config from environment ───────────────────────────────────────────────────
NAUKRI_EMAIL     = os.environ.get("NAUKRI_EMAIL", "")
NAUKRI_PASSWORD  = os.environ.get("NAUKRI_PASSWORD", "")

PROFILE_DIR = os.environ.get("PROFILE_DIR", "naukri_chrome_session")
NAUKRI_PROFILE_DIR = (
    PROFILE_DIR if os.path.isabs(PROFILE_DIR)
    else os.path.join(os.path.dirname(__file__), PROFILE_DIR)
)

CHROME_BIN       = os.environ.get("CHROME_BIN", "")
CHROMEDRIVER_BIN = os.environ.get("CHROMEDRIVER_BIN", "")

USER_AGENT = os.environ.get(
    "USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
)

PAGE_LOAD_TIMEOUT    = int(os.environ.get("PAGE_LOAD_TIMEOUT",    "60"))
ELEMENT_WAIT_TIMEOUT = int(os.environ.get("ELEMENT_WAIT_TIMEOUT", "25"))

NAUKRI_PROFILE_URL = os.environ.get("NAUKRI_PROFILE_URL", "https://www.naukri.com/mnjuser/profile")
NAUKRI_LOGIN_URL   = os.environ.get("NAUKRI_LOGIN_URL",   "https://www.naukri.com/nlogin/login")

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOG_FILE  = os.environ.get("LOG_FILE",  "/var/log/naukri.log")
# ─────────────────────────────────────────────────────────────────────────────


# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("naukri-toggler")
# ─────────────────────────────────────────────────────────────────────────────


def _banner(msg: str) -> None:
    line = "─" * 60
    logger.info(line)
    logger.info("  %s", msg)
    logger.info(line)


def get_driver(binary_override: str | None = None) -> webdriver.Chrome:
    _banner("Initializing Chrome Driver")

    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument(f"user-data-dir={NAUKRI_PROFILE_DIR}")
    logger.info("Chrome profile dir  : %s", NAUKRI_PROFILE_DIR)

    # Headless / Docker flags
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    logger.debug("Headless mode enabled")

    # Anti-bot / anti-fingerprint flags
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--lang=en-US,en;q=0.9")
    logger.info("User-agent          : %s", USER_AGENT)
    logger.debug("Anti-detection flags applied")

    # Resolve Chrome binary
    chrome_candidates = [
        binary_override, CHROME_BIN,
        "/usr/bin/google-chrome", "/usr/bin/chromium",
        "/usr/bin/chromium-browser", "/opt/google/chrome/google-chrome",
    ]
    for candidate in chrome_candidates:
        if candidate and os.path.isfile(candidate):
            options.binary_location = candidate
            logger.info("Chrome binary       : %s", candidate)
            break
    else:
        logger.warning("Chrome binary not found in known paths — Selenium will auto-detect")

    # Resolve ChromeDriver
    driver_candidates = [
        CHROMEDRIVER_BIN,
        "/usr/bin/chromedriver", "/usr/local/bin/chromedriver",
        "/home/seluser/venv/bin/chromedriver",
    ]
    service = None
    for candidate in driver_candidates:
        if candidate and os.path.isfile(candidate):
            service = Service(executable_path=candidate)
            logger.info("ChromeDriver        : %s", candidate)
            break
    else:
        logger.warning("ChromeDriver not found in known paths — Selenium will auto-detect")

    logger.info("Page load timeout   : %ss", PAGE_LOAD_TIMEOUT)
    logger.info("Element wait timeout: %ss", ELEMENT_WAIT_TIMEOUT)

    logger.debug("Launching Chrome process...")
    driver = (
        webdriver.Chrome(service=service, options=options)
        if service else webdriver.Chrome(options=options)
    )
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

    # Patch navigator.webdriver fingerprint via CDP
    logger.debug("Patching navigator.webdriver via CDP...")
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """
    })

    logger.info("Chrome driver ready ✓")
    return driver


def _wait(driver: webdriver.Chrome, timeout: int | None = None) -> WebDriverWait:
    return WebDriverWait(driver, timeout or ELEMENT_WAIT_TIMEOUT)


def _human_pause(min_s: float = 1.0, max_s: float = 2.5) -> None:
    delay = random.uniform(min_s, max_s)
    logger.debug("Human pause: %.2fs", delay)
    time.sleep(delay)


def close_overlays(driver: webdriver.Chrome) -> None:
    logger.debug("Scanning for overlays/popups...")
    selectors = [
        "//div[contains(@class,'lightbox')]//div[contains(@class,'crossLayer')]",
        "//div[contains(@class,'close') and contains(@class,'ltCont')]",
        "//button[contains(.,'Close') or contains(.,'Got it') or contains(.,'No, thanks') or contains(.,'Cancel')]",
        "//span[contains(.,'CrossLayer')]",
    ]
    closed = 0
    for sel in selectors:
        try:
            for el in driver.find_elements(By.XPATH, sel):
                if el.is_displayed():
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    closed += 1
                    time.sleep(0.3)
        except Exception:
            pass
    if closed:
        logger.info("Dismissed %d overlay(s)", closed)
    else:
        logger.debug("No overlays found")


def is_logged_in(driver: webdriver.Chrome) -> bool:
    _banner("Checking Login Status")
    _human_pause(1.0, 2.0)
    logger.info("Navigating to: %s", NAUKRI_PROFILE_URL)
    driver.get(NAUKRI_PROFILE_URL)
    logger.debug("Waiting for page body...")
    _wait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(2)
    close_overlays(driver)
    current_url = driver.current_url
    page_title  = driver.title
    logged_in   = "nlogin" not in current_url
    logger.info("Current URL  : %s", current_url)
    logger.info("Page title   : %s", page_title)
    logger.info("Login status : %s", "✓ LOGGED IN" if logged_in else "✗ NOT LOGGED IN")
    return logged_in


def attempt_login(driver: webdriver.Chrome, email: str, password: str) -> None:
    _banner("Attempting Login")
    logger.info("Navigating to: %s", NAUKRI_LOGIN_URL)
    driver.get(NAUKRI_LOGIN_URL)
    _wait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    logger.info("Login page loaded — title: %s", driver.title)

    email_xpaths = [
        "//input[contains(@placeholder,'Email') or contains(@placeholder,'email')]",
        "//input[contains(@name,'email')]",
        "//input[contains(@id,'email') or contains(@id,'Email')]",
        "//input[contains(@type,'email')]",
        "//input[contains(@autocomplete,'email') or contains(@autocomplete,'username')]",
        "(//form//input[not(@type='password') and not(@type='hidden') and not(@type='submit')])[1]",
    ]
    password_xpaths = [
        "//input[@type='password']",
        "//input[contains(@name,'password')]",
        "//input[contains(@id,'password') or contains(@id,'Password')]",
        "//input[contains(@placeholder,'Password') or contains(@placeholder,'password')]",
    ]
    submit_xpaths = [
        "//button[@type='submit']",
        "//button[contains(.,'Login') or contains(.,'Sign in') or contains(.,'Log in')]",
        "//input[@type='submit']",
        "(//form//button)[last()]",
    ]

    def find_first(xpaths, label):
        for xp in xpaths:
            try:
                el = _wait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xp)))
                if el.is_displayed():
                    logger.debug("Located %s field via: %s", label, xp)
                    return el
            except TimeoutException:
                logger.debug("Not found (%s): %s", label, xp)
        return None

    logger.info("Waiting for login form to render...")
    time.sleep(3)

    logger.info("Locating form fields...")
    email_el  = find_first(email_xpaths,    "email")
    pwd_el    = find_first(password_xpaths, "password")
    submit_el = find_first(submit_xpaths,   "submit")

    if not email_el or not pwd_el or not submit_el:
        logger.error("Page source snippet:\n%s", driver.page_source[:2000])
        raise RuntimeError(
            f"Login form fields not found — "
            f"email={'✓' if email_el else '✗'}  "
            f"password={'✓' if pwd_el else '✗'}  "
            f"submit={'✓' if submit_el else '✗'}"
        )

    logger.info("Filling email...")
    email_el.clear()
    _human_pause(0.3, 0.6)
    email_el.send_keys(email)

    logger.info("Filling password...")
    pwd_el.clear()
    _human_pause(0.3, 0.6)
    pwd_el.send_keys(password)

    logger.info("Submitting form...")
    _human_pause(0.4, 0.8)
    try:
        submit_el.click()
    except ElementClickInterceptedException:
        logger.warning("Click intercepted — retrying via JS")
        driver.execute_script("arguments[0].click();", submit_el)

    logger.info("Waiting for post-login redirect...")
    try:
        _wait(driver, 20).until(EC.url_contains("mnjuser"))
        logger.info("Login successful ✓ — URL: %s", driver.current_url)
    except TimeoutException:
        logger.error("Login redirect timed out — URL: %s | title: %s", driver.current_url, driver.title)
        raise RuntimeError(
            "Login failed or OTP/captcha required. "
            "Manual intervention needed or session cookies may have expired."
        )


def open_resume_headline_editor(driver: webdriver.Chrome) -> None:
    _banner("Opening Headline Editor")
    logger.info("Navigating to profile page: %s", NAUKRI_PROFILE_URL)
    driver.get(NAUKRI_PROFILE_URL)
    _wait(driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    logger.info("Profile page loaded — title: %s", driver.title)
    _human_pause(1.5, 2.5)
    close_overlays(driver)

    edit_xpaths = [
        "(//*[self::h2 or self::div or self::span][contains(translate(normalize-space(.),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'resume headline')])[1]"
        "/ancestor::*[self::section or self::div][1]"
        "//*[self::a or self::button or self::span][contains(translate(normalize-space(.),"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit')][1]",

        "//div[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'resume')"
        " and contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'headline')]"
        "//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit')][1]",

        "(//button[contains(.,'Edit')] | //a[contains(.,'Edit')] | //span[contains(.,'Edit')])[1]",
    ]

    edit_btn = None
    for i, xp in enumerate(edit_xpaths):
        logger.debug("Trying edit-button strategy [%d/%d]", i + 1, len(edit_xpaths))
        try:
            candidate = _wait(driver, 15).until(EC.element_to_be_clickable((By.XPATH, xp)))
            if candidate and candidate.is_displayed():
                logger.info("Edit button found via strategy [%d]", i + 1)
                edit_btn = candidate
                break
        except TimeoutException:
            logger.debug("Strategy [%d] timed out", i + 1)

    if not edit_btn:
        logger.error("Edit button not found. Page snippet:\n%s", driver.page_source[:800])
        raise RuntimeError("Could not locate Resume headline edit button.")

    _human_pause(0.3, 0.7)
    logger.info("Clicking edit button...")
    try:
        edit_btn.click()
    except ElementClickInterceptedException:
        logger.warning("Click intercepted — retrying via JS")
        driver.execute_script("arguments[0].click();", edit_btn)

    logger.info("Waiting for editor drawer...")
    _wait(driver, 20).until(EC.presence_of_element_located((By.XPATH,
        "//div[contains(@class,'resumeHeadlineEdit') "
        "or contains(@class,'profileEditDrawer') "
        "or contains(@class,'lightbox')]"
    )))
    time.sleep(0.5)
    logger.info("Headline editor drawer open ✓")


def get_headline_field(driver: webdriver.Chrome):
    logger.info("Locating headline textarea...")
    field_xpaths = [
        "(//div[contains(@class,'resumeHeadlineEdit') or contains(@class,'profileEditDrawer') or contains(@class,'lightbox')]//textarea)[1]",
        "(//textarea[contains(@placeholder,'headline') or contains(@id,'headline') or contains(@name,'headline')])[1]",
        "(//div[(@contenteditable='true' or contains(@role,'textbox')) and ancestor::div[contains(@class,'resumeHeadlineEdit') or contains(@class,'profileEditDrawer') or contains(@class,'lightbox')]])[1]",
    ]
    for i, xp in enumerate(field_xpaths):
        logger.debug("Trying field strategy [%d/%d]", i + 1, len(field_xpaths))
        try:
            el = _wait(driver, 15).until(EC.presence_of_element_located((By.XPATH, xp)))
            if el.is_displayed():
                logger.info("Headline field found via strategy [%d] (tag: <%s>)", i + 1, el.tag_name)
                return el
        except TimeoutException:
            logger.debug("Strategy [%d] timed out", i + 1)
    raise RuntimeError("Could not find headline input field inside the editor drawer.")


def read_field_value(driver: webdriver.Chrome, el) -> str:
    tag = el.tag_name.lower()
    value = (
        (el.get_attribute("value") or "") if tag in ("textarea", "input")
        else (el.text or "")
    ).strip("\n")
    logger.info("Current headline (%d chars): '%s'", len(value), value)
    return value


def set_field_value(driver: webdriver.Chrome, el, value: str) -> None:
    tag = el.tag_name.lower()
    logger.info("Writing new headline (%d chars): '%s'", len(value), value)
    if tag in ("textarea", "input"):
        el.click()
        _human_pause(0.2, 0.4)
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.DELETE)
        _human_pause(0.1, 0.3)
        el.send_keys(value)
    else:
        driver.execute_script("arguments[0].innerText = arguments[1];", el, value)
    logger.debug("Field value written")


def find_and_click_save(driver: webdriver.Chrome) -> None:
    logger.info("Looking for Save button...")
    save_xpaths = [
        "(//div[contains(@class,'resumeHeadlineEdit') or contains(@class,'profileEditDrawer') or contains(@class,'lightbox')]//button[normalize-space()='Save'])[1]",
        "(//button[contains(.,'Save')])[1]",
        "(//a[contains(.,'Save')])[1]",
    ]
    for i, xp in enumerate(save_xpaths):
        logger.debug("Trying save-button strategy [%d/%d]", i + 1, len(save_xpaths))
        try:
            btn = _wait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xp)))
            logger.info("Save button found via strategy [%d]", i + 1)
            _human_pause(0.3, 0.6)
            try:
                btn.click()
            except ElementClickInterceptedException:
                logger.warning("Click intercepted — retrying via JS")
                driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.8)
            logger.info("Save button clicked ✓")
            return
        except TimeoutException:
            logger.debug("Strategy [%d] timed out", i + 1)
    raise RuntimeError("Save button not found in the editor drawer.")


def toggle_trailing_period(text: str) -> str:
    stripped = (text or "").rstrip()
    if stripped.endswith("."):
        result = stripped[:-1]
        action = "removed trailing period (.)"
    else:
        result = stripped + "."
        action = "added trailing period (.)"
    logger.info("Toggle action: %s", action)
    logger.debug("Before: '%s'", stripped)
    logger.debug("After : '%s'", result)
    return result


def run(email: str, password: str, binary: str | None) -> int:
    _banner("Naukri Headline Toggler — Starting Run")
    logger.info("Profile dir          : %s", NAUKRI_PROFILE_DIR)
    logger.info("Profile URL          : %s", NAUKRI_PROFILE_URL)
    logger.info("Login URL            : %s", NAUKRI_LOGIN_URL)
    logger.info("Page load timeout    : %ss", PAGE_LOAD_TIMEOUT)
    logger.info("Element wait timeout : %ss", ELEMENT_WAIT_TIMEOUT)
    logger.info("Log level            : %s", LOG_LEVEL)
    logger.info("Log file             : %s", LOG_FILE)

    driver = get_driver(binary)
    try:
        if not is_logged_in(driver):
            if not email or not password:
                raise RuntimeError(
                    "Not logged in and no credentials provided. "
                    "Set NAUKRI_EMAIL and NAUKRI_PASSWORD env vars."
                )
            attempt_login(driver, email, password)
            _human_pause(1.5, 2.5)
        else:
            logger.info("Active session found — skipping login")

        open_resume_headline_editor(driver)

        field   = get_headline_field(driver)
        current = read_field_value(driver, field)
        updated = toggle_trailing_period(current)

        if current == updated:
            logger.info("Headline already in desired state — nothing to update")
        else:
            set_field_value(driver, field, updated)
            find_and_click_save(driver)
            _human_pause(0.8, 1.5)
            logger.info("Headline updated and saved ✓")

        _banner("Run Completed Successfully ✓")
        return 0

    except Exception as e:
        logger.exception("Run failed: %s", e)
        _banner("Run FAILED ✗")
        return 1

    finally:
        logger.info("Shutting down Chrome driver...")
        try:
            driver.quit()
            logger.info("Chrome driver stopped ✓")
        except Exception as ex:
            logger.warning("Error stopping driver: %s", ex)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Naukri Resume Headline Toggler",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--email",    default=NAUKRI_EMAIL,    help="Naukri email    [env: NAUKRI_EMAIL]")
    parser.add_argument("--password", default=NAUKRI_PASSWORD, help="Naukri password [env: NAUKRI_PASSWORD]")
    parser.add_argument("--binary",   default=None,            help="Chrome binary   [env: CHROME_BIN]")
    parser.add_argument("--debug",    action="store_true",     help="Force DEBUG log level [env: LOG_LEVEL=DEBUG]")
    args = parser.parse_args()

    if args.debug or LOG_LEVEL == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")

    sys.exit(run(args.email, args.password, args.binary))