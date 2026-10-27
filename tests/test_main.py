from app.main import hello


def test_hello_shows_night_shift():
    body = hello()
    assert "Night Shift" in body
