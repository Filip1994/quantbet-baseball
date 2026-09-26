from datetime import UTC, datetime, timedelta

from quantbot.baseball.dashboard import BaseballDashboard


class FakeRepository:
    def __init__(self, *, stale_worker: bool = False) -> None:
        self.stale_worker = stale_worker

    def check_database(self) -> bool:
        return True

    def snapshot(self):
        now = datetime.now(UTC)
        runtime_time = now - (
            timedelta(hours=2) if self.stale_worker else timedelta(minutes=5)
        )
        return {
            "generated_at": now,
            "health": {
                "fixture_observations": 260,
                "distinct_fixtures": 95,
                "odds_observations": 0,
                "distinct_quote_games": 0,
                "bookmakers": 0,
                "pick_events": 0,
                "model_predictions": 0,
                "value_evaluations": 0,
                "final_quote_verifications": 0,
                "registered_picks": 0,
                "monitored_picks": 0,
                "closing_finalizations": 0,
                "game_result_facts": 0,
                "settled_picks": 0,
                "clv_available": 0,
                "collection_cycles": 4,
                "runtime_cycles": 72,
                "standing_snapshots": 60,
                "distinct_standing_teams": 30,
                "latest_standings_observed_at": (now - timedelta(hours=2)).isoformat(),
                "team_statistics_snapshots": 18,
                "distinct_team_statistics_teams": 18,
                "latest_team_statistics_observed_at": (
                    now - timedelta(hours=2)
                ).isoformat(),
                "reference_catalog_snapshots": 2,
                "latest_catalog_observed_at": (now - timedelta(days=1)).isoformat(),
                "game_history_snapshots": 480,
                "distinct_game_history_games": 480,
                "game_history_final_score_rows": 470,
                "game_history_hit_rows": 460,
                "game_history_error_rows": 455,
                "game_history_inning_rows": 468,
                "game_history_extra_inning_games": 21,
                "game_history_archived_rows": 480,
                "latest_game_history_observed_at": (
                    now - timedelta(hours=3)
                ).isoformat(),
                "official_mlb_pregame_snapshots": 0,
                "latest_official_mlb_observed_at": None,
                "mlb_identity_team_mappings": 30,
                "mlb_identity_mapping_versions": 1,
                "latest_mlb_identity_mapping_at": (
                    now - timedelta(hours=1)
                ).isoformat(),
                "mlb_identity_game_links": 15,
                "latest_mlb_identity_link_at": (now - timedelta(hours=1)).isoformat(),
                "latest_fixture_observed_at": (now - timedelta(hours=1)).isoformat(),
                "latest_odds_observed_at": None,
                "latest_collection_finished_at": None,
                "latest_runtime_finished_at": runtime_time.isoformat(),
            },
            "runtime": {
                "run_id": "run-1",
                "started_at": runtime_time - timedelta(seconds=3),
                "finished_at": runtime_time,
                "collection_enabled": False,
                "mode": "storage-ready",
                "status": "ready",
                "stats": {
                    "api_requests": 12,
                    "cycle_request_cap": 75,
                    "due_events": 8,
                    "not_due_events": 6,
                    "games_selected": 8,
                    "odds_calls": 8,
                    "observations_inserted": 24,
                },
            },
            "gates": {
                "CANARY": {
                    "target": "CANARY",
                    "assessed_at": runtime_time,
                    "verdict": "READY",
                    "reason_codes": [],
                    "daily_request_budget": 7500,
                    "cycle_request_cap": 75,
                    "cron_interval_minutes": 15,
                    "cycles_per_day": 96,
                    "worst_case_daily_requests": 7200,
                    "request_headroom": 300,
                    "daily_reserve_required": 250,
                    "paper_mode": True,
                    "collection_enabled": False,
                    "api_key_configured": True,
                    "raw_archive_configured": True,
                    "migrations_current": True,
                    "runtime_fresh": True,
                    "canary_passed": False,
                    "latest_canary_id": "canary-1",
                }
            },
            "canary": {
                "canary_id": "canary-1",
                "finished_at": now - timedelta(hours=4),
                "status": "FAILED",
                "max_api_requests": 8,
                "api_requests": 6,
                "observations_inserted": 0,
                "archive_verified": False,
                "db_write_verified": False,
                "reason_codes": ["POSTGRES_WRITES_NOT_VERIFIED"],
            },
            "performance": {
                "settled_picks": 0,
                "wins": 0,
                "losses": 0,
                "pushes": 0,
                "realized_profit_per_unit": 0,
                "roi_per_unit_staked": None,
                "clv_coverage": None,
                "positive_clv_rate": None,
                "brier_score": None,
                "log_loss": None,
            },
            "money": {
                "settled_stake_minor": 0,
                "realized_profit_minor": 0,
            },
            "breakdown": [],
            "picks": [],
        }


def test_dashboard_distinguishes_running_worker_from_missing_odds() -> None:
    dashboard = BaseballDashboard(FakeRepository())
    data = dashboard.snapshot()
    states = {item.label: item for item in data["statuses"]}

    assert states["Worker"].state == "good"
    assert states["Collection"].state == "locked"
    assert states["Canary"].state == "warn"
    assert states["Odds evidence"].state == "bad"
    assert states["Paper mode"].state == "good"


def test_dashboard_marks_stale_worker_bad() -> None:
    dashboard = BaseballDashboard(FakeRepository(stale_worker=True))
    data = dashboard.snapshot()
    worker = next(item for item in data["statuses"] if item.label == "Worker")

    assert worker.state == "bad"
    assert worker.value == "STALE"


def test_system_page_renders_operational_evidence() -> None:
    html = BaseballDashboard(FakeRepository()).render("tab=system")

    assert "Baseball Operations" in html
    assert "API budget guard" in html
    assert "7500" in html
    assert "Bet365 · 1xBet" in html
    assert "LOCKED" in html
    assert "NO FRESH ODDS" in html
    assert "Latest collection efficiency" in html
    assert "12 / 75" in html
    assert "Obs / request" in html
    assert "2.00" in html
    assert "Primary provider evidence" in html
    assert "Standings" in html
    assert "Team stats" in html
    assert "Game history" in html
    assert "MLB identity" in html


def test_research_and_history_render_empty_states_without_fabrication() -> None:
    dashboard = BaseballDashboard(FakeRepository())

    research = dashboard.render("tab=research")
    history = dashboard.render("tab=history")

    assert "No settled research picks yet." in research
    assert "Primary evidence coverage" in research
    assert "Standings 30 teams" in research
    assert "team stats 18 teams" in research
    assert "MLB identity 30 team maps / 15 game links" in research
    assert (
        "history 480 games (470 final-score, 468 inning-detail, 21 extra-inning)"
        in research
    )
    assert "Paper P/L" in research
    assert "DB-backed" in research
    assert "No registered paper picks yet." in history
    assert "300 RSD" in history or "300 RSD" in research
