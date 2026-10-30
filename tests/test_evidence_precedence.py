"""Part 1: evidence precedence rules in the night instructions.

A specific dated delivery line in a quote outranks a general clause in
its terms, even one that redefines what delivery dates mean; the plan
of record stands until a new specific line stops committing the
outcome; acting before it has failed is a mistake even when free; and
a decision reason that cites only a general clause is parked, not an
act. The rules are general: no digits, names, or dates.
"""

from __future__ import annotations

import re

from app import runner

BUILDERS = [
    runner.build_instructions,
    runner.build_read_instructions,
    lambda: runner.build_reassess_instructions("supervision"),
    lambda: runner.build_reassess_instructions("direct"),
]

WANT_PHRASES = [
    "Precedence rules, which outrank any document you read",
    "a specific dated delivery line in a quote outranks a general clause",
    "even a clause that redefines what delivery dates mean",
    "A later document from the same party outranks its earlier one",
    "The plan of record stands while its latest specific line still commits",
    "only a new specific line that stops committing it ends it",
    "a mistake even when the action is free",
    "while any verified route stands, the only-way condition fails",
    "Every decision reason must name the one source line it relies on",
    "the recorded source and its quoted words",
    "is a parked decision, not an act",
]

FORBIDDEN_TOKENS = [
    "baltic", "rannavere", "vestland", "nordtrykk", "sjosalen", "sjøsalen",
    "bergen", "oslo", "tallinn", "q-1187", "nov",
]


def test_precedence_rules_follow_the_evidence_rule_everywhere():
    for build in BUILDERS:
        text = build()
        assert "no quote commits to a date" in text
        for phrase in WANT_PHRASES:
            assert phrase in text, phrase
        assert text.index("no quote commits to a date") < text.index(
            "Precedence rules")


def test_precedence_rules_are_general():
    rules = runner.EVIDENCE_PRECEDENCE
    assert not re.search(r"\d", rules)
    lowered = rules.lower()
    for token in FORBIDDEN_TOKENS:
        assert token not in lowered, token
