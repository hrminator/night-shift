"""docs/instructions.md must match what scripts/dump_instructions.py generates."""

from pathlib import Path

from scripts.dump_instructions import generate_markdown


def test_instructions_doc_in_sync():
    doc_path = Path(__file__).resolve().parent.parent / "docs" / "instructions.md"
    assert doc_path.read_text(encoding="utf-8") == generate_markdown()
