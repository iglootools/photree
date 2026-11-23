from pathlib import Path

from photree.common.exif import classify_failed_writes

_PATHS = (Path("a.jpg"), Path("b.jpg"), Path("c.jpg"))


class TestClassifyFailedWrites:
    def test_names_the_files_whose_status_is_not_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["0", "1", "0"], 1) == (Path("b.jpg"),)

    def test_no_failure_when_every_status_is_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["0", "0", "0"], 0) == ()

    def test_blames_every_file_when_statuses_are_missing(self) -> None:
        assert classify_failed_writes(_PATHS, ["0"], 1) == _PATHS

    def test_blames_every_file_when_status_is_not_expanded(self) -> None:
        assert classify_failed_writes(_PATHS, ["${status}"] * 3, 1) == _PATHS

    def test_no_failure_when_unattributable_but_exit_is_zero(self) -> None:
        assert classify_failed_writes(_PATHS, ["${status}"] * 3, 0) == ()
