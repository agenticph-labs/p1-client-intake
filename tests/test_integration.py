#!/usr/bin/env python3
"""
Integration test: runs the full pipeline against both sample data files
and validates the output structure.
"""

import os
import sys
import tempfile
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client_intake_pipeline import run_pipeline


def main():
    script_dir = Path(__file__).parent.parent
    sources = [
        str(script_dir / "intake_data" / "sample_client.json"),
        str(script_dir / "intake_data" / "sample_client.csv"),
    ]

    with tempfile.TemporaryDirectory() as tmp:
        print(f"Integration test — output dir: {tmp}")
        processed, errors = run_pipeline(sources, output_dir=tmp)

        assert processed == 7, f"Expected 7 processed, got {processed}"
        assert errors == 0, f"Expected 0 errors, got {errors}"

        files = list(Path(tmp).glob("*.md"))
        assert len(files) == 8, f"Expected 8 .md files (7 reports + 1 index), got {len(files)}"

        index_files = [f for f in files if f.name == "_index.md"]
        assert len(index_files) == 1, "Missing _index.md"

        # Spot-check a report
        report = [f for f in files if "acme_manufacturing" in f.name]
        assert len(report) == 1, "Missing Acme report"
        content = report[0].read_text()
        assert "Supply Chain" in content, "Classification seems wrong for Acme"

        print(f"\n✓ Integration test PASSED — {processed} scopes, {errors} errors, {len(files)} files")


if __name__ == "__main__":
    main()
