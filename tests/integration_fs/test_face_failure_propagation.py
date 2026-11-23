"""
Face detection failures must reach the user, like JPEG failures do.

An image whose face detection failed is silently missing from clustering, so
every command that refreshes derived data (album import, albums/gallery
refresh, gallery import) reports it and exits 1 rather than claiming success.
"""

from pathlib import Path

from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.importer.album_import import AlbumImportResult
from photree.album.importer.batch import result_failure
from photree.album.importer.output import import_problems
from photree.album.refresh import AlbumRefreshResult
from photree.albums.cmd_handler.refresh import batch_refresh
from photree.foundation.gallery_metadata import GalleryMetadata, save_gallery_metadata
from photree.foundation.linking import LinkMode
from photree.gallery.cmd_handler.importer import import_failure_of
from photree.gallery.importer import (
    AlbumImportResult as GalleryImportResult,
    import_album,
)
from photree.gallery.output import format_import_failure_labels
from tests.testkit import write_file

_FACE_FAILURES = (
    ("main", FaceFailure("0001", FaceFailureStage.DETECTION, "model exploded")),
)


def _ios_album(album: Path) -> Path:
    write_file(album / "ios-main/orig-img/IMG_0001.HEIC")
    write_file(album / "main-img/IMG_0001.HEIC")
    write_file(album / "main-jpg/IMG_0001.jpg")
    return album


def _refresh_with_face_failures(*_: object, **__: object) -> AlbumRefreshResult:
    return AlbumRefreshResult(face_failures=_FACE_FAILURES)


def test_batch_refresh_counts_face_failures_as_failed(tmp_path: Path) -> None:
    album = _ios_album(tmp_path / "2024-07-14 - Hiking")

    result = batch_refresh(
        [album],
        link_mode_for=lambda _: LinkMode.HARDLINK,
        refresh=_refresh_with_face_failures,
    )

    assert result.refreshed == 0
    assert [f.album_dir for f in result.failures] == [album]
    assert "face detection failed" in result.failures[0].reason
    assert "main/0001 (detection): model exploded" in result.failures[0].reason


def test_gallery_import_exposes_face_failures(tmp_path: Path) -> None:
    gallery = tmp_path / "gallery"
    gallery.mkdir()
    save_gallery_metadata(gallery, GalleryMetadata(link_mode=LinkMode.HARDLINK))
    album = _ios_album(tmp_path / "2024-07-14 - Hiking")

    result = import_album(
        source_dir=album,
        gallery_dir=gallery,
        refresh=_refresh_with_face_failures,
    )

    assert result.face_failures == _FACE_FAILURES
    assert not result.complete
    assert result.target_dir.is_dir(), "the album imported despite the failure"


def test_gallery_batch_import_reports_face_failures(tmp_path: Path) -> None:
    album = tmp_path / "2024-07-14 - Hiking"

    failure = import_failure_of(
        album,
        GalleryImportResult(
            album_name=album.name,
            target_dir=tmp_path / "gallery/albums/2024" / album.name,
            id_generated=False,
            face_failures=_FACE_FAILURES,
        ),
    )

    assert failure is not None
    assert failure.face_failures == _FACE_FAILURES
    assert format_import_failure_labels(failure, tmp_path) == (
        "main/0001 (detection): model exploded",
    )


def test_gallery_batch_import_complete_album_is_not_a_failure(tmp_path: Path) -> None:
    album = tmp_path / "2024-07-14 - Hiking"

    assert (
        import_failure_of(
            album,
            GalleryImportResult(
                album_name=album.name,
                target_dir=tmp_path / "gallery/albums/2024" / album.name,
                id_generated=False,
            ),
        )
        is None
    )


def test_album_import_reports_face_failures() -> None:
    """A problem report is what makes ``album import`` exit 1."""
    report = import_problems(
        AlbumImportResult(face_failures=_FACE_FAILURES),
        "2024-07-14 - Trip",
    )

    assert report is not None
    assert "main/0001 (detection): model exploded" in report
    assert "photree album detect-faces" in report


def test_album_import_without_problems_has_no_report() -> None:
    assert import_problems(AlbumImportResult(), "2024-07-14 - Trip") is None


def test_albums_batch_import_reports_every_partial_failure(tmp_path: Path) -> None:
    failure = result_failure(
        tmp_path,
        AlbumImportResult(face_failures=_FACE_FAILURES),
    )

    assert failure is not None
    assert failure.reason == (
        "face detection failed: main/0001 (detection): model exploded"
    )
