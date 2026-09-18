from datetime import date, datetime
from pathlib import Path
import argparse
import logging
import re
import traceback

import pandas as pd
from playwright.sync_api import sync_playwright


PHONE = "6284432234"
COACH_NAME = "Rajendra Kumar"
COACH_PHONE = "9000000099"
PORTAL_URL = "https://sports.punjab.gov.in/login/"
DEFAULT_GAME = "Basketball (ਬਾਸਕਟਬਾਲ)"
DEFAULT_MAX_PLAYERS = 12
DEFAULT_MAX_RECORDS = 1000
DUMMY_AADHAAR_START = 100000000001
MIN_PLAYER_AGE = 10
MAX_PLAYER_AGE = 14

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler("sports.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def normalise_column(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def find_column(columns, aliases, required=True):
    names = {normalise_column(column): column for column in columns}
    for alias in aliases:
        if normalise_column(alias) in names:
            return names[normalise_column(alias)]
    if required:
        raise ValueError(f"Missing Excel column. Expected one of: {', '.join(aliases)}")
    return None


def normalise_aadhaar(value):
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):012d}"
    return str(value).strip()


def load_players(excel_path, max_records, default_player_mobile=PHONE):
    path = Path(excel_path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"Excel file not found: {path}")

    logger.info("Reading Excel workbook once: %s", path)
    frame = pd.read_excel(path, engine="openpyxl")
    logger.info("Workbook loaded: %d rows", len(frame))

    school_column = find_column(frame.columns, ["School Managment", "School Managemnt", "School Management", "School"])
    student_column = find_column(frame.columns, ["Student Name", "Student"])
    father_column = find_column(frame.columns, ["Father's Name", "Fathers Name", "Father Name"])
    gender_column = find_column(frame.columns, ["Gender"])
    dob_column = find_column(frame.columns, ["DOB", "Date of Birth"])
    aadhaar_column = find_column(frame.columns, ["Aadhaar", "Aadhar", "Aadhaar Number", "Aadhar Number"], required=False)
    done_column = find_column(frame.columns, ["done", "completed"], required=False)

    shared_mobile = re.sub(r"\D", "", str(default_player_mobile))
    if not re.fullmatch(r"\d{10}", shared_mobile):
        raise ValueError("The shared player mobile must contain exactly 10 digits.")
    if aadhaar_column is None:
        aadhaar_column = "Aadhaar"
        frame[aadhaar_column] = ""
    frame[aadhaar_column] = frame[aadhaar_column].map(normalise_aadhaar)
    if done_column is None:
        done_column = "done"
        frame[done_column] = False

    today = date.today()
    oldest_eligible_dob = today.replace(year=today.year - MAX_PLAYER_AGE)
    youngest_eligible_dob = today.replace(year=today.year - MIN_PLAYER_AGE)
    dates = pd.to_datetime(frame[dob_column], errors="coerce").dt.date
    school_values = frame[school_column].fillna("").astype(str).str.strip().str.casefold()
    recognised = school_values.isin({"pvt. recognized", "pvt recognized"})
    completed = frame[done_column].fillna(False).astype(str).str.strip().str.casefold().isin({"true", "1", "yes", "y"})
    eligible = (
        recognised
        & dates.gt(oldest_eligible_dob)
        & dates.le(youngest_eligible_dob)
        & ~completed
    )
    indices = frame.index[eligible].tolist()[:max_records]

    existing = {
        str(value)
        for value in frame[aadhaar_column]
        if re.fullmatch(r"\d{12}", str(value))
    }
    next_aadhaar = DUMMY_AADHAAR_START
    players = []

    for index in indices:
        while str(next_aadhaar) in existing:
            next_aadhaar += 1
        if next_aadhaar > 999999999999:
            raise ValueError("No unused 12-digit dummy Aadhaar numbers remain.")
        aadhaar = str(next_aadhaar)
        next_aadhaar += 1
        existing.add(aadhaar)
        frame.at[index, aadhaar_column] = aadhaar

        players.append({
            "row_index": index,
            "aadhaar": aadhaar,
            "dob": dates.at[index].isoformat(),
            "name": str(frame.at[index, student_column]).strip(),
            "father": str(frame.at[index, father_column]).strip(),
            "mobile": shared_mobile,
            "gender": str(frame.at[index, gender_column]).strip(),
            "school": str(frame.at[index, school_column]).strip(),
        })

    if not players:
        raise ValueError("No unfinished Pvt. Recognized students are eligible for Under 14.")
    logger.info("Selected %d eligible student(s)", len(players))
    return frame, players, done_column, path


def save_done(frame, done_column, players, path):
    for player in players:
        frame.at[player["row_index"], done_column] = True
    frame.to_excel(path, index=False, engine="openpyxl")


def set_field_value(locator, value):
    locator.evaluate(
        """
        (el, val) => {
          const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
          descriptor.set.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        """,
        value,
    )


def fill_and_verify(page, locator, value, label):
    expected = value.strip()
    for attempt in range(4):
        locator.click()
        set_field_value(locator, value)
        page.wait_for_timeout(250)
        actual = locator.input_value().strip()
        if actual == expected or actual.casefold() == expected.casefold():
            return
        logger.warning("%s reset on attempt %d", label, attempt + 1)
        page.wait_for_timeout(500)
    raise RuntimeError(f"{label} did not retain its value")


def ensure_rows(page, count):
    add_button = page.get_by_role("button", name=re.compile(r"Add Player", re.IGNORECASE))
    while page.locator(".team-player-content").count() < count:
        current = page.locator(".team-player-content").count()
        if add_button.is_disabled():
            raise RuntimeError(f"Portal disabled Add Player at {current} rows")
        add_button.click()
        page.wait_for_timeout(1200)


def fill_player(page, index, player):
    row = page.locator(".team-player-content").nth(index)
    aadhaar = row.locator(
        'input[aria-label="Enter Aadhaar to prefill"], '
        'input[placeholder="12 digits to prefill"], '
        'input[placeholder*="Aadhaar"]'
    ).first
    dob = row.locator('input[type="date"]').first

    aadhaar.wait_for(state="visible", timeout=20000)
    dob.wait_for(state="visible", timeout=20000)
    fill_and_verify(page, aadhaar, player["aadhaar"], f"Aadhaar row {index + 1}")
    aadhaar.press("Tab")
    fill_and_verify(page, dob, player["dob"], f"DOB row {index + 1}")
    dob.press("Tab")

    # Aadhaar/DOB lookup re-renders this card. Reacquire its controls after it settles.
    page.wait_for_timeout(1000)
    row = page.locator(".team-player-content").nth(index)
    remaining_fields = {
        "Player name": row.locator('input[placeholder="Enter player name"]').first,
        "Father name": row.locator('input[placeholder="Enter father name"]').first,
        "Mobile": row.locator('input[placeholder="Enter mobile number"]').first,
    }
    for label, field in remaining_fields.items():
        field.wait_for(state="visible", timeout=20000)
        fill_and_verify(page, field, player[{"Player name": "name", "Father name": "father", "Mobile": "mobile"}[label]], f"{label} row {index + 1}")


def start_application(page):
    event_form = page.locator("p.input_Select_label").filter(has_text="Game Level").first
    try:
        event_form.wait_for(state="visible", timeout=20000)
    except Exception:
        apply_button = page.get_by_role(
            "button",
            name=re.compile(r"CLICK TO APPLY|Apply for Participation", re.IGNORECASE),
        ).first
        apply_button.wait_for(state="visible", timeout=30000)
        apply_button.click()
        event_form.wait_for(state="visible", timeout=30000)


def confirm_event_selection(page):
    apply_button = page.get_by_role("button", name="Click to apply for the")
    apply_button.wait_for(state="visible", timeout=20000)
    apply_button.click()
    confirm_button = page.get_by_role("button", name="Confirm and proceed to the")
    confirm_button.wait_for(state="visible", timeout=20000)
    confirm_button.click()
    page.get_by_role("textbox", name="Enter team name").wait_for(state="visible", timeout=20000)


def choose_event(page, game):
    def select_field(label, option):
        field_label = page.locator("p.input_Select_label").filter(has_text=label).first
        field_label.wait_for(state="visible", timeout=20000)
        field_label.locator("xpath=..").locator("input").first.click()
        page.get_by_role("option", name=option).click()

    select_field("Game Level", "District")
    select_field("District", "Amritsar")
    select_field("Game", game)
    select_field("Age Group", "Under 14")
    page.get_by_role("radio", name="Team").check()
    page.get_by_role("radio", name="Male", exact=True).check()
    page.get_by_role("checkbox").first.check()


def submit_batch(page, players, team_name, game):
    start_application(page)
    choose_event(page, game)
    confirm_event_selection(page)
    page.get_by_role("textbox", name="Enter team name").fill(team_name)
    page.get_by_role("textbox", name="Enter coach name").fill(COACH_NAME)
    page.get_by_role("textbox", name="Enter phone number").fill(COACH_PHONE)
    ensure_rows(page, len(players))
    for index, player in enumerate(players):
        fill_player(page, index, player)

    save_screenshot(page, "before_submit.png")
    page.get_by_role("button", name="Final Submission").click()
    page.get_by_role("button", name="Submit your application").click()
    page.get_by_role("button", name="Close", description="Close").click(timeout=15000)
    logger.info("Submitted confirmation for %s", team_name)


def save_screenshot(page, path):
    try:
        page.screenshot(path=path, full_page=True, timeout=5000)
    except Exception as error:
        logger.warning("Could not save %s: %s", path, error)


def run(
    excel_path,
    max_records=DEFAULT_MAX_RECORDS,
    max_players=DEFAULT_MAX_PLAYERS,
    game=DEFAULT_GAME,
    default_player_mobile=PHONE,
):
    if max_players < 1:
        raise ValueError("max_players must be at least 1")
    max_players = min(max_players, DEFAULT_MAX_PLAYERS)
    frame, players, done_column, path = load_players(
        excel_path,
        max_records,
        default_player_mobile,
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_navigation_timeout(60000)
        try:
            page.goto(PORTAL_URL, wait_until="domcontentloaded")
            celebration_close = page.get_by_role("button", name="Close celebration message")
            if celebration_close.is_visible(timeout=3000):
                celebration_close.click()
            apply_login = page.get_by_text("APPLY FOR PARTICIPATION", exact=True)
            apply_login.wait_for(state="visible", timeout=30000)
            apply_login.click()
            page.get_by_role("textbox", name="Enter 10-digit mobile number").fill(PHONE)
            page.get_by_role("button", name="Get OTP").click()
            otp = input("\nEnter OTP received on phone: ").strip()
            page.get_by_role("textbox", name="Enter 6-digit OTP").fill(otp)
            page.get_by_role("button", name="Verify & Continue").click()
            account = page.get_by_role("button", name=re.compile(r"Name: Kamlesh Username:|Kamlesh|Vaibhav", re.IGNORECASE)).first
            account.wait_for(state="visible", timeout=30000)
            account.click()

            batch = players[:max_players]
            team_name = batch[0]["school"]
            if not team_name:
                raise ValueError("School name is empty for the first player")
            logger.info("Starting %s: %d student(s), game=%s", team_name, len(batch), game)
            submit_batch(page, batch, team_name, game)
            save_done(frame, done_column, batch, path)
            logger.info("Marked %d rows done. Run the script again for the next batch.", len(batch))
        except Exception as error:
            logger.error(str(error))
            logger.error(traceback.format_exc())
            save_screenshot(page, "error.png")
        finally:
            save_screenshot(page, "final_state.png")
            context.close()
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Submit eligible Excel students in one portal session.")
    parser.add_argument("excel_path", help="Path to the Excel workbook")
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS, help="Maximum students to process (default: 1000)")
    parser.add_argument("--max-players", type=int, default=DEFAULT_MAX_PLAYERS, help="Players per team (default: 12)")
    parser.add_argument("--game", default=DEFAULT_GAME, help="Portal game option")
    parser.add_argument(
        "--default-player-mobile",
        default=PHONE,
        help="Shared player mobile when the workbook has no Mobile column",
    )
    args = parser.parse_args()
    run(
        args.excel_path,
        args.max_records,
        args.max_players,
        args.game,
        args.default_player_mobile,
    )
