"""Zero-provider-request inventory of archived API-Sports Baseball payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .raw_archive import S3RawPayloadArchive, archive_from_env


def _leaf_paths(value: Any, prefix: str = "") -> list[str]:
    paths: set[str] = set()

    def walk(item: Any, path: str) -> None:
        if isinstance(item, dict):
            if not item:
                paths.add(path or "<root>")
                return
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                walk(child, child_path)
            return
        if isinstance(item, list):
            list_path = f"{path}[]" if path else "[]"
            if not item:
                paths.add(list_path)
                return
            walk(item[0], list_path)
            return
        paths.add(path or "<root>")

    walk(value, prefix)
    return sorted(paths)


def _response_summary(document: dict[str, Any]) -> dict[str, Any]:
    payload = document.get("payload")
    if not isinstance(payload, dict):
        return {"response_type": "missing-payload", "leaf_paths": []}

    response = payload.get("response")
    summary: dict[str, Any] = {
        "endpoint": document.get("endpoint"),
        "params": document.get("params"),
        "captured_at": document.get("captured_at"),
        "response_type": type(response).__name__,
        "leaf_paths": _leaf_paths(response),
    }

    if isinstance(response, list):
        summary["row_count"] = len(response)
        if response and isinstance(response[0], dict):
            summary["row_keys"] = sorted(response[0])
    elif isinstance(response, dict):
        summary["response_keys"] = sorted(response)

    if document.get("endpoint") == "odds/bets" and isinstance(response, list):
        summary["markets"] = [
            {"id": row.get("id"), "name": row.get("name")}
            for row in response
            if isinstance(row, dict)
        ]

    if document.get("endpoint") == "odds/bookmakers" and isinstance(response, list):
        summary["bookmakers"] = [
            {"id": row.get("id"), "name": row.get("name")}
            for row in response
            if isinstance(row, dict)
        ]

    return summary


def run_raw_provider_inventory(
    root: Path,
    *,
    day: str,
) -> dict[str, Any]:
    """Inspect today's archived provider payloads without calling API-Sports."""

    archive = archive_from_env(root / "data/baseball/raw", require_remote=True)
    if not isinstance(archive, S3RawPayloadArchive):
        raise RuntimeError("Remote S3 archive is required for raw provider inventory")

    prefix = f"api-sports-baseball/{day}/"
    listed = archive.client.list_objects_v2(
        Bucket=archive.bucket,
        Prefix=prefix,
        MaxKeys=1000,
    )
    objects = listed.get("Contents") or []

    relevant = []
    wanted = {
        "teams_statistics",
        "odds_bets",
        "odds_bookmakers",
        "standings",
    }
    for obj in objects:
        key = str(obj.get("Key") or "")
        if not key.endswith(".json"):
            continue
        if not any(f"_{token}_" in key for token in wanted):
            continue
        relevant.append(key)

    documents: list[dict[str, Any]] = []
    for key in sorted(relevant):
        result = archive.client.get_object(Bucket=archive.bucket, Key=key)
        body = result["Body"].read()
        document = json.loads(body.decode("utf-8"))
        if isinstance(document, dict):
            documents.append(document)

    summaries = [_response_summary(document) for document in documents]

    return {
        "status": "COMPLETE",
        "provider_requests": 0,
        "day": day,
        "objects_scanned": len(objects),
        "relevant_objects": len(relevant),
        "summaries": summaries,
    }
