from quantbot.baseball.bookmaker_policy import (
    is_playable_bookmaker,
    normalize_bookmaker,
)


def test_playable_bookmaker_allowlist_is_exact() -> None:
    assert normalize_bookmaker(" Bet365 ") == "bet365"
    assert normalize_bookmaker("1XBET") == "1xbet"
    assert is_playable_bookmaker("Bet365") is True
    assert is_playable_bookmaker("1XBET") is True
    assert is_playable_bookmaker("Pinnacle") is False
    assert is_playable_bookmaker("Superbet") is False
    assert is_playable_bookmaker("Mozzart") is False
    assert is_playable_bookmaker("bet365-extra") is False
