from playwright.sync_api import sync_playwright
import time

PHONE = "6284432234"


def dump_rows(page, label):
    aadhaar = page.locator('input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]')
    names = page.locator('input[placeholder="Enter player name"], input[aria-label="Enter player name"]')
    fathers = page.locator('input[placeholder="Enter father name"], input[aria-label="Enter father name"]')
    mobiles = page.locator('input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]')

    count = aadhaar.count()
    print(f"\n=== {label} ===")
    print("row_count =", count)

    for i in range(min(count, 12)):
        print(
            i,
            "aadhaar=", aadhaar.nth(i).input_value(),
            "name=", names.nth(i).input_value(),
            "father=", fathers.nth(i).input_value(),
            "mobile=", mobiles.nth(i).input_value(),
        )


with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://sports.punjab.gov.in/login/", wait_until="networkidle")

    page.get_by_text("APPLY FOR PARTICIPATION", exact=True).click()
    page.get_by_role("textbox", name="Enter 10-digit mobile number").fill(PHONE)
    page.get_by_role("button", name="Get OTP").click()

    otp = input("Enter OTP: ")
    page.get_by_role("textbox", name="Enter 6-digit OTP").fill(otp)
    page.get_by_role("button", name="Verify & Continue").click()

    page.get_by_role("button", name="Vaibhav").click()

    page.locator("#react-select-7-input").click()
    page.get_by_role("option", name="District").click()
    page.locator("#react-select-12-input").click()
    page.get_by_role("option", name="Amritsar").click()
    page.locator("#react-select-13-input").click()
    page.get_by_role("option", name="Basketball (ਬਾਸਕਟਬਾਲ)").click()
    page.locator("#react-select-16-input").click()
    page.get_by_role("option", name="Under 14").click()
    page.get_by_role("radio", name="Team").check()
    page.get_by_role("radio", name="Male", exact=True).check()
    page.get_by_role("checkbox").first.check()

    page.get_by_role("button", name="Click to apply for the").click()
    page.get_by_role("button", name="Confirm and proceed to the").click()

    page.get_by_role("textbox", name="Enter team name").fill("Debug Team")
    page.get_by_role("textbox", name="Enter coach name").fill("Debug Coach")
    page.get_by_role("textbox", name="Enter phone number").fill("9999999999")

    for i in range(3):
        dump_rows(page, f"before row {i}")

        aadhaar = page.locator('input[placeholder="12 digits to prefill"], input[placeholder*="Aadhaar"], input[aria-label*="Aadhaar"]').nth(i)
        dob = page.locator('input[type="date"]').nth(i)
        name = page.locator('input[placeholder="Enter player name"], input[aria-label="Enter player name"]').nth(i)
        father = page.locator('input[placeholder="Enter father name"], input[aria-label="Enter father name"]').nth(i)
        mobile = page.locator('input[placeholder="Enter mobile number"], input[aria-label="Enter mobile number"]').nth(i)

        aadhaar.fill(f"1234567890{i}0")
        dob.fill("2013-11-11")
        name.fill(f"Player{i}")
        father.fill(f"Father{i}")
        mobile.fill(f"98765432{i}0")

        dump_rows(page, f"after fill row {i}")

        if i < 2:
            page.get_by_role("button", name="Add Player").click()
            time.sleep(1)
            dump_rows(page, f"after Add Player row {i}")

    input("Press Enter to close browser")
    browser.close()
