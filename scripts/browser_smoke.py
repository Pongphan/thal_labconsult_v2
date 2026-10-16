"""Real Chromium layout/keyboard/Thai PDF checks using synthetic data only.

Run after installing the locked development environment and
`python -m playwright install chromium`. Each server and browser is owned by this
run; no user browser profile, external service or existing server is controlled.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import re
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@contextmanager
def test_server(theme: str, output: Path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    with (output / f"server-{theme}.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py", "--server.address=127.0.0.1",
             f"--server.port={port}", "--server.headless=true", f"--theme.base={theme}",
             "--browser.gatherUsageStats=false", "--server.fileWatcherType=none"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Streamlit failed; inspect server-{theme}.log")
                try:
                    with urlopen(url + "/_stcore/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Streamlit health timeout")
            yield url
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def check_app(browser, url: str, theme: str, width: int, output: Path) -> dict:
    from playwright.sync_api import expect

    context = browser.new_context(viewport={"width": width, "height": 1000}, color_scheme=theme)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until="domcontentloaded")
        home = page.get_by_role("button", name=re.compile(r"(?:^| )หน้าหลัก$"))
        expect(home).to_be_visible(timeout=45000)
        expect(page.locator(".st-key-thal_footer")).to_be_visible(timeout=45000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        expect(page.get_by_test_id("stSidebar")).to_have_count(0)
        # Verify actual computed theme, not only a mocked Python theme branch.
        background = page.get_by_test_id("stApp").evaluate("el => getComputedStyle(el).backgroundColor")
        expected = "rgb(26, 33, 48)" if theme == "dark" else "rgb(250, 248, 247)"
        assert background == expected, (theme, background)
        main = page.get_by_test_id("stMain")
        main.evaluate("el => { el.scrollTop = 0; }")
        assert main.evaluate("el => el.scrollWidth <= el.clientWidth + 2"), "Main container overflow"
        brand_box = page.locator(".thal-brand").bounding_box()
        header_box = page.get_by_test_id("stHeader").bounding_box()
        assert brand_box and header_box and brand_box["y"] >= header_box["y"] + header_box["height"], "Brand hidden under fixed toolbar"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Horizontal page overflow"
        page.screenshot(path=str(output / f"home-{theme}-{width}.png"), full_page=True)
        other = page.get_by_role("button", name=re.compile(r"(?:^| )อื่นๆ$"))
        home.focus()
        for _ in range(3):
            page.keyboard.press("Tab")
        expect(other).to_be_focused()
        page.keyboard.press("Enter")
        report = page.get_by_role("button", name=re.compile(r"(?:^| )การออกแบบใบรายงานผล$"))
        expect(report).to_be_visible()
        # Exercise keyboard focus and activation of the route within the menu.
        tab_steps = 0
        for _ in range(64):
            if report.evaluate("el => el === document.activeElement"):
                break
            page.keyboard.press("Tab")
            tab_steps += 1
        expect(report).to_be_focused()
        page.keyboard.press("Enter")
        html_download = page.get_by_role("button", name=re.compile(r"(?:^| )HTML · DRAFT$"))
        expect(html_download).to_be_visible(timeout=30000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"), "Reporting page overflow"
        frame = page.frame_locator('iframe[title="รายงานสมมติฉบับเดียวกับไฟล์ HTML สำหรับพิมพ์ A4 พร้อมผลและสถานะ DRAFT"]')
        expect(frame.get_by_text("SYNTHETIC-PATIENT-001", exact=True)).to_be_visible()
        page.screenshot(path=str(output / f"reporting-{theme}-{width}.png"), full_page=True)
        with page.expect_download() as download_info:
            html_download.click()
        download = download_info.value
        downloaded = Path(download.path()).read_text(encoding="utf-8")
        iframe_source = page.locator('iframe[title="รายงานสมมติฉบับเดียวกับไฟล์ HTML สำหรับพิมพ์ A4 พร้อมผลและสถานะ DRAFT"]').get_attribute("srcdoc")
        # Streamlit may wrap srcdoc for automatic sizing. The generated document
        # must still be present without a separate layout transformation.
        assert iframe_source and downloaded in iframe_source, "Preview/export documents differ"
        draft_import = None
        if theme == "light" and width == 1440:
            from logic.reporting import demo_rows
            from utils.drafts import capture_synthetic_draft, synthetic_draft_bytes

            page.get_by_text("บันทึกและคืนค่าร่างงานสมมติ (JSON)", exact=True).click()
            with page.expect_download() as saved_draft_info:
                page.get_by_role("button", name=re.compile(r"(?:^| )ดาวน์โหลดร่างงานสมมติ$")).click()
            saved = Path(saved_draft_info.value.path()).read_bytes()
            page.reload(wait_until="domcontentloaded")
            expect(html_download).to_be_visible(timeout=30000)
            page.get_by_text("บันทึกและคืนค่าร่างงานสมมติ (JSON)", exact=True).click()
            uploader = page.get_by_test_id("stFileUploader").locator('input[type="file"]')
            uploader.set_input_files({"name": "saved-synthetic.json", "mimeType": "application/json", "buffer": saved})
            restore = page.get_by_role("button", name=re.compile(r"(?:^| )นำเข้าร่างงานสมมติ$"))
            restore.click()
            expect(page.get_by_text(re.compile("คืนค่าร่างงานสมมติแล้ว"))).to_be_visible()
            rows = demo_rows("cbc")
            rows[0]["result"] = -1
            changed = synthetic_draft_bytes(capture_synthetic_draft({
                "reporting_institution": "Synthetic restored draft",
                "reporting_rows_cbc": rows,
            }))
            uploader.set_input_files({"name": "invalid-synthetic-values.json", "mimeType": "application/json", "buffer": changed})
            restore.click()
            expect(page.get_by_label("ชื่อหน่วยงานบนแม่แบบ (สมมติ)", exact=True)).to_have_value("Synthetic restored draft")
            expect(page.get_by_text(re.compile("REJECT · ข้อมูลสมมติไม่ผ่าน"))).to_be_visible()
            expect(frame.get_by_text("Synthetic restored draft", exact=True)).to_be_visible()
            draft_import = "download_reload_restore_and_revalidate_passed"
        assert not errors, errors
        return {"theme": theme, "width": width, "background": background, "keyboard_tab_route": "passed", "menu_tab_steps": tab_steps, "preview_export_equal": True, "draft_import": draft_import}
    except Exception:
        page.screenshot(path=str(output / f"failed-{theme}-{width}.png"), full_page=True)
        (output / f"failed-{theme}-{width}.txt").write_text(page.locator("body").aria_snapshot(), encoding="utf-8")
        raise
    finally:
        context.close()


def check_reports(browser, output: Path) -> list[dict]:
    import pypdfium2 as pdfium
    from logic.reporting import TEST_CATALOG, demo_rows, validate_report
    from utils.report_layout import ReportTemplate, build_report_payload, render_report_html

    evidence = []
    page = browser.new_page(viewport={"width": 1000, "height": 1200})
    try:
        for panel in ("cbc", "combined"):
            rows = demo_rows(panel)
            validation = validate_report(rows, panel=panel)
            payload = build_report_payload(rows, TEST_CATALOG, validation, ReportTemplate(panel=panel, language="bilingual"))
            html = render_report_html(payload)
            (output / f"{panel}.html").write_text(html, encoding="utf-8")
            page.set_content(html, wait_until="load")
            page.evaluate("document.fonts.ready")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Report horizontal overflow"
            pdf_path = output / f"{panel}.pdf"
            page.pdf(path=str(pdf_path), format="A4", prefer_css_page_size=True, print_background=True)
            document = pdfium.PdfDocument(str(pdf_path))
            texts, sizes = [], []
            try:
                for index in range(len(document)):
                    pdf_page = document[index]
                    try:
                        sizes.append(list(pdf_page.get_size()))
                        text_page = pdf_page.get_textpage()
                        try:
                            texts.append(text_page.get_text_range())
                        finally:
                            text_page.close()
                        bitmap = pdf_page.render(scale=1.25)
                        try:
                            bitmap.to_pil().save(output / f"{panel}-page-{index + 1}.png")
                        finally:
                            bitmap.close()
                    finally:
                        pdf_page.close()
            finally:
                document.close()
            text = "\n".join(texts)
            assert all(abs(w - 595.28) < 2 and abs(h - 841.89) < 2 for w, h in sizes), sizes
            assert "SYNTHETIC-PATIENT-001" in text and "Snapshot SHA-256" in text
            # Chromium/PDFium can repeat Thai combining clusters during text
            # extraction despite correct visual shaping. Check a stable Thai
            # heading plus replacement glyphs; inspect rendered PNGs as well.
            assert "ผลตรวจสมมติ" in text, "Thai heading missing from PDF"
            assert "\ufffd" not in text and "\u25a1" not in text, "Replacement glyph in PDF"
            for row in rows:
                # Thai shaping clusters can interleave with adjacent Latin text
                # in extraction order. Compare the Latin test-name channel;
                # visual verification uses the page PNGs, not this assertion.
                latin = lambda value: re.sub(r"[^A-Za-z0-9]", "", value)
                assert latin(TEST_CATALOG[row["code"]]["name_en"]) in latin(text), row["code"]
            if panel == "combined":
                assert len(sizes) > 1, "Expected multi-page combined report"
            evidence.append({"panel": panel, "pages": len(sizes), "page_sizes_points": sizes, "thai_text": "passed", "all_tests_present": True})
        return evidence
    finally:
        page.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "browser")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright
    from utils.build_provenance import capture_build_provenance

    evidence = {"status": "running", "build_provenance": capture_build_provenance(), "app": [], "reports": []}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                evidence["browser_version"] = browser.version
                for theme in ("light", "dark"):
                    with test_server(theme, output) as url:
                        for width in (1440, 390):
                            evidence["app"].append(check_app(browser, url, theme, width, output))
                evidence["reports"] = check_reports(browser, output)
                evidence["status"] = "passed"
            finally:
                browser.close()
    except Exception as exc:
        evidence.update(status="failed", error=str(exc))
        raise
    finally:
        (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PASS: 4 browser layouts, keyboard routes, shared HTML preview, {len(evidence['reports'])} multipage Thai PDF cases. Evidence: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
