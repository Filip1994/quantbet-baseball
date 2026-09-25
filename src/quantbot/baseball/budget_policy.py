"""Fail-closed API budget policy for the Baseball Railway cron."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class BaseballAPIBudgetPolicy:
    daily_limit: int = 7500
    cron_interval_minutes: int = 15
    reserved_headroom: int = 750
    policy_version: str = "BASEBALL_API_BUDGET_V1"

    def __post_init__(self) -> None:
        if self.daily_limit < 1:
            raise ValueError("daily_limit must be positive")
        if self.cron_interval_minutes < 1:
            raise ValueError("cron_interval_minutes must be positive")
        if 1440 % self.cron_interval_minutes != 0:
            raise ValueError("cron interval must divide evenly into one day")
        if not 0 <= self.reserved_headroom < self.daily_limit:
            raise ValueError("reserved_headroom must be within the daily limit")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if self.usable_daily_budget < self.runs_per_day:
            raise ValueError("usable daily budget must allow at least one request per run")

    @property
    def runs_per_day(self) -> int:
        return 1440 // self.cron_interval_minutes

    @property
    def usable_daily_budget(self) -> int:
        return self.daily_limit - self.reserved_headroom

    @property
    def per_run_hard_limit(self) -> int:
        return self.usable_daily_budget // self.runs_per_day

    @property
    def maximum_scheduled_daily_requests(self) -> int:
        return self.per_run_hard_limit * self.runs_per_day

    @property
    def effective_headroom(self) -> int:
        return self.daily_limit - self.maximum_scheduled_daily_requests

    @property
    def budget_safe(self) -> bool:
        return (
            self.per_run_hard_limit > 0
            and self.maximum_scheduled_daily_requests <= self.usable_daily_budget
            and self.effective_headroom >= self.reserved_headroom
        )

    def to_dict(self) -> dict[str, int | str | bool]:
        payload = asdict(self)
        payload.update(
            {
                "runs_per_day": self.runs_per_day,
                "usable_daily_budget": self.usable_daily_budget,
                "per_run_hard_limit": self.per_run_hard_limit,
                "maximum_scheduled_daily_requests": self.maximum_scheduled_daily_requests,
                "effective_headroom": self.effective_headroom,
                "budget_safe": self.budget_safe,
            }
        )
        return payload

    @classmethod
    def from_env(cls, *, daily_limit: int = 7500) -> "BaseballAPIBudgetPolicy":
        interval = int(os.getenv("BASEBALL_CRON_INTERVAL_MINUTES", "15").strip())
        reserve_default = max(1, math.ceil(daily_limit * 0.10))
        reserve = int(
            os.getenv("BASEBALL_API_RESERVED_HEADROOM", str(reserve_default)).strip()
        )
        return cls(
            daily_limit=daily_limit,
            cron_interval_minutes=interval,
            reserved_headroom=reserve,
        )
