"""PostgreSQL settlement, result and CLV repository for Baseball moneyline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .decision_lifecycle import RegisteredPick
from .decision_repository import PostgreSQLMoneylineDecisionRepository
from .evidence import OddsObservation
from .fixture_evidence import FixtureObservation
from .monitoring_lifecycle import ClosingFinalization
from .postgres_repository import EvidenceConflictError, PostgreSQLEvidenceRepository
from .settlement_lifecycle import (
    GameResultFact,
    PickSettlement,
    build_pick_settlement,
    canonical_result_json,
    canonical_settlement_json,
)


def _canonical_text(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to an object")
    return value


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


class PostgreSQLMoneylineSettlementRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.decisions = PostgreSQLMoneylineDecisionRepository(connection)
        self.evidence = PostgreSQLEvidenceRepository(connection)

    def _append_fact(
        self,
        *,
        table: str,
        identity_column: str,
        identity: str,
        columns: tuple[str, ...],
        values: tuple[Any, ...],
    ) -> bool:
        placeholders = ["%s"] * len(values)
        placeholders[-1] = "%s::jsonb"
        insert = (
            f"INSERT INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join(placeholders)}) ON CONFLICT DO NOTHING"
        )
        with self.connection.cursor() as cursor:
            cursor.execute(insert, values)
            if cursor.rowcount == 1:
                self.connection.commit()
                return True
            cursor.execute(
                f"SELECT canonical_record FROM {table} WHERE {identity_column} = %s",
                (identity,),
            )
            row = cursor.fetchone()
        if row is None or _canonical_text(row[0]) != values[-1]:
            self.connection.rollback()
            raise EvidenceConflictError(f"conflicting immutable identity: {identity}")
        self.connection.commit()
        return False

    def append_fixture_observations(
        self,
        records: tuple[FixtureObservation, ...],
    ) -> int:
        return self.evidence.append_fixture_observations(records)

    def append_result(self, record: GameResultFact) -> bool:
        return self._append_fact(
            table="game_result_facts",
            identity_column="result_id",
            identity=record.result_id,
            columns=(
                "result_id",
                "game_id",
                "fixture_observation_id",
                "provider_status",
                "observed_at",
                "home_score",
                "away_score",
                "winner",
                "source_payload_ref",
                "source_payload_checksum",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.result_id,
                record.game_id,
                record.fixture_observation_id,
                record.provider_status,
                record.observed_at,
                record.home_score,
                record.away_score,
                record.winner,
                record.source_payload_ref,
                record.source_payload_checksum,
                record.schema_version,
                canonical_result_json(record),
            ),
        )

    def get_result(self, result_id: str) -> GameResultFact | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM game_result_facts WHERE result_id = %s",
                (result_id,),
            )
            row = cursor.fetchone()
        return None if row is None else GameResultFact(**_object(row[0]))

    def latest_result(self, game_id: str) -> GameResultFact | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM game_result_facts WHERE game_id = %s "
                "ORDER BY observed_at DESC, result_id DESC LIMIT 1",
                (game_id,),
            )
            row = cursor.fetchone()
        return None if row is None else GameResultFact(**_object(row[0]))

    def get_settlement(self, pick_id: str) -> PickSettlement | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_settlements WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        return None if row is None else PickSettlement(**_object(row[0]))

    def _pick(self, pick_id: str) -> RegisteredPick:
        pick = self.decisions.get_registered_pick(pick_id)
        if pick is None:
            raise LookupError(pick_id)
        return pick

    def closing_finalization(self, pick_id: str) -> ClosingFinalization:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_closing_finalizations "
                "WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise LookupError(f"closing finalization missing for {pick_id}")
        return ClosingFinalization(**_object(row[0]))

    def closing_pair(
        self,
        closing: ClosingFinalization,
    ) -> tuple[OddsObservation, OddsObservation] | None:
        if closing.outcome != "CAPTURED":
            return None
        if (
            closing.candidate_home_observation_id is None
            or closing.candidate_away_observation_id is None
        ):
            raise EvidenceConflictError("captured close is missing candidate pair")
        home = self.evidence.get_observation(closing.candidate_home_observation_id)
        away = self.evidence.get_observation(closing.candidate_away_observation_id)
        if home is None or away is None:
            raise EvidenceConflictError("closing observation evidence is missing")
        return home, away

    def due_pick_ids(
        self,
        *,
        as_of: datetime,
        limit: int = 50,
    ) -> tuple[str, ...]:
        current = _utc(as_of, "as_of")
        if limit < 1:
            return ()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id FROM registered_picks r "
                "JOIN pick_closing_finalizations c ON c.pick_id = r.pick_id "
                "LEFT JOIN pick_settlements s ON s.pick_id = r.pick_id "
                "WHERE s.pick_id IS NULL AND c.cutoff_at <= %s "
                "ORDER BY c.cutoff_at, r.pick_id LIMIT %s",
                (current, limit),
            )
            return tuple(str(row[0]) for row in cursor.fetchall())

    def refresh_context(
        self,
        pick_id: str,
        *,
        as_of: datetime,
    ) -> tuple[RegisteredPick, FixtureObservation]:
        current = _utc(as_of, "as_of")
        pick = self._pick(pick_id)
        fixture = self.decisions.latest_fixture_observation(
            pick.game_id,
            as_of=current,
        )
        if fixture is None:
            raise LookupError(f"fixture missing for {pick.game_id}")
        return pick, fixture

    def append_settlement(self, record: PickSettlement) -> bool:
        return self._append_fact(
            table="pick_settlements",
            identity_column="settlement_id",
            identity=record.settlement_id,
            columns=(
                "settlement_id",
                "pick_id",
                "game_id",
                "result_id",
                "closing_finalization_id",
                "selection",
                "entry_odds",
                "settled_at",
                "outcome",
                "profit_per_unit",
                "paper_stake_rsd",
                "paper_profit_rsd",
                "closing_outcome",
                "closing_observation_id",
                "closing_odds",
                "closing_market_probability",
                "clv_probability_delta",
                "clv_price_ratio",
                "clv_status",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.settlement_id,
                record.pick_id,
                record.game_id,
                record.result_id,
                record.closing_finalization_id,
                record.selection,
                record.entry_odds,
                record.settled_at,
                record.outcome,
                record.profit_per_unit,
                record.paper_stake_rsd,
                record.paper_profit_rsd,
                record.closing_outcome,
                record.closing_observation_id,
                record.closing_odds,
                record.closing_market_probability,
                record.clv_probability_delta,
                record.clv_price_ratio,
                record.clv_status,
                record.schema_version,
                canonical_settlement_json(record),
            ),
        )

    def settle(
        self,
        pick_id: str,
        result: GameResultFact,
        *,
        settled_at: datetime,
    ) -> PickSettlement:
        existing = self.get_settlement(pick_id)
        if existing is not None:
            return existing
        pick = self._pick(pick_id)
        closing = self.closing_finalization(pick_id)
        record = build_pick_settlement(
            pick,
            result,
            closing,
            settled_at=_utc(settled_at, "settled_at").isoformat(),
            closing_pair=self.closing_pair(closing),
        )
        try:
            self.append_settlement(record)
        except EvidenceConflictError:
            existing = self.get_settlement(pick_id)
            if existing is not None:
                return existing
            raise
        persisted = self.get_settlement(pick_id)
        if persisted is None:
            raise EvidenceConflictError("settlement did not persist")
        return persisted

    def dashboard_snapshot(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT registered_picks, closing_finalizations, settled_picks, "
                "pending_settlement, wins, losses, pushes, realized_profit_per_unit, "
                "realized_paper_profit_rsd, total_paper_staked_rsd, "
                "clv_available, clv_unavailable, average_clv_probability_delta, "
                "average_clv_price_ratio, paper_yield FROM baseball_moneyline_dashboard"
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("dashboard projection returned no row")
        return {
            "registered_picks": int(row[0]),
            "closing_finalizations": int(row[1]),
            "settled_picks": int(row[2]),
            "pending_settlement": int(row[3]),
            "wins": int(row[4]),
            "losses": int(row[5]),
            "pushes": int(row[6]),
            "realized_profit_per_unit": float(row[7]),
            "realized_paper_profit_rsd": float(row[8]),
            "total_paper_staked_rsd": int(row[9]),
            "clv_available": int(row[10]),
            "clv_unavailable": int(row[11]),
            "average_clv_probability_delta": (
                None if row[12] is None else float(row[12])
            ),
            "average_clv_price_ratio": None if row[13] is None else float(row[13]),
            "paper_yield": None if row[14] is None else float(row[14]),
        }
