from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import BaseballSettings
from .raw_archive import ArchiveReceipt, LocalRawPayloadArchive, RawPayloadArchive


class BaseballAPIError(RuntimeError):
    pass


class BaseballAPIBudgetExceeded(BaseballAPIError):
    pass


class BaseballAPIClient:
    """API-Sports Baseball client with cache, archive, and per-run budget."""

    def __init__(
        self,
        settings: BaseballSettings,
        *,
        raw_archive: RawPayloadArchive | None = None,
    ) -> None:
        settings.validate()
        self.settings = settings
        self.request_count = 0
        self.cache_hits = 0
        self.raw_archive = raw_archive or LocalRawPayloadArchive(
            settings.raw_archive_dir
        )
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def remaining_budget(self) -> int:
        return max(0, self.settings.api_request_budget - self.request_count)

    def _cache_path(self, endpoint: str, params: dict[str, Any]) -> Path:
        canonical = json.dumps(
            [endpoint, sorted(params.items())],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self.settings.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path) -> list[dict[str, Any]] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if float(payload["expires_at"]) <= time.time():
                return None
            response = payload["response"]
            if isinstance(response, list):
                self.cache_hits += 1
                return response
        except (
            FileNotFoundError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None
        return None

    def _write_cache(
        self,
        path: Path,
        response: list[dict[str, Any]],
        ttl_seconds: int,
    ) -> None:
        if ttl_seconds <= 0:
            return
        payload = {"expires_at": time.time() + ttl_seconds, "response": response}
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def get_with_receipt(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        ttl_seconds: int = 0,
        use_cache: bool = True,
    ) -> tuple[list[dict[str, Any]], ArchiveReceipt | None]:
        """Return API rows plus the durable archive receipt for a fresh request."""

        params = {
            key: value for key, value in (params or {}).items() if value is not None
        }
        cache_path = self._cache_path(endpoint, params)
        if use_cache:
            cached = self._read_cache(cache_path)
            if cached is not None:
                return cached, None

        if not self.settings.api_key:
            raise BaseballAPIError("API_BASEBALL_KEY is not configured")
        if self.request_count >= self.settings.api_request_budget:
            raise BaseballAPIBudgetExceeded(
                "Baseball API budget exhausted at "
                f"{self.settings.api_request_budget} requests"
            )

        query = urlencode(params)
        url = f"{self.settings.api_base_url}/{endpoint.lstrip('/')}"
        if query:
            url = f"{url}?{query}"

        raw = ""
        for attempt in range(self.settings.api_max_attempts):
            if self.request_count >= self.settings.api_request_budget:
                raise BaseballAPIBudgetExceeded(
                    "Baseball API budget exhausted at "
                    f"{self.settings.api_request_budget} requests"
                )
            request = Request(
                url,
                headers={
                    "x-apisports-key": self.settings.api_key,
                    "Accept": "application/json",
                },
                method="GET",
            )
            self.request_count += 1
            try:
                with urlopen(request, timeout=20) as response:
                    raw = response.read().decode("utf-8")
                break
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if retryable and attempt + 1 < self.settings.api_max_attempts:
                    retry_after = (exc.headers or {}).get("Retry-After")
                    self._retry_delay(attempt, retry_after)
                    continue
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                raise BaseballAPIError(
                    f"API HTTP {exc.code} for {endpoint}: {detail}"
                ) from exc
            except (URLError, TimeoutError) as exc:
                if attempt + 1 < self.settings.api_max_attempts:
                    self._retry_delay(attempt)
                    continue
                reason = getattr(exc, "reason", str(exc))
                raise BaseballAPIError(
                    f"API network error for {endpoint}: {reason}"
                ) from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BaseballAPIError(f"API returned invalid JSON for {endpoint}") from exc
        if not isinstance(payload, dict):
            raise BaseballAPIError(f"Unexpected API envelope for {endpoint}")

        receipt = self.raw_archive.archive(endpoint, params, payload)

        errors = payload.get("errors")
        if errors:
            raise BaseballAPIError(f"API error for {endpoint}: {errors}")
        result = payload.get("response")
        if not isinstance(result, list):
            raise BaseballAPIError(f"Unexpected API response for {endpoint}")

        if use_cache:
            self._write_cache(cache_path, result, ttl_seconds)
        return result, receipt

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        *,
        ttl_seconds: int = 0,
    ) -> list[dict[str, Any]]:
        response, _ = self.get_with_receipt(
            endpoint,
            params,
            ttl_seconds=ttl_seconds,
        )
        return response

    def _retry_delay(self, attempt: int, retry_after: str | None = None) -> None:
        delay = self.settings.api_retry_base_seconds * (2**attempt)
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        time.sleep(min(delay, 30.0))

    def games_by_date(self, date_iso: str) -> list[dict[str, Any]]:
        return self.get("games", {"date": date_iso}, ttl_seconds=300)

    def games_by_date_with_receipt(
        self,
        date_iso: str,
    ) -> tuple[list[dict[str, Any]], ArchiveReceipt]:
        """Fetch a fresh schedule page and require durable raw evidence."""

        response, receipt = self.get_with_receipt(
            "games",
            {"date": date_iso},
            use_cache=False,
        )
        if receipt is None:
            raise BaseballAPIError("Fresh games response was not archived")
        return response, receipt

    def game(self, game_id: int) -> list[dict[str, Any]]:
        return self.get("games", {"id": game_id}, ttl_seconds=120)

    def games_by_league_season(
        self,
        league_id: int,
        season: int,
    ) -> list[dict[str, Any]]:
        return self.get(
            "games",
            {"league": league_id, "season": season},
            ttl_seconds=21_600,
        )

    def standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return self.get(
            "standings",
            {"league": league_id, "season": season},
            ttl_seconds=21_600,
        )

    def team_statistics(
        self,
        team_id: int,
        league_id: int,
        season: int,
    ) -> list[dict[str, Any]]:
        return self.get(
            "teams/statistics",
            {"team": team_id, "league": league_id, "season": season},
            ttl_seconds=86_400,
        )

    def player_statistics(
        self,
        player_id: int,
        season: int,
    ) -> list[dict[str, Any]]:
        return self.get(
            "players/statistics",
            {"id": player_id, "season": season},
            ttl_seconds=86_400,
        )

    def odds(self, game_id: int) -> list[dict[str, Any]]:
        return self.get("odds", {"game": game_id}, ttl_seconds=120)

    def odds_with_receipt(
        self,
        game_id: int,
    ) -> tuple[list[dict[str, Any]], ArchiveReceipt]:
        """Fetch fresh odds and require a durable source receipt."""

        response, receipt = self.get_with_receipt(
            "odds",
            {"game": game_id},
            use_cache=False,
        )
        if receipt is None:
            raise BaseballAPIError("Fresh odds response was not archived")
        return response, receipt
