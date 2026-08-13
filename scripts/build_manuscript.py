"""Assemble the manuscript body with verified references and end-matter tables."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    body = (ROOT / "manuscript" / "MANUSCRIPT_BODY.md").read_text(encoding="utf-8")
    tables = (ROOT / "tables" / "MAIN_TABLES.md").read_text(encoding="utf-8")
    references = (ROOT / "references" / "manuscript_references_vancouver.md").read_text(
        encoding="utf-8"
    )
    references = references.replace("# Verified reference library", "## References", 1)
    if "{{TABLE_" in body:
        raise RuntimeError("Inline table placeholder remains in MANUSCRIPT_BODY.md")
    output = body.rstrip() + "\n\n" + references.strip() + "\n\n" + tables.strip() + "\n"
    target = ROOT / "manuscript" / "MANUSCRIPT.md"
    target.write_text(output, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
