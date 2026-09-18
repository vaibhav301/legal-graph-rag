from playwright.sync_api import sync_playwright
from datetime import date
import logging
import traceback
import time
import re
import uuid

# ==========================================
# CONFIG
# ==========================================

PHONE = "6284432234"
import pandas as pd

EXCEL_FILE = "Students_data121212.xlsx"
MAX_PLAYERS = 12
MIN_PLAYER_AGE = 10
MAX_PLAYER_AGE = 14


def generate_mobile(student_id, used_mobiles):
    digits = "".join(ch for ch in str(student_id) if ch.isdigit())
    candidate = f"9{digits[-9:].zfill(9)}"
    while candidate in used_mobiles or candidate == "9000000000":
        candidate = f"9{uuid.uuid4().int % 1_000_000_000:09d}"
    used_mobiles.add(candidate)
    return candidate

def generate_aadhaar(student_id):
    digits = "".join(ch for ch in str(student_id) if ch.isdigit())
    return ("99" + digits.zfill(10))[-12:]

def load_players_from_excel():
    df = pd.read_excel(EXCEL_FILE)

    school_column = next(
        (
            column
            for column in df.columns
            if str(column).strip().casefold()
            in {"school", "school name", "school management", "school managment"}
        ),
        None,
    )
    if school_column is None:
        raise ValueError("Excel file must contain a School Name or School column")

    done_column = next(
        (column for column in df.columns if str(column).strip().casefold() == "done"),
        "Done",
    )
    if done_column not in df.columns:
        df[done_column] = ""

    completed = df[done_column].fillna("").astype(str).str.strip().str.casefold().isin(
        {"y", "yes", "true", "1"}
    )
    dob_values = pd.to_datetime(df["DOB"], errors="coerce").dt.date
    today = date.today()
    oldest_eligible_dob = today.replace(year=today.year - MAX_PLAYER_AGE)
    youngest_eligible_dob = today.replace(year=today.year - MIN_PLAYER_AGE)
    age_eligible = (
        dob_values.gt(oldest_eligible_dob)
        & dob_values.le(youngest_eligible_dob)
    )
    pending = df[~completed & age_eligible]

    players = []
    used_mobiles = set()

    for _, row in pending.iterrows():
        players.append(
            {
                "student_id": row["Student ID"],
                "aadhaar": generate_aadhaar(row["Student ID"]),
                "dob": pd.to_datetime(row["DOB"]).strftime("%Y-%m-%d"),
                "name": str(row["Student Name"]).strip(),
                "father": str(row["Father's Name"]).strip(),
                "mobile": generate_mobile(row["Student ID"], used_mobiles),
                "school": str(row[school_column]).strip(),
            }
        )

    return players, df

def mark_done(df, submitted_ids):
    mask = df["Student ID"].astype(str).isin(
        [str(x) for x in submitted_ids]
    )
    done_column = next(
        (column for column in df.columns if str(column).strip().casefold() == "done"),
        "Done",
    )
    if done_column not in df.columns:
        df[done_column] = ""
    df.loc[mask, done_column] = "Y"
    df.to_excel(EXCEL_FILE, index=False)
COACH_NAME = "Rajendra Kumar"
COACH_PHONE = "9000000099"

# ==========================================
# LOGGING
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("sports.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def wait_for_player_field(page, selector, index, timeout_ms=20000):
    """Wait until the nth dynamic player field is rendered."""
    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:
        try:
            count = page.locator(selector).count()
            if count > index:
                return
        except Exception:
            pass
        page.wait_for_timeout(300)

    raise TimeoutError(
        f"Field selector '{selector}' did not render enough rows for index {index}."
    )


def set_field_value(locator, value):
    """Set the value in a React-controlled input using the native setter and input events."""
    locator.evaluate(
        """
        (el, val) => {
          const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
          descriptor.set.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value,
    )


def fill_and_verify(page, locator_factory, value, label, max_retries=7, blur=False):
    """Fill a dynamic React field and confirm the current DOM node retained it."""
    for attempt in range(max_retries + 1):
        locator = locator_factory()
        locator.wait_for(state="visible", timeout=20000)
        locator.click()
        set_field_value(locator, value)
        if blur:
            locator.press("Tab")
        page.wait_for_timeout(800)

        current_value = locator_factory().input_value().strip()
        if current_value.casefold() == value.strip().casefold():
            logger.info(f"{label} retained value on attempt {attempt + 1}")
            return

        logger.warning(f"{label} value reset on attempt {attempt + 1}; retrying")
        page.wait_for_timeout(1000)

    raise RuntimeError(f"{label} did not keep the value after {max_retries + 1} attempts: {value}")


def fill_player_row(page, index, player):
    """Fill the current existing row using row-scoped selectors to avoid cross-row re-render issues."""
    row = lambda: page.locator('.team-player-content').nth(index)
    aadhaar_box = lambda: row().locator('input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]').first
    dob_box = lambda: row().locator('input[type="date"]').first
    lookup_button = lambda: row().locator('span[aria-label="Search using Aadhaar and DOB"] > button[type="button"]').first
    aadhaar_box().wait_for(state='visible', timeout=20000)
    dob_box().wait_for(state='visible', timeout=20000)

    fill_and_verify(page, aadhaar_box, player["aadhaar"], f"Aadhaar row {index + 1}", blur=True)
    fill_and_verify(page, dob_box, player["dob"], f"DOB row {index + 1}", blur=True)

    lookup_button().wait_for(state="visible", timeout=20000)
    for _ in range(20):
        if lookup_button().is_enabled():
            lookup_button().click()
            break
        page.wait_for_timeout(250)
    else:
        raise RuntimeError(f"Aadhaar/DOB lookup button remained disabled for row {index + 1}")

    # The lookup re-renders the card and may populate the player name.
    page.wait_for_timeout(3500)
    remaining_fields = {
        "Player name": lambda: row().locator('input[placeholder="Enter player name"], input[aria-label="Enter player name"]').first,
        "Father name": lambda: row().locator('input[placeholder="Enter father name"], input[aria-label="Enter father name"]').first,
        "Mobile": lambda: row().locator('input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]').first,
    }
    for label, field in remaining_fields.items():
        key = {"Player name": "name", "Father name": "father", "Mobile": "mobile"}[label]
        fill_and_verify(page, field, player[key], f"{label} row {index + 1}")


def ensure_player_rows(page, target_count):
    """Create enough player rows for the requested total while preserving already-filled rows after Add Player re-renders."""
    add_button = page.get_by_role("button", name=re.compile(r"Add Player", re.IGNORECASE))

    while page.locator('.team-player-content').count() < target_count:
        logger.info(f"Creating extra player row. Current rows: {page.locator('.team-player-content').count()} / {target_count}")
        add_button.click()
        page.wait_for_timeout(1200)


def validate_all_rows_filled(page, expected_count):
    """Ensure every existing row has all required values before proceeding to submit."""
    rows = page.locator('.team-player-content')
    count = rows.count()

    if count < expected_count:
        raise RuntimeError(f"Expected at least {expected_count} rows, found {count}.")

    for i in range(expected_count):
        row = rows.nth(i)
        aadhaar = row.locator('input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]').first
        dob = row.locator('input[type="date"]').first
        name = row.locator('input[placeholder="Enter player name"], input[aria-label="Enter player name"]').first
        father = row.locator('input[placeholder="Enter father name"], input[aria-label="Enter father name"]').first
        mobile = row.locator('input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]').first

        values = [
            aadhaar.input_value().strip(),
            dob.input_value().strip(),
            name.input_value().strip(),
            father.input_value().strip(),
            mobile.input_value().strip(),
        ]

        if any(v == "" for v in values):
            raise RuntimeError(f"Row {i + 1} is not fully filled before submit: {values}")

        logger.info(f"Validated row {i + 1} before submit: {values[2]} / {values[3]} / {values[4]}")


def save_screenshot(page, path):
    try:
        page.screenshot(path=path, full_page=True, timeout=5000)
    except Exception as error:
        logger.warning("Could not save %s: %s", path, error)


# ==========================================
# MAIN
# ==========================================

def run(otp_value=None, otp_provider=None, max_players=MAX_PLAYERS):
    players, excel_df = load_players_from_excel()
    if max_players < 1 or max_players > MAX_PLAYERS:
        raise ValueError(f"max_players must be between 1 and {MAX_PLAYERS}")
    players = players[:max_players]
    if not players:
        raise RuntimeError("No unfinished students found in the Excel file.")

    submitted = False
    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        context = browser.new_context()

        page = context.new_page()

        try:

            logger.info("Opening website")

            page.goto(
                "https://sports.punjab.gov.in/login/",
                wait_until="networkidle"
            )

            # -------------------------
            # LOGIN
            # -------------------------

            celebration_close = page.get_by_role("button", name="Close celebration message")
            if celebration_close.is_visible(timeout=3000):
                celebration_close.click()

            page.get_by_role("button", name=re.compile(r"CLICK TO APPLY|APPLY FOR PARTICIPATION", re.IGNORECASE)).first.click()

            page.get_by_role(
                "textbox",
                name="Enter 10-digit mobile number"
            ).fill(PHONE)

            page.get_by_role(
                "button",
                name="Get OTP"
            ).click()

            otp = otp_value or (otp_provider() if otp_provider else input("\nEnter OTP received on phone: ").strip())

            page.get_by_role(
                "textbox",
                name="Enter 6-digit OTP"
            ).fill(otp)

            page.get_by_role(
                "button",
                name="Verify & Continue"
            ).click()

            logger.info("OTP verified")

            # -------------------------
            # ACCOUNT
            # -------------------------

            page.get_by_role(
                "button",
                name=re.compile(r"Name: Kamlesh Username:|Kamlesh|Vaibhav", re.IGNORECASE)
            ).first.click()

            logger.info("Account selected")

            # -------------------------
            # EVENT SELECTION
            # -------------------------

            page.locator(
                "#react-select-7-input"
            ).click()

            page.get_by_role(
                "option",
                name="District"
            ).click()

            page.locator(
                "#react-select-12-input"
            ).click()

            page.get_by_role(
                "option",
                name="Amritsar"
            ).click()

            page.locator(
                "#react-select-13-input"
            ).click()

            page.get_by_role(
                "option",
                name="Handball"
            ).click()

            page.locator(
                "#react-select-16-input"
            ).click()

            page.get_by_role(
                "option",
                name="Under 14"
            ).click()

            page.get_by_role(
                "radio",
                name="Team"
            ).check()

            page.get_by_role(
                "radio",
                name="Male",
                exact=True
            ).check()

            page.get_by_role(
                "checkbox"
            ).first.check()

            logger.info("Event selected")

            page.get_by_role(
                "button",
                name="Click to apply for the"
            ).click()

            page.get_by_role(
                "button",
                name="Confirm and proceed to the"
            ).click()

            # -------------------------
            # COACH
            # -------------------------

            team_name = players[0]["school"]
            if not team_name:
                raise ValueError("School name is empty for the first player")
            page.get_by_role(
                "textbox",
                name="Enter team name"
            ).fill(team_name)

            page.get_by_role(
                "textbox",
                name="Enter coach name"
            ).fill(COACH_NAME)

            page.get_by_role(
                "textbox",
                name="Enter phone number"
            ).fill(COACH_PHONE)

            logger.info("Coach details filled")

            # -------------------------
            # PLAYERS
            # -------------------------

            ensure_player_rows(page, len(players))

            for i, player in enumerate(players):

                logger.info(
                    f"Filling existing player row {i+1}: {player['name']}"
                )

                fill_player_row(page, i, player)

            for i, player in enumerate(players):
                logger.info(f"Final re-apply for row {i + 1}: {player['name']}")
                fill_player_row(page, i, player)

            logger.info(
                "All players added"
            )
            validate_all_rows_filled(page, len(players))
            logger.info(
                "All rows validated. Ready to submit."
            )

            # -------------------------
            # FINAL SUBMIT
            # -------------------------

            save_screenshot(page, "before_submit.png")

            logger.info("All data filled. Proceeding to final submission.")

            final_submit = page.get_by_role(
                "button",
                name=re.compile(r"Final Submission|Submit.*application|Confirm.*submit|Confirm.*application", re.IGNORECASE)
            )
            final_submit.wait_for(state="visible", timeout=20000)
            final_submit.click()

            confirm_submit = page.get_by_role("button", name="Submit your application")
            try:
                confirm_submit.first.wait_for(
                    state="visible",
                    timeout=2000
                )
                confirm_submit.first.click()
            except Exception:
                logger.info("No confirmation popup")

            close_button = page.get_by_role("button", name="Close", description="Close")
            try:
                if close_button.is_visible(timeout=1000):
                    close_button.click(timeout=1000)
            except Exception:
                logger.info("No post-submit close button")

            mark_done(excel_df, [player["student_id"] for player in players])

            logger.info("Excel updated")
            submitted = True
        except Exception as error:
            logger.error(str(error))
            logger.error(traceback.format_exc())
            save_screenshot(page, "new_error.png")
        finally:
            context.close()
            browser.close()
    return submitted

if __name__ == "__main__":
    run()
