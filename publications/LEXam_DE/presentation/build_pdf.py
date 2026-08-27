#!/usr/bin/env python3
"""Print slides.html to slides.pdf (one 1280x720 page per slide).

Needs a chromium binary on PATH. Usage: python3 presentation/build_pdf.py
(from the LEXam_DE folder) or python3 build_pdf.py (from presentation/).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).parent

CHROME_FALLBACKS = [
    "chromium",
    "chromium-browser",
    "google-chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def find_chrome() -> str:
    for cand in CHROME_FALLBACKS:
        if shutil.which(cand) or Path(cand).is_file():
            return cand
    raise SystemExit("no chromium/chrome binary found; install one or add it to PATH")

PRINT_CSS = """<style media="print">
  @page { size: 1280px 720px; margin: 0; }
  body { background: #ffffff !important; overflow: visible !important; }
  #stage-wrap { position: static !important; display: block !important; }
  #stage { width: 1280px !important; height: auto !important; transform: none !important; }
  .slide {
    position: relative !important; inset: auto !important;
    display: flex !important;
    width: 1280px; height: 720px;
    border: none !important;
    page-break-after: always; break-after: page;
    overflow: hidden;
  }
  .slide:last-of-type { page-break-after: auto; break-after: auto; }
  #hud { display: none !important; }
</style>
"""


def main() -> None:
    src = (HERE / "slides.html").read_text()
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(src.replace("</style>", "</style>\n" + PRINT_CSS, 1))
        tmp = f.name
    try:
        subprocess.run(
            [find_chrome(), "--headless", "--disable-gpu", "--no-sandbox",
             "--virtual-time-budget=4000", "--no-pdf-header-footer",
             f"--print-to-pdf={HERE / 'slides.pdf'}", f"file://{tmp}"],
            check=True, capture_output=True,
        )
    finally:
        Path(tmp).unlink(missing_ok=True)
    print(f"wrote {HERE / 'slides.pdf'}")


if __name__ == "__main__":
    main()
