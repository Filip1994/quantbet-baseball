"""PostgreSQL persistence for the Baseball moneyline decision lifecycle."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .decision_lifecycle import (
    FinalQuoteVerification,
    ModelPrediction,
    MoneylineEvaluation,
    RegisteredPick,
    canonical_lifecycle_json,
)
from .evidence import OddsObservation
from .fixture_evidence import FixtureObservation
from .postgres_repository import EvidenceConflictError, PostgreSQLEvidenceRepository


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


def _canonical_object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to an object")
    return value


def _verification_from_object(value: Any) -> FinalQuoteVerification:
    payload = _canonical_object(value)
    payload["reason_codes"] = tuple(payload.get("reason_codes") or ())
    return FinalQuoteVerification(**payload)


class PostgreSQLMoneylineDecisionRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
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

    def append_prediction(self, record: ModelPrediction) -> bool:
        return self._append_fact(
            table="model_predictions",
            identity_column="prediction_id",
            identity=record.prediction_id,
            columns=(
                "prediction_id",
                "game_id",
                "model_version",
                "feature_snapshot_ref",
                "source_data_cutoff_at",
                "predicted_at",
                "home_probability",
                "away_probability",
                "uncertainty_metric",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.prediction_id,
                record.game_id,
                record.model_version,
                record.feature_snapshot_ref,
                record.source_data_cutoff_at,
                record.predicted_at,
                record.home_probability,
                record.away_probability,
                record.uncertainty_metric,
                record.schema_version,
                canonical_lifecycle_json(record),
            ),
        )

    def get_prediction(self, prediction_id: str) -> ModelPrediction | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM model_predictions WHERE prediction_id = %s",
                (prediction_id,),
            )
            row = cursor.fetchone()
        return None if row is None else ModelPrediction(**_canonical_object(row[0]))

    def append_evaluation(self, record: MoneylineEvaluation) -> bool:
        return self._append_fact(
            table="value_evaluations",
            identity_column="evaluation_id",
            identity=record.evaluation_id,
            columns=(
                "evaluation_id",
                "prediction_id",
                "game_id",
                "bookmaker",
                "home_observation_id",
                "away_observation_id",
                "selected_observation_id",
                "selection",
                "stage",
                "evaluated_at",
                "quote_observed_at",
                "quote_age_seconds",
                "selected_odds",
                "market_probability",
                "model_probability",
                "fair_decimal_odds",
                "edge",
                "expected_value_per_unit",
                "uncertainty_metric",
                "min_edge",
                "min_expected_value",
                "outcome",
                "reason_code",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.evaluation_id,
                record.prediction_id,
                record.game_id,
                record.bookmaker,
                record.home_observation_id,
                record.away_observation_id,
                record.selected_observation_id,
                record.selection,
                record.stage,
                record.evaluated_at,
                record.quote_observed_at,
                record.quote_age_seconds,
                record.selected_odds,
                record.market_probability,
                record.model_probability,
                record.fair_decimal_odds,
                record.edge,
                record.expected_value_per_unit,
                record.uncertainty_metric,
                record.min_edge,
                record.min_expected_value,
                record.outcome,
                record.reason_code,
                record.schema_version,
                canonical_lifecycle_json(record),
            ),
        )

    def get_evaluation(self, evaluation_id: str) -> MoneylineEvaluation | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM value_evaluations WHERE evaluation_id = %s",
                (evaluation_id,),
            )
            row = cursor.fetchone()
        return None if row is None else MoneylineEvaluation(**_canonical_object(row[0]))

    def begin_verification(
        self,
        record: FinalQuoteVerification,
    ) -> FinalQuoteVerification:
        if record.status != "REQUESTED":
            raise ValueError("begin_verification requires REQUESTED status")
        canonical = canonical_lifecycle_json(record)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO final_quote_verifications "
                "(verification_id, preliminary_evaluation_id, game_id, bookmaker, "
                "selection, requested_at, status, reason_codes, schema_version, "
                "canonical_record) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'REQUESTED', '{}', %s, %s::jsonb) "
                "ON CONFLICT DO NOTHING",
                (
                    record.verification_id,
                    record.preliminary_evaluation_id,
                    record.game_id,
                    record.bookmaker,
                    record.selection,
                    record.requested_at,
                    record.schema_version,
                    canonical,
                ),
            )
            inserted = cursor.rowcount == 1
            cursor.execute(
                "SELECT canonical_record FROM final_quote_verifications "
                "WHERE verification_id = %s",
                (record.verification_id,),
            )
            row = cursor.fetchone()
        if row is None:
            self.connection.rollback()
            raise EvidenceConflictError("verification insert did not resolve")
        existing = _verification_from_object(row[0])
        if not inserted and (
            existing.preliminary_evaluation_id != record.preliminary_evaluation_id
            or existing.game_id != record.game_id
            or existing.bookmaker != record.bookmaker
            or existing.selection != record.selection
        ):
            self.connection.rollback()
            raise EvidenceConflictError(
                f"conflicting verification identity: {record.verification_id}"
            )
        self.connection.commit()
        return existing

    def get_verification(
        self,
        verification_id: str,
    ) -> FinalQuoteVerification | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM final_quote_verifications "
                "WHERE verification_id = %s",
                (verification_id,),
            )
            row = cursor.fetchone()
        return None if row is None else _verification_from_object(row[0])

    def save_terminal_verification(
        self,
        record: FinalQuoteVerification,
    ) -> FinalQuoteVerification:
        if record.status not in {"READY", "REJECTED"}:
            raise ValueError("terminal verification must be READY or REJECTED")
        canonical = canonical_lifecycle_json(record)
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE final_quote_verifications SET status = %s, reason_codes = %s, "
                "returned_home_observation_id = %s, returned_away_observation_id = %s, "
                "final_evaluation_id = %s, decided_at = %s, schema_version = %s, "
                "canonical_record = %s::jsonb "
                "WHERE verification_id = %s AND status = 'REQUESTED'",
                (
                    record.status,
                    list(record.reason_codes),
                    record.returned_home_observation_id,
                    record.returned_away_observation_id,
                    record.final_evaluation_id,
                    record.decided_at,
                    record.schema_version,
                    canonical,
                    record.verification_id,
                ),
            )
            updated = cursor.rowcount == 1
            cursor.execute(
                "SELECT canonical_record FROM final_quote_verifications "
                "WHERE verification_id = %s",
                (record.verification_id,),
            )
            row = cursor.fetchone()
        if row is None:
            self.connection.rollback()
            raise LookupError(record.verification_id)
        existing = _verification_from_object(row[0])
        if not updated and canonical_lifecycle_json(existing) != canonical:
            self.connection.rollback()
            raise EvidenceConflictError(
                f"verification already terminated differently: {record.verification_id}"
            )
        self.connection.commit()
        return existing

    def append_registered_pick(self, record: RegisteredPick) -> bool:
        return self._append_fact(
            table="registered_picks",
            identity_column="pick_id",
            identity=record.pick_id,
            columns=(
                "pick_id",
                "verification_id",
                "final_evaluation_id",
                "prediction_id",
                "game_id",
                "market_family",
                "selection",
                "bookmaker",
                "entry_observation_id",
                "entry_odds",
                "model_probability",
                "market_probability",
                "fair_decimal_odds",
                "edge",
                "expected_value_per_unit",
                "uncertainty_metric",
                "model_version",
                "feature_snapshot_ref",
                "source_data_cutoff_at",
                "kickoff_at",
                "registered_at",
                "paper_mode",
                "state",
                "paper_stake_minor",
                "currency",
                "schema_version",
                "canonical_record",
            ),
            values=(
                record.pick_id,
                record.verification_id,
                record.final_evaluation_id,
                record.prediction_id,
                record.game_id,
                record.market_family,
                record.selection,
                record.bookmaker,
                record.entry_observation_id,
                record.entry_odds,
                record.model_probability,
                record.market_probability,
                record.fair_decimal_odds,
                record.edge,
                record.expected_value_per_unit,
                record.uncertainty_metric,
                record.model_version,
                record.feature_snapshot_ref,
                record.source_data_cutoff_at,
                record.kickoff_at,
                record.registered_at,
                record.paper_mode,
                record.state,
                record.paper_stake_minor,
                record.currency,
                record.schema_version,
                canonical_lifecycle_json(record),
            ),
        )

    def get_registered_pick(self, pick_id: str) -> RegisteredPick | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM registered_picks WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        return None if row is None else RegisteredPick(**_canonical_object(row[0]))

    def append_observations(self, records: tuple[OddsObservation, ...]) -> int:
        return self.evidence.append_observations(records)

    def get_observation(self, observation_id: str) -> OddsObservation | None:
        return self.evidence.get_observation(observation_id)

    def get_registered_pick_for_verification(
        self,
        verification_id: str,
    ) -> RegisteredPick | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM registered_picks WHERE verification_id = %s",
                (verification_id,),
            )
            row = cursor.fetchone()
        return None if row is None else RegisteredPick(**_canonical_object(row[0]))

    def latest_fixture_observation(
        self,
        game_id: str,
        *,
        as_of: datetime,
    ) -> FixtureObservation | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM fixture_observations "
                "WHERE game_id = %s AND observed_at <= %s "
                "ORDER BY observed_at DESC, fixture_observation_id DESC LIMIT 1",
                (game_id, as_of),
            )
            row = cursor.fetchone()
        return None if row is None else FixtureObservation(**_canonical_object(row[0]))

    def latest_moneyline_pair(
        self,
        game_id: str,
        bookmaker: str,
        *,
        as_of: datetime,
        limit: int = 100,
    ) -> tuple[OddsObservation, OddsObservation] | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM odds_observations "
                "WHERE game_id = %s AND market_family = 'moneyline' "
                "AND bookmaker = %s AND market_status = 'open' "
                "AND observed_at <= %s "
                "ORDER BY observed_at DESC, observation_id DESC LIMIT %s",
                (game_id, bookmaker, as_of, limit),
            )
            rows = cursor.fetchall()

        by_time: dict[str, dict[str, OddsObservation]] = {}
        ordered_times: list[str] = []
        for row in rows:
            observation = OddsObservation(**_canonical_object(row[0]))
            bucket = by_time.setdefault(observation.observed_at, {})
            if observation.observed_at not in ordered_times:
                ordered_times.append(observation.observed_at)
            bucket[observation.selection] = observation

        for observed_at in ordered_times:
            bucket = by_time[observed_at]
            home = bucket.get("home")
            away = bucket.get("away")
            if home is not None and away is not None:
                return home, away
        return None
