from quantbot.baseball.collector import compact_odds


def test_compact_odds_keeps_playable_books_and_game_level_target_markets() -> None:
    payload = [
        {
            "bookmakers": [
                {
                    "name": "bet365",
                    "bets": [
                        {
                            "name": "Moneyline",
                            "values": [{"value": "Home", "odd": "1.90"}],
                        },
                        {
                            "name": "Over/Under",
                            "values": [{"value": "Over 8.5", "odd": "1.95"}],
                        },
                        {
                            "name": "Player Strikeouts",
                            "values": [{"value": "Over 5.5", "odd": "1.95"}],
                        },
                    ],
                },
                {
                    "name": "1xbet",
                    "bets": [
                        {
                            "name": "Home/Away",
                            "values": [{"value": "Away", "odd": "2.10"}],
                        }
                    ],
                },
                {
                    "name": "OtherBook",
                    "bets": [
                        {
                            "name": "Home/Away",
                            "values": [{"value": "Away", "odd": "2.10"}],
                        },
                        {
                            "name": "Over/Under",
                            "values": [{"value": "Under 8.5", "odd": "1.90"}],
                        },
                        {
                            "name": "Player Hits",
                            "values": [{"value": "Over 1.5", "odd": "2.20"}],
                        },
                        {
                            "name": "Unrelated",
                            "values": [{"value": "X", "odd": "9.00"}],
                        },
                    ],
                },
            ]
        }
    ]

    result = compact_odds(payload)

    # Coverage retains the actual provider universe for intelligence/audit.
    assert result["bookmaker_names"] == ["1xbet", "OtherBook", "bet365"]

    bet365 = next(item for item in result["bookmakers"] if item["name"] == "bet365")
    assert bet365["playable"] is True
    assert {item["name"] for item in bet365["markets"]} == {
        "Moneyline",
        "Over/Under",
    }
    assert all(item["name"] != "Player Strikeouts" for item in bet365["markets"])

    one_x = next(item for item in result["bookmakers"] if item["name"] == "1xbet")
    assert one_x["playable"] is True
    assert [item["name"] for item in one_x["markets"]] == ["Home/Away"]

    other = next(item for item in result["bookmakers"] if item["name"] == "OtherBook")
    assert other["playable"] is False
    assert {item["name"] for item in other["markets"]} == {
        "Home/Away",
        "Over/Under",
    }
    assert all(item["name"] != "Player Hits" for item in other["markets"])
