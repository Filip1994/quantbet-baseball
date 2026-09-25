"""PostgreSQL repository for Baseball registered-pick moneyline monitoring."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from .decision_lifecycle import RegisteredPick
from .decision_repository import PostgreSQLMoneylineDecisionRepository
from .evidence import OddsObservation
from .fixture_evidence import FixtureObservation
from .monitoring_lifecycle import (
    ClosingFinalization,
    MonitoringRecord,
    OddsCheckpoint,
    OddsLifecyclePolicy,
    PickOddsLifecycle,
    build_closing_finalization,
    canonical_closing_json,
    monitoring_transition_id,
)


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise TypeError("canonical_record must decode to an object")
    return value


def _closing_from_object(value: Any) -> ClosingFinalization:
    return ClosingFinalization(**_object(value))


class MonitoringConflictError(RuntimeError):
    pass


class ClosingNotDueError(RuntimeError):
    pass


class PostgreSQLMoneylineMonitoringRepository:
    def __init__(self, connection: Any) -> None:
        self.connection = connection
        self.decisions = PostgreSQLMoneylineDecisionRepository(connection)

    def _pick(self, pick_id: str) -> RegisteredPick:
        pick = self.decisions.get_registered_pick(pick_id)
        if pick is None:
            raise LookupError(pick_id)
        return pick

    def _fixture(
        self,
        game_id: str,
        *,
        as_of: datetime,
    ) -> FixtureObservation:
        fixture = self.decisions.latest_fixture_observation(game_id, as_of=as_of)
        if fixture is None:
            raise MonitoringConflictError(
                "no fixture observation exists as of requested time"
            )
        return fixture

    @staticmethod
    def _state_from_row(row: tuple[Any, ...]) -> MonitoringRecord:
        return MonitoringRecord(
            pick_id=str(row[0]),
            state=str(row[1]),
            policy=OddsLifecyclePolicy(
                monitoring_interval_seconds=int(row[3]),
                current_max_age_seconds=int(row[4]),
                closing_max_age_seconds=int(row[5]),
                version=str(row[2]),
            ),
            started_at=row[6].isoformat(),
            next_refresh_at=None if row[7] is None else row[7].isoformat(),
            updated_at=row[8].isoformat(),
            version=int(row[9]),
        )

    def monitoring_state(self, pick_id: str) -> MonitoringRecord | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT pick_id, state, lifecycle_policy_version, "
                "monitoring_interval_seconds, current_max_age_seconds, "
                "closing_max_age_seconds, started_at, next_refresh_at, "
                "updated_at, version FROM pick_monitoring_states WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        return None if row is None else self._state_from_row(row)

    def start_monitoring(
        self,
        pick_id: str,
        *,
        started_at: datetime,
        policy: OddsLifecyclePolicy,
    ) -> MonitoringRecord:
        started = _utc(started_at, "started_at")
        pick = self._pick(pick_id)
        kickoff = datetime.fromisoformat(pick.kickoff_at).astimezone(UTC)
        existing = self.monitoring_state(pick_id)
        if existing is not None:
            return existing

        next_refresh = (
            started
            if started >= kickoff
            else min(
                started + timedelta(seconds=policy.monitoring_interval_seconds),
                kickoff,
            )
        )
        transition_id = monitoring_transition_id(pick_id, "MONITORING_STARTED")
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO pick_monitoring_states "
                    "(pick_id, state, lifecycle_policy_version, "
                    "monitoring_interval_seconds, current_max_age_seconds, "
                    "closing_max_age_seconds, started_at, next_refresh_at, "
                    "updated_at, version) "
                    "VALUES (%s, 'MONITORING', %s, %s, %s, %s, %s, %s, %s, 1)",
                    (
                        pick_id,
                        policy.version,
                        policy.monitoring_interval_seconds,
                        policy.current_max_age_seconds,
                        policy.closing_max_age_seconds,
                        started,
                        next_refresh,
                        started,
                    ),
                )
                cursor.execute(
                    "INSERT INTO pick_monitoring_transitions "
                    "(transition_id, pick_id, transition_type, from_state, "
                    "to_state, occurred_at) "
                    "VALUES (%s, %s, 'MONITORING_STARTED', 'REGISTERED', "
                    "'MONITORING', %s)",
                    (transition_id, pick_id, started),
                )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            existing = self.monitoring_state(pick_id)
            if existing is not None:
                return existing
            raise
        state = self.monitoring_state(pick_id)
        if state is None:
            raise MonitoringConflictError("monitoring start did not persist")
        return state

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
                "SELECT pick_id FROM pick_monitoring_states "
                "WHERE state = 'MONITORING' AND next_refresh_at <= %s "
                "ORDER BY next_refresh_at, pick_id LIMIT %s",
                (current, limit),
            )
            return tuple(str(row[0]) for row in cursor.fetchall())

    def unstarted_pick_ids(self, *, limit: int = 50) -> tuple[str, ...]:
        if limit < 1:
            return ()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.pick_id FROM registered_picks r "
                "LEFT JOIN pick_monitoring_states m ON m.pick_id = r.pick_id "
                "WHERE m.pick_id IS NULL ORDER BY r.registered_at, r.pick_id LIMIT %s",
                (limit,),
            )
            return tuple(str(row[0]) for row in cursor.fetchall())

    def advance_refresh(
        self,
        pick_id: str,
        *,
        refreshed_at: datetime,
    ) -> MonitoringRecord:
        refreshed = _utc(refreshed_at, "refreshed_at")
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT state, monitoring_interval_seconds, version "
                "FROM pick_monitoring_states WHERE pick_id = %s FOR UPDATE",
                (pick_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise MonitoringConflictError("monitoring has not started")
            if row[0] != "MONITORING":
                return self.monitoring_state(pick_id)  # type: ignore[return-value]

            pick = self._pick(pick_id)
            kickoff = datetime.fromisoformat(pick.kickoff_at).astimezone(UTC)
            next_refresh = min(
                refreshed + timedelta(seconds=int(row[1])),
                kickoff,
            )
            cursor.execute(
                "UPDATE pick_monitoring_states SET next_refresh_at = %s, "
                "updated_at = %s, version = version + 1 "
                "WHERE pick_id = %s AND state = 'MONITORING' AND version = %s",
                (next_refresh, refreshed, pick_id, int(row[2])),
            )
            if cursor.rowcount != 1:
                self.connection.rollback()
                raise MonitoringConflictError("monitoring state CAS failed")
        self.connection.commit()
        state = self.monitoring_state(pick_id)
        if state is None:
            raise MonitoringConflictError("monitoring state disappeared")
        return state

    def refresh_context(
        self,
        pick_id: str,
        *,
        as_of: datetime,
    ) -> tuple[RegisteredPick, FixtureObservation]:
        current = _utc(as_of, "as_of")
        return self._pick(pick_id), self._fixture(
            self._pick(pick_id).game_id,
            as_of=current,
        )

    def append_observations(self, records: tuple[OddsObservation, ...]) -> int:
        return self.decisions.append_observations(records)

    def append_fixture_observations(
        self,
        records: tuple[FixtureObservation, ...],
    ) -> int:
        return self.decisions.evidence.append_fixture_observations(records)

    def _complete_pairs(
        self,
        pick: RegisteredPick,
        *,
        available_at: datetime,
        cutoff_at: datetime,
    ) -> tuple[tuple[OddsObservation, OddsObservation], ...]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM odds_observations "
                "WHERE game_id = %s AND market_family = 'moneyline' "
                "AND bookmaker = %s AND market_status = 'open' "
                "AND observed_at < %s AND observed_at <= %s "
                "ORDER BY observed_at, observation_id",
                (
                    pick.game_id,
                    pick.bookmaker,
                    cutoff_at,
                    available_at,
                ),
            )
            rows = cursor.fetchall()

        grouped: dict[str, dict[str, OddsObservation]] = {}
        order: list[str] = []
        for row in rows:
            observation = OddsObservation(**_object(row[0]))
            bucket = grouped.setdefault(observation.observed_at, {})
            if observation.observed_at not in order:
                order.append(observation.observed_at)
            bucket[observation.selection] = observation

        pairs: list[tuple[OddsObservation, OddsObservation]] = []
        for observed_at in order:
            bucket = grouped[observed_at]
            home = bucket.get("home")
            away = bucket.get("away")
            if home is not None and away is not None:
                pairs.append((home, away))
        return tuple(pairs)

    def latest_complete_pair(
        self,
        pick_id: str,
        *,
        available_at: datetime,
        cutoff_at: datetime,
    ) -> tuple[OddsObservation, OddsObservation] | None:
        pick = self._pick(pick_id)
        pairs = self._complete_pairs(
            pick,
            available_at=_utc(available_at, "available_at"),
            cutoff_at=_utc(cutoff_at, "cutoff_at"),
        )
        return None if not pairs else pairs[-1]

    def _closing(self, pick_id: str) -> ClosingFinalization | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT canonical_record FROM pick_closing_finalizations "
                "WHERE pick_id = %s",
                (pick_id,),
            )
            row = cursor.fetchone()
        return None if row is None else _closing_from_object(row[0])

    def finalize_closing(
        self,
        pick_id: str,
        *,
        finalized_at: datetime,
    ) -> ClosingFinalization:
        finalized = _utc(finalized_at, "finalized_at")
        existing = self._closing(pick_id)
        if existing is not None:
            return existing

        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT state, lifecycle_policy_version, "
                "monitoring_interval_seconds, current_max_age_seconds, "
                "closing_max_age_seconds, version "
                "FROM pick_monitoring_states WHERE pick_id = %s FOR UPDATE",
                (pick_id,),
            )
            state_row = cursor.fetchone()
            if state_row is None:
                raise MonitoringConflictError("monitoring has not started")
            if state_row[0] != "MONITORING":
                existing = self._closing(pick_id)
                if existing is not None:
                    return existing
                raise MonitoringConflictError(
                    "monitoring already closed without finalization"
                )

            pick = self._pick(pick_id)
            fixture = self._fixture(pick.game_id, as_of=finalized)
            cutoff = datetime.fromisoformat(fixture.kickoff_at).astimezone(UTC)
            if finalized < cutoff:
                raise ClosingNotDueError("authoritative kickoff cutoff has not passed")

            policy = OddsLifecyclePolicy(
                monitoring_interval_seconds=int(state_row[2]),
                current_max_age_seconds=int(state_row[3]),
                closing_max_age_seconds=int(state_row[4]),
                version=str(state_row[1]),
            )
            pair = self.latest_complete_pair(
                pick_id,
                available_at=cutoff,
                cutoff_at=cutoff,
            )
            finalization = build_closing_finalization(
                pick,
                fixture,
                finalized_at=finalized.isoformat(),
                policy=policy,
                pair=pair,
            )
            canonical = canonical_closing_json(finalization)
            cursor.execute(
                "INSERT INTO pick_closing_finalizations "
                "(finalization_id, pick_id, game_id, fixture_observation_id, "
                "cutoff_at, bookmaker, selection, finalized_at, outcome, "
                "candidate_home_observation_id, candidate_away_observation_id, "
                "closing_observation_id, lifecycle_policy_version, "
                "closing_max_age_seconds, schema_version, canonical_record) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                "%s, %s, %s, %s::jsonb)",
                (
                    finalization.finalization_id,
                    finalization.pick_id,
                    finalization.game_id,
                    finalization.fixture_observation_id,
                    finalization.cutoff_at,
                    finalization.bookmaker,
                    finalization.selection,
                    finalization.finalized_at,
                    finalization.outcome,
                    finalization.candidate_home_observation_id,
                    finalization.candidate_away_observation_id,
                    finalization.closing_observation_id,
                    finalization.lifecycle_policy_version,
                    finalization.closing_max_age_seconds,
                    finalization.schema_version,
                    canonical,
                ),
            )
            cursor.execute(
                "INSERT INTO pick_monitoring_transitions "
                "(transition_id, pick_id, transition_type, from_state, "
                "to_state, occurred_at) "
                "VALUES (%s, %s, 'ODDS_CLOSED', 'MONITORING', "
                "'CLOSED_FOR_ODDS', %s)",
                (
                    monitoring_transition_id(pick_id, "ODDS_CLOSED"),
                    pick_id,
                    finalized,
                ),
            )
            cursor.execute(
                "UPDATE pick_monitoring_states SET state = 'CLOSED_FOR_ODDS', "
                "next_refresh_at = NULL, updated_at = %s, version = version + 1 "
                "WHERE pick_id = %s AND state = 'MONITORING' AND version = %s",
                (finalized, pick_id, int(state_row[5])),
            )
            if cursor.rowcount != 1:
                self.connection.rollback()
                raise MonitoringConflictError("monitoring close CAS failed")
        self.connection.commit()
        stored = self._closing(pick_id)
        if stored is None:
            raise MonitoringConflictError("closing finalization disappeared")
        return stored

    @staticmethod
    def _selected_checkpoint(
        pick: RegisteredPick,
        pair: tuple[OddsObservation, OddsObservation],
        *,
        freshness: str | None = None,
    ) -> OddsCheckpoint:
        selected = pair[0] if pick.selection == "home" else pair[1]
        return OddsCheckpoint.from_observation(selected, freshness=freshness)

    def read_lifecycle(
        self,
        pick_id: str,
        *,
        as_of: datetime,
    ) -> PickOddsLifecycle:
        current_time = _utc(as_of, "as_of")
        pick = self._pick(pick_id)
        state_record = self.monitoring_state(pick_id)
        state = "REGISTERED" if state_record is None else state_record.state
        finalization = self._closing(pick_id)

        if finalization is None:
            fixture = self._fixture(pick.game_id, as_of=current_time)
            cutoff = datetime.fromisoformat(fixture.kickoff_at).astimezone(UTC)
            available = min(current_time, cutoff)
        else:
            cutoff = datetime.fromisoformat(finalization.cutoff_at).astimezone(UTC)
            available = cutoff

        pairs = self._complete_pairs(
            pick,
            available_at=available,
            cutoff_at=cutoff,
        )
        opening = None if not pairs else self._selected_checkpoint(pick, pairs[0])

        maximum_age = (
            1800
            if state_record is None
            else state_record.policy.current_max_age_seconds
        )
        current = None
        if pairs:
            latest = pairs[-1]
            observed = datetime.fromisoformat(latest[0].observed_at).astimezone(UTC)
            age = (available - observed).total_seconds()
            current = self._selected_checkpoint(
                pick,
                latest,
                freshness="FRESH" if age <= maximum_age else "STALE",
            )

        entry_observation = self.decisions.get_observation(pick.entry_observation_id)
        if entry_observation is None:
            raise MonitoringConflictError("entry observation is missing")
        entry = OddsCheckpoint.from_observation(entry_observation)

        closing = None
        closing_outcome = None
        if finalization is not None:
            closing_outcome = finalization.outcome
            if finalization.closing_observation_id is not None:
                closing_observation = self.decisions.get_observation(
                    finalization.closing_observation_id
                )
                if closing_observation is None:
                    raise MonitoringConflictError("closing observation is missing")
                closing = OddsCheckpoint.from_observation(
                    closing_observation,
                    freshness="FRESH",
                )

        history = tuple(self._selected_checkpoint(pick, pair) for pair in pairs)
        markers: dict[str, list[str]] = {}
        for marker, checkpoint in (
            ("OPEN", opening),
            ("ENTRY", entry),
            ("CURRENT", current),
            ("CLOSE", closing),
        ):
            if checkpoint is not None:
                markers.setdefault(checkpoint.observation_id, []).append(marker)

        return PickOddsLifecycle(
            pick_id=pick_id,
            state=state,
            opening=opening,
            entry=entry,
            current=current,
            closing=closing,
            closing_outcome=closing_outcome,
            history=history,
            markers={key: tuple(value) for key, value in markers.items()},
        )
