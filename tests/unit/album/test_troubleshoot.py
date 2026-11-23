import shlex

import pytest
from rich.text import Text

from photree.album.check.troubleshoot import suggest_exif_fixes
from photree.album.exif_date_check import ExifMismatch

_ALBUM = "albums/2024/2024-07-14 - Bob's [trip]"


def _rendered(lines: list[str]) -> list[str]:
    """Return the lines as Rich prints them, markup resolved, indentation dropped."""
    return [Text.from_markup(line).plain.strip() for line in lines]


def _fix_command(lines: list[str]) -> list[str]:
    """Return the words of the suggested `fix-exif` command, as the shell splits it."""
    [command] = [line for line in _rendered(lines) if "fix-exif" in line]
    return shlex.split(command)


def _mismatch(
    file_name: str = "main-jpg/IMG_0001.jpg",
    timestamp: str = "2023-01-01T10:00:00",
    upstream_files: tuple[str, ...] = (),
) -> ExifMismatch:
    return ExifMismatch(
        file_name=file_name,
        timestamp=timestamp,
        upstream_files=upstream_files,
    )


class TestSuggestExifFixes:
    def test_fix_targets_upstream_files_with_quoted_paths(self) -> None:
        lines = suggest_exif_fixes(
            (
                _mismatch(
                    upstream_files=(
                        "ios-main/orig-img/IMG_0001.HEIC",
                        "ios-main/edit-img/IMG_E0001.HEIC",
                    ),
                ),
            ),
            album_date="2024-07-14",
            album_dir=_ALBUM,
        )

        assert _fix_command(lines) == [
            "photree",
            "album",
            "fix-exif",
            "--set-date",
            "2024-07-14",
            f"{_ALBUM}/ios-main/edit-img/IMG_E0001.HEIC",
            f"{_ALBUM}/ios-main/orig-img/IMG_0001.HEIC",
        ]

    def test_fix_skips_aae_sidecars(self) -> None:
        lines = suggest_exif_fixes(
            (
                _mismatch(
                    upstream_files=(
                        "ios-main/orig-img/IMG_0001.HEIC",
                        "ios-main/orig-img/IMG_0001.AAE",
                    ),
                ),
            ),
            album_date="2024-07-14",
            album_dir=_ALBUM,
        )

        assert _fix_command(lines)[5:] == [
            f"{_ALBUM}/ios-main/orig-img/IMG_0001.HEIC",
        ]

    def test_fix_falls_back_to_the_file_itself_without_upstream(self) -> None:
        lines = suggest_exif_fixes(
            (_mismatch(),),
            album_date="2024-07-14",
            album_dir=_ALBUM,
        )

        assert _fix_command(lines)[5:] == [f"{_ALBUM}/main-jpg/IMG_0001.jpg"]

    @pytest.mark.parametrize(
        ("album_date", "exif_date"),
        [
            ("2024", "2024-01-01"),
            ("2024-07", "2024-07-01"),
            ("2024-07-14", "2024-07-14"),
            ("2024-07-14--2024-07-16", "2024-07-14"),
            ("2024-07--2024-08", "2024-07-01"),
        ],
    )
    def test_fix_date_is_the_first_day_of_the_album_date(
        self,
        album_date: str,
        exif_date: str,
    ) -> None:
        lines = suggest_exif_fixes(
            (_mismatch(),),
            album_date=album_date,
            album_dir=_ALBUM,
        )

        assert _fix_command(lines)[4] == exif_date

    def test_suggestions_follow_the_fix_with_a_rebuild(self) -> None:
        lines = _rendered(
            suggest_exif_fixes(
                (_mismatch(),),
                album_date="2024-07-14",
                album_dir=_ALBUM,
            ),
        )

        rebuild = next(line for line in lines if "album refresh" in line)
        assert shlex.split(rebuild) == [
            "photree",
            "album",
            "refresh",
            "--album-dir",
            _ALBUM,
            "--refresh-browsable",
        ]

    def test_move_and_rm_suggestions_are_dry_runs_with_quoted_paths(self) -> None:
        lines = _rendered(
            suggest_exif_fixes(
                (_mismatch(file_name="main-jpg/a [1].jpg"),),
                album_date="2024-07-14",
                album_dir=_ALBUM,
            ),
        )

        mv = shlex.split(next(line for line in lines if "mv-media" in line))
        rm = shlex.split(next(line for line in lines if "rm-media" in line))
        assert mv == [
            "photree",
            "album",
            "mv-media",
            "--dry-run",
            "-s",
            _ALBUM,
            "-d",
            "DEST_ALBUM",
            "main-jpg/a [1].jpg",
        ]
        assert rm == [
            "photree",
            "album",
            "rm-media",
            "--dry-run",
            "-a",
            _ALBUM,
            "main-jpg/a [1].jpg",
        ]

    def test_mismatches_are_grouped_by_date_in_order(self) -> None:
        lines = _rendered(
            suggest_exif_fixes(
                (
                    _mismatch(file_name="main-jpg/b.jpg", timestamp="2023-05-02T09:00"),
                    _mismatch(file_name="main-jpg/a.jpg", timestamp="2023-01-01T09:00"),
                    _mismatch(file_name="main-jpg/c.jpg", timestamp="2023-05-02T11:00"),
                ),
                album_date="2024-07-14",
                album_dir=_ALBUM,
            ),
        )

        headings = [line for line in lines if line.endswith("file(s)):")]
        assert headings == ["# 2023-01-01 (1 file(s)):", "# 2023-05-02 (2 file(s)):"]
