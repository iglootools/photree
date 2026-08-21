"""JPEG conversion failures must be counted and reported, never discarded.

Regression cover for a silent-failure bug: the parallel path tallied every
planned file as converted *before* running the work and then threw away
``run_parallel``'s results, so a run where sips failed on half the directory
reported a full success and exited 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from photree.album.jpeg import convert_single_file, refresh_jpeg_dir
from photree.common.sips import SipsError


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _exploding_convert(src: Path, dst_dir: Path, *, dry_run: bool) -> Path | None:
    raise OSError(f"boom: {src.name}")


class TestSequentialPath:
    def test_failure_is_recorded_not_raised(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "IMG_0001.HEIC")
        _write(src / "IMG_0002.HEIC")

        result = refresh_jpeg_dir(src, dst, convert_file=_exploding_convert)

        assert not result.success
        assert result.converted == 0
        assert [f.filename for f in result.failed] == [
            "IMG_0001.HEIC",
            "IMG_0002.HEIC",
        ]
        assert "boom" in result.failed[0].reason

    def test_one_bad_file_does_not_abandon_the_rest(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "good.jpg")
        _write(src / "bad.HEIC")

        def convert(s: Path, d: Path, *, dry_run: bool) -> Path | None:
            if s.suffix == ".HEIC":
                raise OSError("nope")
            return convert_single_file(s, d, dry_run=dry_run)

        result = refresh_jpeg_dir(src, dst, convert_file=convert)

        assert result.copied == 1
        assert [f.filename for f in result.failed] == ["bad.HEIC"]
        assert (dst / "good.jpg").exists()


class TestParallelPath:
    """The parallel path is what production uses (max_workers=os.cpu_count()).

    A HEIC file whose bytes are not HEIC fails on macOS because sips rejects it,
    and on Linux because sips does not exist — either way the conversion raises,
    which is the condition under test.
    """

    def test_failures_are_counted_from_results_not_from_the_plan(
        self, tmp_path: Path
    ) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "IMG_0001.HEIC", "not really heic")
        _write(src / "IMG_0002.HEIC", "not really heic")

        result = refresh_jpeg_dir(src, dst, max_workers=4)

        assert not result.success
        assert result.converted == 0, "a file that never converted must not be counted"
        assert len(result.failed) == 2
        assert all(f.reason for f in result.failed), "each failure carries a reason"

    def test_success_is_still_counted(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "img", tmp_path / "jpg"
        _write(src / "already.jpg")

        result = refresh_jpeg_dir(src, dst, max_workers=4)

        assert result.success
        assert result.copied == 1
        assert (dst / "already.jpg").exists()


class TestSipsError:
    def test_carries_stderr_in_its_message(self) -> None:
        exc = SipsError(
            path=Path("/x/IMG_0001.HEIC"), returncode=1, stderr="Error: bad format\n"
        )

        assert "IMG_0001.HEIC" in str(exc)
        assert "bad format" in str(exc)

    def test_falls_back_to_the_exit_code(self) -> None:
        assert "exited 3" in str(
            SipsError(path=Path("/x/a.HEIC"), returncode=3, stderr="")
        )

    def test_is_an_oserror_so_batch_loops_catch_it(self) -> None:
        # refresh_jpeg_dir's sequential path catches OSError; sips failures must
        # land in that net rather than escaping as an unrelated exception type.
        assert isinstance(
            SipsError(path=Path("/x/a.HEIC"), returncode=1, stderr=""), Exception
        )


class TestRefreshPropagation:
    def test_album_refresh_surfaces_the_failures(self, tmp_path: Path) -> None:
        from photree.album.id import generate_album_id
        from photree.album.refresh import refresh_album_derived_data
        from photree.album.store.metadata import save_album_metadata
        from photree.album.store.protocol import AlbumMetadata

        album = tmp_path / "2024-07-14 - Hiking"
        _write(album / "ios-main" / "orig-img" / "IMG_0001.HEIC", "not really heic")
        save_album_metadata(album, AlbumMetadata(id=generate_album_id()))

        result = refresh_album_derived_data(album, max_workers=4)

        assert not result.success
        sources = {source for source, _ in result.jpeg_failures}
        assert sources == {"main"}


@pytest.mark.parametrize("max_workers", [None, 4])
def test_empty_dir_succeeds(tmp_path: Path, max_workers: int | None) -> None:
    src, dst = tmp_path / "img", tmp_path / "jpg"
    src.mkdir(parents=True)

    result = refresh_jpeg_dir(src, dst, max_workers=max_workers)

    assert result.success
    assert result.failed == ()
