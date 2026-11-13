"""Browser E2E against a running stack: login -> client -> uploads + mapping -> run -> export.

python tests/e2e/ui_flow.py <base-url> <email> <password> <datagen-dir> <screenshot-dir>
Needs `pip install playwright` and Chrome (uses channel="chrome", no browser download).
Fails on any console error other than the expected 409 that opens the mapping form.
"""
import json
import re
import sys
import time

from playwright.sync_api import expect, sync_playwright

BASE, EMAIL, PASSWORD, DATA, SHOTS = sys.argv[1:6]
gstin = json.load(open(f"{DATA}/gstr2b.json"))["data"]["gstin"]
problems = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(accept_downloads=True, viewport={"width": 1440, "height": 900})
    page.on("console", lambda m: m.type in ("error", "warning")
            and problems.append(f"console {m.type}: {m.text}"))
    page.on("pageerror", lambda e: problems.append(f"pageerror: {e}"))

    page.goto(BASE)
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Sign in").click()
    page.get_by_role("heading", name="Add client").wait_for()

    name = f"E2E {int(time.time())}"
    page.get_by_label("Name").fill(name)
    page.get_by_label("GSTIN").fill(gstin)
    page.get_by_role("button", name="Add client").click()
    page.get_by_role("link", name=name).click()
    page.get_by_role("heading", name=name).wait_for()

    page.get_by_label("Return period").fill("2025-04")
    page.get_by_label("GSTR-2B file").set_input_files(f"{DATA}/gstr2b.json")
    page.get_by_role("button", name=re.compile("Upload for")).first.click()
    expect(page.get_by_test_id("gstr2b-result")).to_contain_text("invoices", timeout=30000)

    page.get_by_label("Purchase register file").set_input_files(f"{DATA}/books.xlsx")
    page.get_by_role("button", name=re.compile("Upload for")).nth(1).click()
    page.get_by_role("button", name="Save mapping and upload").click()  # 409 -> mapping form
    expect(page.get_by_test_id("books-result")).to_contain_text("invoices", timeout=30000)

    page.get_by_role("button", name="Start reconciliation").click()
    page.wait_for_url(re.compile(r"/runs/"), timeout=15000)
    page.get_by_role("button", name="Export to Excel").wait_for(timeout=60000)
    page.screenshot(path=f"{SHOTS}/e2e-run.png", full_page=True)

    with page.expect_download(timeout=30000) as dl:
        page.get_by_role("button", name="Export to Excel").click()
    download = dl.value
    path = download.path()
    print("export:", download.suggested_filename, open(path, "rb").read(2) == b"PK")

    notes = page.get_by_role("button", name=re.compile("^Copy$"))
    print("vendor note copy buttons:", notes.count())
    browser.close()

csp = [x for x in problems if "Content Security Policy" in x or "Refused" in x]
print("console/page problems:", len(problems), "| CSP violations:", len(csp))
for x in problems[:10]:
    print("  ", x[:200])
unexpected = [x for x in problems if "409" not in x]
sys.exit(1 if unexpected else 0)
