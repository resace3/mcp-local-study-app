import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright


def _request(url, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


@pytest.fixture(scope="module")
def browser_app(tmp_path_factory):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    data_dir = tmp_path_factory.mktemp("browser-data")
    environment = dict(os.environ, STUDY_DATA_DIR=str(data_dir), STUDY_PORT=str(port))
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "local_study_app.server:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
    )
    base_url = "http://127.0.0.1:%d/" % port
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            if _request(base_url + "api/health")["status"] == "ok":
                break
        except Exception:
            time.sleep(0.1)
    else:
        process.terminate()
        raise RuntimeError("Browser test server did not become healthy")
    yield base_url
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _launch_browser(runtime):
    try:
        return runtime.chromium.launch(headless=True)
    except Exception:
        return runtime.chromium.launch(headless=True, channel="chrome")


def test_visible_modes_resume_and_responsive_layout(browser_app):
    errors = []
    with sync_playwright() as runtime:
        browser = _launch_browser(runtime)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(browser_app)
        expect(page.get_by_role("heading", name="Small sessions. Big growth.")).to_be_visible()

        page.get_by_role("button", name="＋ Create").click()
        page.get_by_placeholder("e.g. Anatomy midterm").fill("Browser test deck")
        page.get_by_placeholder("What will this deck help you learn?").fill("Automated visible verification")
        page.get_by_role("button", name="Create deck", exact=True).click()
        expect(page.get_by_role("heading", name="Browser test deck")).to_be_visible()
        deck_id = int(page.url.rsplit("/", 1)[-1])

        page.get_by_role("button", name="▣ Flashcards").click()
        expect(page.get_by_role("heading", name="No cards to review")).to_be_visible()

        page.goto(browser_app + "#deck/%d" % deck_id)
        page.get_by_role("button", name="＋ Add card").click()
        inline_row = page.locator(".card-editor-row").last
        inline_row.get_by_label("Front", exact=True).fill("Inline term")
        inline_row.get_by_label("Back", exact=True).fill("Inline answer")
        expect(inline_row.locator(".save-state")).to_have_text("Saved", timeout=5000)
        page.reload()
        expect(page.locator(".card-editor-row").first.get_by_label("Front", exact=True)).to_have_value("Inline term")
        expect(page.locator(".card-editor-row").first.get_by_label("Back", exact=True)).to_have_value("Inline answer")

        for index in range(5):
            result = _request(
                browser_app + "api/cards",
                {"deck_id": deck_id, "front": "Term %d" % index, "back": "Answer %d" % index},
            )
            assert result["success"]
        page.reload()
        expect(page.get_by_text("6 cards · 0% mastered")).to_be_visible()

        page.get_by_role("button", name="▣ Flashcards").click()
        expect(page.get_by_text("1 / 6")).to_be_visible()
        page.locator("#flashcard").click()
        expect(page.locator("#flashcard")).to_have_class(re.compile("flipped"))

        page.goto(browser_app + "#learn/%d" % deck_id)
        page.get_by_role("button", name="Start learn").click()
        expect(page.get_by_role("button", name="← Exit")).to_be_visible()
        prompt_before_refresh = page.locator(".question").text_content()
        page.reload()
        expect(page.get_by_role("button", name="← Exit")).to_be_visible()
        assert page.locator(".question").text_content() == prompt_before_refresh

        page.goto(browser_app + "#write/%d" % deck_id)
        page.get_by_role("button", name="Start write").click()
        expect(page.get_by_role("button", name="Don’t know")).to_be_visible()

        page.goto(browser_app + "#spell/%d" % deck_id)
        page.get_by_role("button", name="Start spell").click()
        expect(page.get_by_role("button", name="🐢 Play slowly")).to_be_visible()

        page.goto(browser_app + "#test/%d" % deck_id)
        page.get_by_role("button", name="Start test").click()
        expect(page.get_by_text("6 questions")).to_be_visible()

        page.goto(browser_app + "#match/%d" % deck_id)
        expect(page.locator(".match-tile")).to_have_count(12)

        page.goto(browser_app + "#progress")
        expect(page.get_by_role("heading", name="Most missed")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")

        for width, height in ((768, 900), (390, 844)):
            page.set_viewport_size({"width": width, "height": height})
            page.goto(browser_app + "#dashboard")
            assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        page.goto(browser_app + "#deck/%d" % deck_id)
        assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
        expect(page.locator(".card-editor-row").first.get_by_label("Front", exact=True)).to_be_visible()
        for name in ("Home", "Library", "Folders", "Progress"):
            assert page.get_by_role("button", name=name, exact=True).bounding_box()["height"] >= 44
        browser.close()
    assert errors == []
