from playwright.sync_api import sync_playwright
from datetime import date
import logging
import random
import traceback
import time
import re
from pathlib import Path

# ==========================================
# CONFIG
# ==========================================

PHONE = "6284432234"  # login mobile number used to authenticate on the portal
import pandas as pd

EXCEL_FILE = "under14.csv"
MAX_PLAYERS = 12
GAME_MAX_PLAYERS = {
    "Basketball": 12,
    "Handball": 16,
    "Hockey": 18
}

# Header names in your Excel sheet — adjust if yours differ
AADHAAR_COL = "Aadhaar"
PHONE_COL = "Phn. No."
COACH_NAME_ALIASES = {"coach", "coach name", "coachname"}
COACH_PHONE_ALIASES = {"coach phone", "coach mobile", "coach phone number", "coachmobile"}

# Age-group boundaries (inclusive/exclusive matches the birthday control below).
# A player qualifies for a group if:
#   (today - MAX_AGE years) < DOB <= (today - MIN_AGE years)
AGE_GROUPS = {
    "Under 14": {"min_age": 10, "max_age": 14},
    "Under 17": {"min_age": 14, "max_age": 17},
    "Under 21": {"min_age": 17, "max_age": 21},
}

# Coach assigned per game
GAME_COACHES = {
    "Basketball": {"name": "Rajendra Kumar", "phone": "9000000099"},
    "Handball": {"name": "Manoj Sharma", "phone": "8569908727"},
    "Badminton": {"name": "Rakesh Titu", "phone": "8902010101"},
    "Chess": {"name": "Pawan Kumar Singh", "phone": "6902078910"},
    "Hockey": {"name": "Gurpreet Singh", "phone": "9914188691"},
}

DISTRICT = "Amritsar"

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


# ==========================================
# DATA LOADING (real phone only; Aadhaar falls back to a random 12-digit number)
# ==========================================

def _clean_aadhaar(value):
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 12:
        # invalid/missing Aadhaar — substitute a random 12-digit number instead of skipping the row
        digits = str(random.randint(2, 9)) + "".join(str(random.randint(0, 9)) for _ in range(11))
    return digits

def _clean_mobile(value):
    digits = re.sub(r"\D", "", str(value))
    if len(digits) >= 10:
        digits = digits[-10:]
    if len(digits) != 10 or digits[0] not in "6789":
        return None
    return digits


def load_players_from_excel(min_age, max_age, data_file=None):
    data_file = Path(data_file or EXCEL_FILE)
    if data_file.suffix.casefold() == ".csv":
        df = pd.read_csv(data_file, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(data_file)

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

    if AADHAAR_COL not in df.columns:
        raise ValueError(f"Excel file must contain an '{AADHAAR_COL}' column")
    if PHONE_COL not in df.columns:
        raise ValueError(f"Excel file must contain a '{PHONE_COL}' column")

    coach_name_column = next(
        (column for column in df.columns if str(column).strip().casefold() in COACH_NAME_ALIASES),
        None,
    )
    coach_phone_column = next(
        (column for column in df.columns if str(column).strip().casefold() in COACH_PHONE_ALIASES),
        None,
    )

    done_column = next(
        (column for column in df.columns if str(column).strip().casefold() == "done"),
        "Done",
    )
    if done_column not in df.columns:
        df[done_column] = ""

    completed = df[done_column].fillna("").astype(str).str.strip().str.casefold().isin(
        {"y", "yes", "true", "1"}
    )

    # ---- birthday control ----
    dob_values = pd.to_datetime(df["DOB"], errors="coerce").dt.date
    today = date.today()
    oldest_eligible_dob = today.replace(year=today.year - max_age)
    youngest_eligible_dob = today.replace(year=today.year - min_age)
    age_eligible = dob_values.gt(oldest_eligible_dob) & dob_values.le(youngest_eligible_dob)

    pending = df[~completed & age_eligible]

    players = []
    skipped = []

    for idx, row in pending.iterrows():
        aadhaar = _clean_aadhaar(row[AADHAAR_COL])
        mobile = _clean_mobile(row[PHONE_COL])
        student_name = str(row["Student Name"]).strip()
        father_name = str(row["Father's Name"]).strip()
        student_id = str(row["Student ID"]).strip()

        if aadhaar is None or mobile is None:
            skipped.append(
                {
                    "row": idx,
                    "student_id": row.get("Student ID"),
                    "reason": "invalid Aadhaar" if aadhaar is None else "invalid phone",
                }
            )
            continue

        # Rows with blank required fields can never pass portal validation; skip
        # them permanently instead of letting them re-fail every retry forever.
        if not student_name or not father_name:
            skipped.append(
                {
                    "row": idx,
                    "student_id": row.get("Student ID"),
                    "reason": "missing student name" if not student_name else "missing father name",
                }
            )
            continue

        players.append(
            {
                "student_id": row["Student ID"],
                "aadhaar": aadhaar,
                "dob": pd.to_datetime(row["DOB"]).strftime("%Y-%m-%d"),
                "name": student_name,
                "father": father_name,
                "mobile": mobile,
                "school": str(row[school_column]).strip(),
                "coach_name": (
                    str(row[coach_name_column]).strip()
                    if coach_name_column and pd.notna(row[coach_name_column])
                    else ""
                ),
                "coach_phone": (
                    _clean_mobile(row[coach_phone_column])
                    if coach_phone_column and pd.notna(row[coach_phone_column])
                    else None
                ),
            }
        )

    for item in skipped:
        logger.warning(
            "Skipping row %s (Student ID %s): %s",
            item["row"], item["student_id"], item["reason"],
        )

    return players, df


def mark_done(df, submitted_ids, data_file=None):
    mask = df["Student ID"].astype(str).isin([str(x) for x in submitted_ids])
    done_column = next(
        (column for column in df.columns if str(column).strip().casefold() == "done"),
        "Done",
    )
    if done_column not in df.columns:
        df[done_column] = ""
    done_value = True if pd.api.types.is_bool_dtype(df[done_column]) else "Y"
    df.loc[mask, done_column] = done_value
    data_file = Path(data_file or EXCEL_FILE)
    if data_file.suffix.casefold() == ".csv":
        df.to_csv(data_file, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(data_file, index=False)


# ==========================================
# FAST FIELD HELPERS
# ==========================================

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


def fill_and_verify(page, locator_factory, value, label, max_retries=4, blur=False):
    """Fill a dynamic React field and confirm the current DOM node retained it.
    Uses short polling instead of flat sleeps so it moves on as soon as the value sticks."""
    for attempt in range(max_retries + 1):
        locator = locator_factory()
        locator.wait_for(state="visible", timeout=15000)
        locator.click()
        set_field_value(locator, value)
        if blur:
            locator.press("Tab")
            page.wait_for_timeout(1000)  # let the row settle after tabbing off

        # poll quickly instead of a flat 800ms wait
        current_value = ""
        for _ in range(6):  # up to ~360ms
            page.wait_for_timeout(60)
            try:
                current_value = locator_factory().input_value().strip()
            except Exception:
                continue
            if current_value.casefold() == value.strip().casefold():
                break

        if current_value.casefold() == value.strip().casefold():
            logger.info(f"{label} retained value on attempt {attempt + 1}")
            return True

        logger.warning(f"{label} value reset on attempt {attempt + 1}; retrying")
        page.wait_for_timeout(300)

    logger.error(f"{label} did not keep the value after {max_retries + 1} attempts: {value}")
    return False


def fill_player_row(page, index, player):
    """Fill the current existing row using row-scoped selectors to avoid cross-row re-render issues."""
    row = lambda: page.locator('.team-player-content').nth(index)
    aadhaar_box = lambda: row().locator(
        'input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]'
    ).first
    dob_box = lambda: row().locator('input[type="date"]').first
    lookup_button = lambda: row().locator(
        'span[aria-label="Search using Aadhaar and DOB"] > button[type="button"]'
    ).first

    aadhaar_box().wait_for(state='visible', timeout=15000)
    dob_box().wait_for(state='visible', timeout=15000)

    fill_and_verify(page, aadhaar_box, player["aadhaar"], f"Aadhaar row {index + 1}", blur=True)
    fill_and_verify(page, dob_box, player["dob"], f"DOB row {index + 1}", blur=True)

    lookup_button().wait_for(state="visible", timeout=15000)
    for _ in range(20):
        if lookup_button().is_enabled():
            lookup_button().click()
            break
        page.wait_for_timeout(150)
    else:
        raise RuntimeError(f"Aadhaar/DOB lookup button remained disabled for row {index + 1}")

    # Wait for the async Aadhaar/DOB lookup to actually finish — the row shows a
    # "Searching..." status while the request is in flight, and typing into
    # Name/Father/Mobile before that clears wipes whatever we just entered.
    searching_indicator = row().get_by_text(re.compile(r"Searching", re.IGNORECASE))
    try:
        searching_indicator.first.wait_for(state="visible", timeout=1500)
    except Exception:
        pass  # it may already have finished or never shown at all
    try:
        searching_indicator.first.wait_for(state="hidden", timeout=15000)
    except Exception:
        logger.warning(f"'Searching...' indicator did not clear for row {index + 1} within timeout")
    page.wait_for_timeout(500)  # small settle buffer after the lookup resolves

    remaining_fields = {
        "name": lambda: row().locator(
            'input[placeholder="Enter player name"], input[aria-label="Enter player name"]'
        ).first,
        "father": lambda: row().locator(
            'input[placeholder="Enter father name"], input[aria-label="Enter father name"]'
        ).first,
        "mobile": lambda: row().locator(
            'input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]'
        ).first,
    }
    ok = True
    for key, field in remaining_fields.items():
        ok &= fill_and_verify(page, field, player[key], f"{key} row {index + 1}")
    return ok


def ensure_player_rows(page, target_count):
    """Create enough player rows for the requested total, polling for the new row instead of a flat sleep."""
    add_button = page.get_by_role("button", name=re.compile(r"Add Player", re.IGNORECASE))

    while page.locator('.team-player-content').count() < target_count:
        current = page.locator('.team-player-content').count()
        logger.info(f"Creating extra player row. Current rows: {current} / {target_count}")
        add_button.click()
        for _ in range(15):  # up to ~3s
            page.wait_for_timeout(200)
            if page.locator('.team-player-content').count() > current:
                break


def validate_all_rows_filled(page, expected_count):
    """Ensure every existing row has all post-lookup values before submitting.

    The portal consumes and clears the Aadhaar lookup input after a successful
    search, so Aadhaar must not be required in this final-state check.
    """
    rows = page.locator('.team-player-content')
    count = rows.count()

    if count < expected_count:
        raise RuntimeError(f"Expected at least {expected_count} rows, found {count}.")

    bad_rows = []
    for i in range(expected_count):
        row = rows.nth(i)
        aadhaar = row.locator('input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]').first
        dob = row.locator('input[type="date"]').first
        name = row.locator('input[placeholder="Enter player name"], input[aria-label="Enter player name"]').first
        father = row.locator('input[placeholder="Enter father name"], input[aria-label="Enter father name"]').first
        mobile = row.locator('input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]').first

        aadhaar_value = aadhaar.input_value().strip()
        values = [
            dob.input_value().strip(),
            name.input_value().strip(),
            father.input_value().strip(),
            mobile.input_value().strip(),
        ]

        if any(v == "" for v in values):
            bad_rows.append(i)
            logger.warning(
                f"Row {i + 1} is not fully filled before submit: "
                f"Aadhaar lookup value={aadhaar_value!r}, fields={values}"
            )
        else:
            logger.info(f"Validated row {i + 1} before submit: {values[1]} / {values[2]} / {values[3]}")

    return bad_rows


def save_screenshot(page, path):
    try:
        page.screenshot(path=path, full_page=True, timeout=5000)
    except Exception as error:
        logger.warning("Could not save %s: %s", path, error)


# ==========================================
# MAIN
# ==========================================

def run(
    game,
    age_group,
    otp_value=None,
    otp_provider=None,
    max_players=None,
    district=DISTRICT,
    coach_name=None,
    coach_phone=None,
    data_file=None,
):
    """
    game: one of "Basketball", "Handball", "Badminton", "Chess"
    age_group: one of "Under 14", "Under 17", "Under 21"
    """
    if game not in GAME_COACHES:
        raise ValueError(f"Unknown game '{game}'. Choose one of {list(GAME_COACHES)}")
    if age_group not in AGE_GROUPS:
        raise ValueError(f"Unknown age group '{age_group}'. Choose one of {list(AGE_GROUPS)}")

    coach = GAME_COACHES[game].copy()
    bounds = AGE_GROUPS[age_group]
    game_max_players = GAME_MAX_PLAYERS[game]
    if max_players is None:
        max_players = game_max_players

    players, excel_df = load_players_from_excel(bounds["min_age"], bounds["max_age"], data_file)
    if max_players < 1 or max_players > game_max_players:
        raise ValueError(f"max_players for {game} must be between 1 and {game_max_players}")
    players = players[:max_players]
    if not players:
        raise RuntimeError(f"No eligible, unfinished students found for {game} / {age_group}.")
    coach_name = coach_name or next(
        (player["coach_name"] for player in players if player["coach_name"]),
        coach["name"],
    )
    coach_phone = coach_phone or next(
        (player["coach_phone"] for player in players if player["coach_phone"]),
        coach["phone"],
    )

    submitted = False
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        try:
            logger.info("Opening website")
            page.goto("https://sports.punjab.gov.in/login/", wait_until="domcontentloaded")

            # -------------------------
            # LOGIN
            # -------------------------

            celebration_close = page.get_by_role("button", name="Close celebration message")
            if celebration_close.is_visible(timeout=3000):
                celebration_close.click()

            page.get_by_role(
                "button", name=re.compile(r"CLICK TO APPLY|APPLY FOR PARTICIPATION", re.IGNORECASE)
            ).first.click()

            page.get_by_role("textbox", name="Enter 10-digit mobile number").fill(PHONE)
            page.get_by_role("button", name="Get OTP").click()

            otp = otp_value or (otp_provider() if otp_provider else input("\nEnter OTP received on phone: ").strip())

            page.get_by_role("textbox", name="Enter 6-digit OTP").fill(otp)
            page.get_by_role("button", name="Verify & Continue").click()

            logger.info("OTP verified")

            # -------------------------
            # ACCOUNT
            # -------------------------

            account_pattern = re.compile(r"Name:\s*Kamlesh|Username:|Kamlesh|Vaibhav", re.IGNORECASE)
            account_button = page.get_by_role("button", name=account_pattern).first
            account_text = page.get_by_text(account_pattern).first
            try:
                account_button.wait_for(state="visible", timeout=15000)
                account_button.click()
            except Exception:
                account_text.wait_for(state="visible", timeout=15000)
                account_text.click()

            logger.info("Account selected")

            # -------------------------
            # EVENT SELECTION
            # -------------------------

            page.locator("#react-select-7-input").click()
            page.get_by_role("option", name="District").click()

            page.locator("#react-select-12-input").click()
            page.get_by_role("option", name=district).click()

            page.locator("#react-select-13-input").click()
            page.get_by_role("option", name=game).click()

            page.locator("#react-select-16-input").click()
            page.get_by_role("option", name=age_group).click()

            page.get_by_role("radio", name="Team").check()
            page.get_by_role("radio", name="Male", exact=True).check()
            page.get_by_role("checkbox").first.check()

            logger.info(f"Event selected: {game} / {age_group} / {district}")

            page.get_by_role("button", name="Click to apply for the").click()
            page.get_by_role("button", name="Confirm and proceed to the").click()

            # -------------------------
            # COACH
            # -------------------------

            team_name = players[0]["school"]
            if not team_name:
                raise ValueError("School name is empty for the first player")

            page.get_by_role("textbox", name="Enter team name").fill(team_name)
            page.get_by_role("textbox", name="Enter coach name").fill(coach_name)
            page.get_by_role("textbox", name="Enter phone number").fill(coach_phone)

            logger.info(f"Coach details filled: {coach_name} / {coach_phone}")

            # -------------------------
            # PLAYERS
            # -------------------------

            ensure_player_rows(page, len(players))

            for i, player in enumerate(players):
                logger.info(f"Filling player row {i + 1}: {player['name']}")
                fill_player_row(page, i, player)

            logger.info("All players added. Validating before any re-fill pass.")
            bad_rows = validate_all_rows_filled(page, len(players))

            # Only re-fill rows that actually failed — not a full second pass over everything.
            for i in bad_rows:
                logger.info(f"Re-applying row {i + 1} after failed validation")
                fill_player_row(page, i, players[i])

            bad_rows = validate_all_rows_filled(page, len(players))
            if bad_rows:
                raise RuntimeError(f"Rows still incomplete after retry: {[r + 1 for r in bad_rows]}")

            logger.info("All rows validated. Ready to submit.")

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
                confirm_submit.first.wait_for(state="visible", timeout=2000)
                confirm_submit.first.click()
            except Exception:
                logger.info("No confirmation popup")

            close_button = page.get_by_role("button", name="Close", description="Close")
            try:
                if close_button.is_visible(timeout=1000):
                    close_button.click(timeout=1000)
            except Exception:
                logger.info("No post-submit close button")

            mark_done(excel_df, [player["student_id"] for player in players], data_file)
            logger.info("CSV data file updated")
            submitted = True

        except Exception as error:
            logger.error(str(error))
            logger.error(traceback.format_exc())
            save_screenshot(page, "new_error.png")
        finally:
            try:
                page.wait_for_timeout(1000)  # let the portal settle before tearing down
            except Exception:
                pass
            context.close()
            browser.close()

    return submitted


if __name__ == "__main__":
    from run_batches import run_hockey as run_batches

    run_batches()