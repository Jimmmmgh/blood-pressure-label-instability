"""Assemble the manuscript body with generated tables and verified references."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker) + len(marker)
    next_heading = markdown.find("\n## ", start)
    return markdown[start : next_heading if next_heading >= 0 else len(markdown)].strip()


def main() -> int:
    body = (ROOT / "manuscript" / "MANUSCRIPT_BODY.md").read_text(encoding="utf-8")
    tables = (ROOT / "tables" / "MAIN_TABLES.md").read_text(encoding="utf-8")
    for number, title in ((1, "Table 1. Source-specific cohort characteristics"),
                          (2, "Table 2. Measurement-source instability"),
                          (3, "Table 3. Policy-specific mortality association sensitivity")):
        body = body.replace(f"{{{{TABLE_{number}}}}}", section(tables, title))
    references = (ROOT / "references" / "manuscript_references_vancouver.md").read_text(
        encoding="utf-8"
    )
    references = references.replace("# Verified reference library", "## References", 1)
    output = body.rstrip() + "\n\n" + references.strip() + "\n"
    target = ROOT / "manuscript" / "MANUSCRIPT.md"
    target.write_text(output, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
