from quantbot.baseball.collector import compact_odds


def test_compact_odds_keeps_game_markets_and_marks_playable_books() -> None:
    payload = [
        {
            "bookmakers": [
                {
                    "name": "Bet365",
                    "bets": [
                        {
                            "name": "Home/Away",
                            "values": [
                                {"value": "Home", "odd": "1.90"},
                                {"value": "Away", "odd": "2.00"},
                            ],
                        },
                        {
                            "name": "Over/Under",
                            "values": [
                                {"value": "Over 8.5", "odd": "1.95"},
                                {"value": "Under 8.5", "odd": "1.85"},
                            ],
                        },
                        {
                            "name": "Player Strikeouts",
                            "values": [{"value": "Over 5.5", "odd": "1.95"}],
                        },
                        {
                            "name": "Over/Under (1st 5 Innings)",
                            "values": [{"value": "Over 4.5", "odd": "1.90"}],
                        },
                    ],
                },
                {
                    "name": "1xbet",
                    "bets": [
                        {
                            "name": "Home/Away",
                            "values": [
                                {"value": "Home", "odd": "1.91"},
                                {"value": "Away", "odd": "1.99"},
                            ],
                        }
                    ],
                },
                {
                    "name": "Pinnacle",
                    "bets": [
                        {
                            "name": "Home/Away",
                            "values": [
                                {"value": "Home", "odd": "1.92"},
                                {"value": "Away", "odd": "1.98"},
                            ],
                        },
                        {
                            "name": "Pitcher Strikeouts",
                            "values": [{"value": "Over 6.5", "odd": "1.90"}],
                        },
                    ],
                },
            ]
        }
    ]

    result = compact_odds(payload)

    assert result["bookmaker_names"] == ["1xbet", "Bet365", "Pinnacle"]

    bet365 = next(item for item in result["bookmakers"] if item["name"] == "Bet365")
    assert bet365["playable"] is True
    assert {item["name"] for item in bet365["markets"]} == {
        "Home/Away",
        "Over/Under",
    }

    one_x = next(item for item in result["bookmakers"] if item["name"] == "1xbet")
    assert one_x["playable"] is True
    assert [item["name"] for item in one_x["markets"]] == ["Home/Away"]

    pinnacle = next(item for item in result["bookmakers"] if item["name"] == "Pinnacle")
    assert pinnacle["playable"] is False
    assert [item["name"] for item in pinnacle["markets"]] == ["Home/Away"]

    retained = {
        market["name"]
        for bookmaker in result["bookmakers"]
        for market in bookmaker["markets"]
    }
    assert "Player Strikeouts" not in retained
    assert "Pitcher Strikeouts" not in retained
    assert "Over/Under (1st 5 Innings)" not in retained
