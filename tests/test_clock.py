"""Clock tests: deadline arithmetic lives in code, not the model."""

from datetime import timedelta

from app import clock


def test_deadline_chain_is_cutoff_minus_10_minus_20():
    assert clock.fmt(clock.cutoff()) == "02:00"
    assert clock.answer_deadline() == clock.cutoff() - timedelta(minutes=10)
    assert clock.fmt(clock.answer_deadline()) == "01:50"
    assert clock.latest_safe_notification() == clock.answer_deadline() - timedelta(
        minutes=20
    )
    assert clock.fmt(clock.latest_safe_notification()) == "01:30"


def test_virtual_times_map_to_nov3_nov4_oslo():
    assert clock.at("21:30").date().isoformat() == "2026-11-03"
    assert clock.at("00:38").date().isoformat() == "2026-11-04"
    assert clock.at("21:30") < clock.at("00:38") < clock.cutoff()
    assert clock.is_at_or_before("01:50", "02:00")
    assert not clock.is_at_or_before("01:51", "01:50")
    assert "01:30" in clock.deadline_facts_line()
    assert "01:50" in clock.deadline_facts_line()
    assert "02:00" in clock.deadline_facts_line()
