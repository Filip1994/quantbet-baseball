from quantbot.baseball.raw_archive import LocalRawPayloadArchive


def test_local_archive_can_be_read_back_by_checksum(tmp_path) -> None:
    archive = LocalRawPayloadArchive(tmp_path)
    receipt = archive.archive(
        "games",
        {"id": 123},
        {"response": [{"id": 123}]},
    )

    assert archive.verify(receipt.ref, receipt.checksum) is True
    assert archive.verify(receipt.ref, "0" * 64) is False
