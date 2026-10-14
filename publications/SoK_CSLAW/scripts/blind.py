"""Render manuscript_blind.pdf, the anonymous version of the paper for review.

manuscript.qmd carries BLIND-REVIEW SWAP blocks. A <<NAMED ... NAMED>> block
holds the text of the named version; the <<BLIND ... BLIND>> block next to it
holds the anonymous text, commented out (YAML lines behind a leading "#",
body lines inside an HTML comment). This script drops the NAMED blocks,
uncomments the BLIND blocks, writes the result to manuscript_blind.qmd,
renders that copy with Quarto and deletes it again. manuscript.qmd is never
modified. Run via `make blind` (which builds the tables first).
"""

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "manuscript.qmd"
TMP = ROOT / "manuscript_blind.qmd"

OPEN_NAMED = {"#<<NAMED", "<!-- <<NAMED -->"}
CLOSE_NAMED = {"#NAMED>>", "<!-- NAMED>> -->"}
OPEN_BLIND = {"#<<BLIND", "<!-- <<BLIND"}
CLOSE_BLIND = {"#BLIND>>", "BLIND>> -->"}
# Text that must not survive the swap.
LEAKS = re.compile(r"\bour (?:earlier|own|companion|prior)\b|Sebastian Nagl|sebastian\.nagl|\(TUM\)|nagl2027transformation")


def swap(text: str) -> str:
    """The blind text: NAMED blocks dropped, BLIND blocks uncommented."""
    out, mode, counts = [], None, {"named": 0, "blind": 0}
    for n, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s in OPEN_NAMED or s in OPEN_BLIND:
            if mode is not None:
                raise SystemExit(f"line {n}: swap block opened inside another one")
            mode = "named" if s in OPEN_NAMED else "blind"
            counts[mode] += 1
            continue
        if s in CLOSE_NAMED or s in CLOSE_BLIND:
            if mode != ("named" if s in CLOSE_NAMED else "blind"):
                raise SystemExit(f"line {n}: stray {s}")
            mode = None
            continue
        if mode == "named":
            continue
        if mode == "blind" and line.startswith("#"):
            line = line[1:]
        out.append(line)
    if mode is not None or counts["named"] != counts["blind"]:
        raise SystemExit(f"unbalanced swap blocks: {counts}, still open: {mode}")
    result = "\n".join(out)
    if leak := LEAKS.search(result):
        raise SystemExit(f"identifying text survives the swap: {leak.group(0)!r}")
    return result


def main() -> None:
    TMP.write_text(swap(SRC.read_text(encoding="utf-8")), encoding="utf-8")
    try:
        subprocess.run(["quarto", "render", TMP.name], cwd=ROOT, check=True)
    finally:
        TMP.unlink(missing_ok=True)
        (ROOT / "manuscript_blind.tex").unlink(missing_ok=True)
        shutil.rmtree(ROOT / "manuscript_blind_files", ignore_errors=True)
    print("wrote manuscript_blind.pdf")


if __name__ == "__main__":
    main()
