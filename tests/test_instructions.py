"""docs/instructions.md must match what scripts/dump_instructions.py generates."""

from pathlib import Path

from scripts.dump_instructions import generate_markdown


def test_instructions_doc_in_sync():
    doc_path = Path(__file__).resolve().parent.parent / "docs" / "instructions.md"
    assert doc_path.read_text(encoding="utf-8") == generate_markdown()


def test_reissue_rule_present_and_general():
    import re

    from app import runner

    rule = runner.REISSUE_RULE
    assert "same recipient" in rule
    assert "one current message per party" in rule
    assert "nothing that commits to a dropped plan" in rule
    assert "never an approval" in rule
    assert not re.search(r"\d", rule)
    lowered = rule.lower()
    for token in ("baltic", "rannavere", "vestland", "nordtrykk",
                  "sjosalen", "bergen", "oslo", "q-1187", "nov"):
        assert token not in lowered, token
    assert rule in runner.build_read_instructions()
    assert rule in runner.build_reassess_instructions("supervision")
    assert rule in runner.build_reassess_instructions("direct")
    job = {"id": "unused-for-text"}
    answer = {"id": 1, "payload": {"choice": "x"}}
    assert rule in runner.build_resume_instructions(
        job["id"], answer, "supervision")
    assert rule in runner.build_resume_instructions(
        job["id"], answer, "direct")
