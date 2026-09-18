import os
import time
import logging
import traceback
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ==================================================
# CONFIG
# ==================================================

PHONE_NUMBER = "6284432234"
HEADLESS = False

SAVE_DRAFT_ONLY = True

COACH = {
    "team_name": "Punjab Warriors",
    "coach_name": "Vaibhav Khanna",
    "phone": "9876543210",
    "alt_phone": "9876543211",
    "email": "coach@test.com"
}

PLAYERS = [
    {
        "aadhaar": f"1234567890{i:02}",
        "dob": "01/01/2013",
        "player_name": f"Player{i}",
        "father_name": f"Father{i}",
        "mobile": f"9876543{i:04}"
    }
    for i in range(1, 13)
]

# ==================================================
# LOGGER
# ==================================================

os.makedirs("logs", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/sports.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("SPORTS")

# ==================================================
# HELPERS
# ==================================================

def screenshot(driver, name):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file = f"screenshots/{name}_{ts}.png"
    driver.save_screenshot(file)
    logger.info(f"Screenshot saved: {file}")

def click(wait, xpath, desc):
    logger.info(f"Clicking: {desc}")

    element = wait.until(
        EC.element_to_be_clickable((By.XPATH, xpath))
    )

    element.click()
    return element

def fill(wait, xpath, value, desc):
    logger.info(f"Filling {desc}: {value}")

    element = wait.until(
        EC.presence_of_element_located((By.XPATH, xpath))
    )

    element.clear()
    element.send_keys(str(value))
    return element

# ==================================================
# MAIN
# ==================================================

driver = None

try:

    options = webdriver.ChromeOptions()

    if HEADLESS:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(
        service=Service(
            ChromeDriverManager().install()
        ),
        options=options
    )

    wait = WebDriverWait(driver, 30)

    logger.info("Opening Punjab Sports Portal")

    driver.get("https://sports.punjab.gov.in/login/")
    driver.maximize_window()

    screenshot(driver, "homepage")

    # ==================================================
    # CLICK TO APPLY
    # ==================================================

    click(
        wait,
        "//*[contains(text(),'CLICK TO APPLY')]",
        "CLICK TO APPLY"
    )

    # ==================================================
    # PHONE NUMBER
    # ==================================================

    fill(
        wait,
        "//input",
        PHONE_NUMBER,
        "Phone Number"
    )

    click(
        wait,
        "//*[contains(text(),'Get OTP')]",
        "Get OTP"
    )

    logger.info(
        "OTP sent. Enter OTP manually."
    )

    input(
        "\nAfter OTP verification press ENTER..."
    )

    screenshot(driver, "after_otp")

    # ==================================================
    # ACCOUNT SELECTION
    # ==================================================

    try:

        click(
            wait,
            "//*[contains(text(),'Vaibhav')]",
            "Select Vaibhav Account"
        )

        logger.info(
            "Account selected successfully"
        )

    except Exception:

        logger.warning(
            "Could not auto-select account. Select manually."
        )

        input(
            "Select account manually then press ENTER..."
        )

    # ==================================================
    # PARTICIPATION PAGE
    # ==================================================

    logger.info(
        "Waiting for participation page"
    )

    time.sleep(5)

    screenshot(driver, "participation_page")

    # ==================================================
    # TOURNAMENT SELECTION
    # ==================================================
    # Replace these selectors with actual page selectors

    click(wait,
          "//div[@id='TOURNAMENT']",
          "Tournament Dropdown")

    click(wait,
          "//*[contains(text(),'Khedan Watan Punjab Diyan 2026')]",
          "Tournament")

    click(wait,
          "//div[@id='LEVEL']",
          "Level")

    click(wait,
          "//*[contains(text(),'District')]",
          "District")

    click(wait,
          "//div[@id='STATE']",
          "State")

    click(wait,
          "//*[contains(text(),'Punjab')]",
          "Punjab")

    click(wait,
          "//div[@id='DISTRICT']",
          "District")

    click(wait,
          "//*[contains(text(),'Amritsar')]",
          "Amritsar")

    click(wait,
          "//div[@id='GAME']",
          "Game")

    click(wait,
          "//*[contains(text(),'Basketball')]",
          "Basketball")

    click(wait,
          "//*[contains(text(),'Under 14')]",
          "Under 14")

    click(wait,
          "//label[contains(.,'Team')]",
          "Team Event")

    screenshot(driver, "selection_complete")

    # ==================================================
    # SUBMIT
    # ==================================================

    click(wait,
          "//*[contains(text(),'SUBMIT')]",
          "Submit")

    click(wait,
          "//*[contains(text(),'APPLY')]",
          "Apply")

    screenshot(driver, "apply_clicked")

    # ==================================================
    # COACH DETAILS
    # ==================================================

    fill(wait,
         "//input[contains(@placeholder,'team')]",
         COACH["team_name"],
         "Team Name")

    fill(wait,
         "//input[contains(@placeholder,'coach')]",
         COACH["coach_name"],
         "Coach Name")

    fill(wait,
         "//input[contains(@placeholder,'phone')]",
         COACH["phone"],
         "Coach Phone")

    screenshot(driver, "coach_filled")

    # ==================================================
    # PLAYERS
    # ==================================================

    for index, player in enumerate(PLAYERS):

        logger.info(
            f"Adding Player {index+1}"
        )

        aadhaar_xpath = (
            f"(//input[contains(@placeholder,'Aadhar')])[{index+1}]"
        )

        name_xpath = (
            f"(//input[contains(@placeholder,'player')])[{index+1}]"
        )

        father_xpath = (
            f"(//input[contains(@placeholder,'father')])[{index+1}]"
        )

        mobile_xpath = (
            f"(//input[contains(@placeholder,'mobile')])[{index+1}]"
        )

        fill(wait,
             aadhaar_xpath,
             player["aadhaar"],
             f"Aadhaar {index+1}")

        fill(wait,
             name_xpath,
             player["player_name"],
             f"Player Name {index+1}")

        fill(wait,
             father_xpath,
             player["father_name"],
             f"Father Name {index+1}")

        fill(wait,
             mobile_xpath,
             player["mobile"],
             f"Mobile {index+1}")

        if index < len(PLAYERS) - 1:

            try:

                click(
                    wait,
                    "//*[contains(text(),'Add Player')]",
                    "Add Player"
                )

                time.sleep(1)

            except Exception:
                logger.warning(
                    "Add Player button not found"
                )

    screenshot(driver, "players_added")

    # ==================================================
    # SAVE OR SUBMIT
    # ==================================================

    if SAVE_DRAFT_ONLY:

        click(
            wait,
            "//*[contains(text(),'Save Draft')]",
            "Save Draft"
        )

        logger.info(
            "Draft Saved Successfully"
        )

    else:

        click(
            wait,
            "//*[contains(text(),'Final Submission')]",
            "Final Submission"
        )

        logger.info(
            "Final Submission Completed"
        )

    screenshot(driver, "completed")

    input(
        "\nPress ENTER to close browser..."
    )

except Exception as e:

    logger.error(str(e))
    logger.error(traceback.format_exc())

    if driver:
        screenshot(driver, "ERROR")

finally:

    if driver:
        driver.quit()