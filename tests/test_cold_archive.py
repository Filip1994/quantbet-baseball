from pathlib import Path

from quantbot.baseball.cold_archive import LocalColdArchiveStore, sha256_file


def test_local_cold_archive_verifies_and_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl.gz"
    source.write_bytes(b"verified-cold-object")
    checksum = sha256_file(source)

    store = LocalColdArchiveStore(tmp_path / "bucket")
    receipt = store.put_verified_file(
        key="cold-storage/baseball/test/object.jsonl.gz",
        path=source,
        checksum=checksum,
    )

    assert receipt.checksum == checksum
    assert receipt.compressed_bytes == source.stat().st_size
    assert receipt.ref.startswith("file://")

    restored = tmp_path / "restored.jsonl.gz"
    store.download_file(ref=receipt.ref, path=restored)

    assert restored.read_bytes() == source.read_bytes()
    assert sha256_file(restored) == checksum
