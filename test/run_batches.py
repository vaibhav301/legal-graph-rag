from __future__ import annotations

from pathlib import Path
import random
import re
import sqlite3
import threading
import time

import pandas as pd

import new_bot

EXCEL_FILE = new_bot.EXCEL_FILE
GAME_MAX_PLAYERS = new_bot.GAME_MAX_PLAYERS
MAX_RECORDS_PER_TARGET = 768
OTP_TIMEOUT_SECONDS = 90
OTP_POLL_SECONDS = 2
OTP_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
AGE_FILES = {
    "Under 14": Path("under14.csv"),
    "Under 17": Path("under17.csv"),
    "Under 21": Path("under21.csv"),
}
GAMES = ("Handball", "Basketball")
COACH_NAMES = [
    "Aarav Sharma",
    "Vivaan Verma",
    "Aditya Gupta",
    "Aryan Mishra",
    "Krish Tiwari",
    "Ansh Yadav",
    "Rudra Chauhan",
    "Reyansh Agrawal",
    "Atharv Jain",
    "Daksh Bansal",
    "Kartik Sharma",
    "Yash Verma",
    "Kunal Gupta",
    "Mohit Mishra",
    "Rohit Tiwari",
    "Nitin Yadav",
    "Saurabh Chauhan",
    "Ayush Agrawal",
    "Rohan Jain",
    "Varun Bansal",
    "Ananya Sharma",
    "Aadhya Verma",
    "Saanvi Gupta",
    "Kavya Mishra",
    "Diya Tiwari",
    "Priya Yadav",
    "Riya Chauhan",
    "Pooja Agrawal",
    "Neha Jain",
    "Sneha Bansal"
]


class CoachRotator:
    def __init__(self, names, shuffle_after=3):
        self.names = list(names)
        self.shuffle_after = shuffle_after
        self.completed_runs = 0
        self.lock = threading.Lock()

    def next_name(self):
        with self.lock:
            if self.completed_runs % self.shuffle_after == 0:
                random.shuffle(self.names)
            name = self.names[self.completed_runs % len(self.names)]
            self.completed_runs += 1
            return name


COACH_ROTATOR = CoachRotator(COACH_NAMES)


def read_latest_otp():
    database = Path.home() / "Library/Messages/chat.db"
    if not database.exists():
        raise RuntimeError(f"Messages database not found: {database}")

    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            rows = connection.execute(
                "SELECT text FROM message WHERE text IS NOT NULL "
                "ORDER BY date DESC LIMIT 500"
            ).fetchall()
    except sqlite3.Error as error:
        raise RuntimeError(
            "Could not read Messages chat.db. Grant Terminal/Python Full Disk Access "
            f"in System Settings > Privacy & Security > Full Disk Access. {error}"
        ) from error

    for (message_text,) in rows:
        match = OTP_PATTERN.search(message_text or "")
        if match:
            return match.group(1)
    return None


def wait_for_new_otp(previous_otp):
    time.sleep(4)  # give the SMS a moment to arrive so we don't grab a stale OTP
    deadline = time.monotonic() + OTP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        latest_otp = read_latest_otp()
        if latest_otp and latest_otp != previous_otp:
            print(f"Using latest OTP from Messages: {latest_otp}")
            return latest_otp
        time.sleep(OTP_POLL_SECONDS)
    raise TimeoutError("No new 6-digit OTP was found in Messages before the timeout.")


def done_count(frame):
    done_column = next(
        (column for column in frame.columns if str(column).strip().casefold() == "done"),
        None,
    )
    if done_column is None:
        return 0
    return int(
        frame[done_column]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        .isin({"y", "yes", "true", "1"})
        .sum()
    )


def run_target(game, age_group, data_file, max_records=MAX_RECORDS_PER_TARGET):
    processed_this_target = 0
    previous_otp = read_latest_otp()
    coach = new_bot.GAME_COACHES[game]

    bounds = new_bot.AGE_GROUPS[age_group]
    while processed_this_target < max_records:
        frame = pd.read_csv(data_file, dtype=str, keep_default_na=False)
        before_done = done_count(frame)
        remaining = max_records - processed_this_target
        available = len(new_bot.load_players_from_excel(bounds["min_age"], bounds["max_age"], data_file)[0])
        if available == 0:
            print(f"No unfinished {game} / {age_group} students remain.")
            return

        batch_size = min(new_bot.GAME_MAX_PLAYERS[game], remaining, available)
        print(
            f"Starting {game} / {age_group} batch with up to {batch_size} players "
            f"({processed_this_target}/{max_records} this target; {before_done} already done)."
        )

        coach_name = COACH_ROTATOR.next_name()
        try:
            submitted = new_bot.run(
                game=game,
                age_group=age_group,
                otp_provider=lambda: wait_for_new_otp(previous_otp),
                max_players=batch_size,
                coach_name=coach_name,
                coach_phone=coach["phone"],
                data_file=data_file,
            )
        except Exception as error:
            print(f"Batch failed ({game} / {age_group}): {error}. Retrying next batch.")
            previous_otp = read_latest_otp()
            time.sleep(5)
            continue

        if not submitted:
            print(f"Batch did not complete for {game} / {age_group}; retrying next batch.")
            previous_otp = read_latest_otp()
            time.sleep(5)
            continue

        updated = pd.read_csv(data_file, dtype=str, keep_default_na=False)
        after_done = done_count(updated)
        delta = after_done - before_done
        if delta <= 0:
            print(f"No new records marked done for {game} / {age_group}; retrying next batch.")
            previous_otp = read_latest_otp()
            time.sleep(5)
            continue

        processed_this_target += delta
        previous_otp = read_latest_otp()
        print(f"Excel updated: {delta} {game} / {age_group} students marked done.")

    print(f"Reached the {max_records}-record cap for {game} / {age_group}.")


def run():
    age_group = "Under 17"
    data_file = AGE_FILES[age_group]
    if not data_file.is_file():
        raise FileNotFoundError(f"Age-group CSV not found: {data_file}")
    for game in GAMES:
        try:
            run_target(game, age_group, data_file)
        except Exception as error:
            print(f"{game} / {age_group} stopped early: {error}. Continuing with next game.")


HOCKEY_TARGETS = {
    "Under 14": 180,
    "Under 17": 396,
    "Under 21": 324,
}


def run_hockey():
    game = "Hockey"
    for age_group, target in HOCKEY_TARGETS.items():
        data_file = AGE_FILES[age_group]
        if not data_file.is_file():
            raise FileNotFoundError(f"Age-group CSV not found: {data_file}")
        try:
            run_target(game, age_group, data_file, max_records=target)
        except Exception as error:
            print(f"{game} / {age_group} stopped early: {error}. Continuing with next age group.")


if __name__ == "__main__":
    run_hockey()
