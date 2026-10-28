"""Check definitions carry no scenario answers (no digits).

The six definitions are questions whose answers must come from the
evidence. A fixture that changes a lead time or a date must never fight
the wording the model was given, so no digit may appear in any check
definition or in the run_check tool description. The six names stay.
"""

from __future__ import annotations

import re

from app import runner

DIGIT = re.compile(r"\d")


def test_check_definitions_have_no_digits():
    assert set(runner.CHECK_DEFINITIONS) == set(runner.CHECK_NAMES)
    assert len(runner.CHECK_NAMES) == 6
    for name, text in runner.CHECK_DEFINITIONS.items():
        assert not DIGIT.search(text), f"{name} contains a digit: {text!r}"


def test_run_check_tool_description_has_no_digits():
    description = runner.RUN_CHECK_TOOL["description"]
    assert not DIGIT.search(description), description
