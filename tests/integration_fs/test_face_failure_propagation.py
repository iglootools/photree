"""Face detection failures must reach the user, like JPEG failures do.

An image whose face detection failed is silently missing from clustering, so
every command that refreshes derived data (album import, albums/gallery
refresh, gallery import) reports it and exits 1 rather than claiming success.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.importer import album_import
from photree.album.importer.album_import import AlbumImportResult
from photree.album.refresh import AlbumRefreshResult
from photree.albums.cmd_handler import refresh as refresh_handler
from photree.albums.cmd_handler.refresh import batch_refresh
from photree.cli import app
from photree.fsprotocol import GalleryMetadata, LinkMode, save_gallery_metadata
from photree.gallery.cmd_handler.importer import _import_one
from photree.gallery.import_plan import AlbumPlan, ImportAction
from photree.gallery.importer import AlbumImportResult as GalleryImportResult
from photree.gallery.importer import import_album
from photree.gallery.output import format_import_failure_labels

runner = CliRunner()

_FACE_FAILURES = (
    ("main", FaceFailure("0001", FaceFailureStage.DETECTION, "model exploded")),
)


def _write(path: Path, content: str = "data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _ios_album(album: Path) -> Path:
    _write(album / "ios-main/orig-img/IMG_0001.HEIC")
    _write(album / "main-img/IMG_0001.HEIC")
    _write(album / "main-jpg/IMG_0001.jpg")
    return album


def _refresh_with_face_failures(*_: object, **__: object) -> AlbumRefreshResult:
    return AlbumRefreshResult(face_failures=_FACE_FAILURES)


def test_batch_refresh_counts_face_failures_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    album = _ios_album(tmp_path / "2024-07-14 - Hiking")
    monkeypatch.setattr(
        refresh_handler, "refresh_album_derived_data", _refresh_with_face_failures
    )

    result = batch_refresh([album])

    assert result.refreshed == 0
    assert result.failed_albums == (album,)
    assert "face detection failed" in result.failures[0].reason
    assert "main/0001 (detection): model exploded" in result.failures[0].reason


def test_gallery_import_exposes_face_failures(tmp_path: Path) -> None:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK))
    album = _ios_album(tmp_path / "2024-07-14 - Hiking")

    result = import_album(
        source_dir=album, gallery_dir=gallery, refresh=_refresh_with_face_failures
    )

    assert result.face_failures == _FACE_FAILURES
    assert not result.complete
    assert result.target_dir.is_dir(), "the album imported despite the failure"


def test_gallery_batch_import_reports_face_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import photree.gallery.importer as gallery_importer

    album = tmp_path / "2024-07-14 - Hiking"
    target = tmp_path / "gallery/albums/2024" / album.name

    def _import(**_: object) -> GalleryImportResult:
        return GalleryImportResult(
            album_name=album.name,
            target_dir=target,
            id_generated=False,
            face_failures=_FACE_FAILURES,
        )

    monkeypatch.setattr(gallery_importer, "import_album", _import)

    failure = _import_one(
        AlbumPlan(album, ImportAction.NEW, target),
        tmp_path / "gallery",
        LinkMode.HARDLINK,
        False,
        exiftool=None,
        analyzer_factory=lambda: None,  # type: ignore[arg-type,return-value]
        max_workers=None,
    )

    assert failure is not None
    assert failure.face_failures == _FACE_FAILURES
    assert format_import_failure_labels(failure, tmp_path) == (
        "main/0001 (detection): model exploded",
    )


def test_album_import_reports_face_failures_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("sips", "exiftool"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    album = tmp_path / "2024-07-14 - Trip"
    _write(album / "to-import-std-nelu/orig/DSC_0001.JPG")
    (tmp_path / "ic").mkdir()

    def _import(**_: object) -> AlbumImportResult:
        return AlbumImportResult(face_failures=_FACE_FAILURES)

    monkeypatch.setattr(album_import, "run_import", _import)

    result = runner.invoke(
        app,
        ["album", "import", "-a", str(album), "-s", str(tmp_path / "ic"), "--force"],
    )

    assert result.exit_code == 1
    assert "main/0001 (detection): model exploded" in result.output
    assert "photree album detect-faces" in result.output


def test_albums_batch_import_reports_every_partial_failure(tmp_path: Path) -> None:
    from photree.album.importer.batch import _result_failure

    failure = _result_failure(
        tmp_path,
        AlbumImportResult(face_failures=_FACE_FAILURES),
    )

    assert failure is not None
    assert failure.reason == (
        "face detection failed: main/0001 (detection): model exploded"
    )
