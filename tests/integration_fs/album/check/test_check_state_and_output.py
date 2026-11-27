"""Regression tests for check state detection and integrity output."""

from dataclasses import replace
from io import StringIO
from pathlib import Path

import numpy as np
from rich.console import Console

from photree.album.check import AlbumIntegrityResult
from photree.album.check.exif_cache_state import (
    ExifCacheStateCheck,
    check_exif_cache_state,
)
from photree.album.check.face_state import (
    FaceStateCheck,
    FaceSyncIssue,
    FaceSyncIssueKind,
    check_face_state,
)
from photree.album.check.ios import (
    DuplicateNumber,
    IosMediaSourceIntegrityResult,
    MiscategorizedFile,
    MiscategorizedKind,
)
from photree.album.check.output.album import (
    format_exif_cache_check,
    format_face_state_check,
    format_integrity_checks,
)
from photree.album.check.output.derived import derived_failures_report
from photree.album.check.output.troubleshoot import (
    format_album_preflight_troubleshoot,
)
from photree.album.check.std import OrphanEdits
from photree.album.check.testkit import (
    INTEGRITY_FAILURES,
    IOS_INTEGRITY_OK,
    PREFLIGHT_OK,
    STD_INTEGRITY_FAILURES,
    STD_INTEGRITY_OK,
)
from photree.album.exif_cache.protocol import ExifCache
from photree.album.exif_cache.store import save_exif_cache
from photree.album.faces.failures import FaceFailure, FaceFailureStage
from photree.album.faces.protocol import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_VERSION,
    FaceProcessedKey,
    FaceProcessingState,
)
from photree.album.faces.store import FaceData, save_face_data, save_face_state
from photree.album.faces.testkit import write_legacy_face_data
from photree.album.jpeg import JpegConversionFailure
from photree.album.store.media_source import ios_media_source, std_media_source
from photree.albums.output.check import duplicate_ids_report

MAIN = ios_media_source("main")


def _state(face_count: int) -> FaceProcessingState:
    return FaceProcessingState(
        model_name=DEFAULT_MODEL_NAME,
        model_version=DEFAULT_MODEL_VERSION,
        processed_keys={
            "0410": FaceProcessedKey(
                mtime=1.0,
                file_name="IMG_0410.HEIC",
                face_count=face_count,
                orig_width=4032,
                orig_height=3024,
                thumb_width=640,
                thumb_height=480,
            ),
        },
    )


def _face_data(keys: list[str]) -> FaceData:
    n = len(keys)
    return FaceData(
        keys=np.array(keys, dtype=np.str_),
        face_indices=np.zeros(n, dtype=np.int32),
        det_scores=np.full(n, 0.9, dtype=np.float32),
        bboxes=np.zeros((n, 4), dtype=np.float32),
        landmarks=np.zeros((n, 5, 2), dtype=np.float32),
        embeddings=np.zeros((n, 512), dtype=np.float32),
    )


class TestFaceStateDesync:
    def test_in_sync(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=1))
        save_face_data(tmp_path, "main", _face_data(["0410"]))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.success

    def test_yaml_records_faces_but_npz_missing(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=2))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.npz_yaml_sync_errors == (
            FaceSyncIssue("main", FaceSyncIssueKind.MISSING_NPZ),
        )

    def test_yaml_without_faces_needs_no_npz(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=0))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.success

    def test_npz_without_yaml(self, tmp_path: Path) -> None:
        save_face_data(tmp_path, "main", _face_data(["0410"]))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.npz_yaml_sync_errors == (
            FaceSyncIssue("main", FaceSyncIssueKind.MISSING_YAML),
        )

    def test_legacy_npz_is_reported_not_read(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, "main", _state(face_count=1))
        write_legacy_face_data(tmp_path, "main", np.array(["0410"]))

        check = check_face_state(tmp_path, media_sources=[MAIN])

        assert check is not None
        assert check.npz_yaml_sync_errors == (
            FaceSyncIssue("main", FaceSyncIssueKind.LEGACY_NPZ),
        )


class TestExifCacheState:
    def test_no_cache_dir_is_not_checked(self, tmp_path: Path) -> None:
        assert check_exif_cache_state(tmp_path, [MAIN]) is None

    def test_complete_cache_reports_success(self, tmp_path: Path) -> None:
        save_exif_cache(tmp_path, MAIN.name, ExifCache())

        check = check_exif_cache_state(tmp_path, [MAIN])

        assert check is not None
        assert check.success
        assert "exif cache" in format_exif_cache_check(check)


class TestIntegrityOutputLabels:
    def test_ios_labels_use_media_source_dirs(self) -> None:
        result = AlbumIntegrityResult(
            by_media_source=((ios_media_source("bruno"), IOS_INTEGRITY_OK),),
        )

        output = format_integrity_checks(result)

        assert "bruno-img" in output
        assert "bruno-vid" in output
        assert "bruno-jpg" in output
        assert "main-" not in output


class TestStdDuplicateStems:
    def test_duplicate_stems_are_printed(self) -> None:
        result = AlbumIntegrityResult(
            by_media_source=((std_media_source("nelu"), STD_INTEGRITY_FAILURES),),
        )

        output = format_integrity_checks(result)

        assert "duplicate stems" in output
        assert "stem photo2 has multiple media files" in output

    def test_std_failures_get_suggestions(self) -> None:
        preflight = replace(
            PREFLIGHT_OK,
            integrity=AlbumIntegrityResult(
                by_media_source=((std_media_source("nelu"), STD_INTEGRITY_FAILURES),),
            ),
        )

        troubleshoot = format_album_preflight_troubleshoot(preflight, "album")

        assert troubleshoot is not None
        assert "--refresh-browsable" in troubleshoot
        assert "sharing a stem" in troubleshoot


class TestStdOrphanEdits:
    _RESULT = AlbumIntegrityResult(
        by_media_source=(
            (
                std_media_source("nelu"),
                replace(
                    STD_INTEGRITY_OK,
                    orphan_edits=(OrphanEdits("edit-img", ("b.jpg",)),),
                ),
            ),
        ),
    )

    def test_orphan_edits_are_printed(self) -> None:
        output = format_integrity_checks(self._RESULT)
        assert "orphan edits" in output
        assert "edit-img/: no original with the same stem for b.jpg" in output

    def test_orphan_edits_get_suggestions(self) -> None:
        preflight = replace(PREFLIGHT_OK, integrity=self._RESULT)
        troubleshoot = format_album_preflight_troubleshoot(preflight, "album")
        assert troubleshoot is not None
        assert "Put the original of each orphan edit" in troubleshoot
        assert "--rm-orphan" in troubleshoot


def _render(markup: str) -> str:
    """Print *markup* as the CLI does, and return what the user sees."""
    out = StringIO()
    Console(file=out, width=500, highlight=False, color_system=None).print(markup)
    return out.getvalue()


def _ios_integrity(result: IosMediaSourceIntegrityResult) -> AlbumIntegrityResult:
    return AlbumIntegrityResult(by_media_source=((MAIN, result),))


class TestIosIntegrityFailureOutput:
    def test_duplicate_numbers_name_every_file(self) -> None:
        result = _ios_integrity(
            replace(
                IOS_INTEGRITY_OK,
                duplicate_numbers=(
                    DuplicateNumber(
                        "edit-img",
                        "7658",
                        ("IMG_E7658 [1].HEIC", "IMG_E7658.JPG"),
                    ),
                ),
            ),
        )

        output = _render(format_integrity_checks(result))

        assert "✗ duplicate numbers: 1 issue(s)" in output
        assert (
            "edit-img/: number 7658 has multiple media files with same prefix:"
            " IMG_E7658 [1].HEIC, IMG_E7658.JPG"
        ) in output

    def test_miscategorized_files_say_what_they_look_like(self) -> None:
        output = _render(format_integrity_checks(INTEGRITY_FAILURES))

        assert "✗ file categorization: 2 issue(s)" in output
        assert (
            "IMG_E0410.HEIC in orig-img/ looks like an edited file (IMG_E prefix)"
        ) in output
        assert (
            "IMG_0100.HEIC in edit-img/ looks like an original file (no E/O prefix)"
        ) in output

    def test_miscategorized_file_names_are_escaped(self) -> None:
        result = _ios_integrity(
            replace(
                IOS_INTEGRITY_OK,
                miscategorized=(
                    MiscategorizedFile(
                        "IMG_O0001 [copy].AAE",
                        "orig-img",
                        MiscategorizedKind.EDITED_SIDECAR_IN_ORIG,
                    ),
                ),
            ),
        )

        output = _render(format_integrity_checks(result))

        assert (
            "IMG_O0001 [copy].AAE in orig-img/ looks like an edited sidecar" in output
        )


class TestCacheCheckOutput:
    def test_face_sync_issues_are_listed_with_their_fix(self) -> None:
        check = FaceStateCheck(
            model_mismatch=True,
            npz_yaml_sync_errors=(
                FaceSyncIssue("main [old]", FaceSyncIssueKind.MISSING_NPZ),
                FaceSyncIssue("nelu", FaceSyncIssueKind.ARRAY_LENGTHS),
            ),
        )

        output = _render(format_face_state_check(check))

        assert "✗ face state (3 issue(s))" in output
        assert "model version mismatch" in output
        assert "main [old]: .yaml records faces but the .npz is missing" in output
        assert "nelu: .npz array lengths inconsistent" in output
        assert "photree album detect-faces --redetect" in output

    def test_exif_cache_lists_at_most_five_sources(self) -> None:
        sources = tuple(f"ms{i} [x]" for i in range(7))

        output = _render(format_exif_cache_check(ExifCacheStateCheck(sources)))

        assert "✗ exif cache (7 issue(s))" in output
        assert "missing cache: ms0 [x], ms1 [x], ms2 [x], ms3 [x], ms4 [x]" in output
        assert "ms5 [x]" not in output
        assert "... and 2 more" in output


class TestMediaSourceConflictTroubleshoot:
    def test_conflicting_names_are_listed_and_escaped(self) -> None:
        preflight = replace(PREFLIGHT_OK, media_source_conflicts=("main", "trip [1]"))

        troubleshoot = format_album_preflight_troubleshoot(preflight, "album")

        assert troubleshoot is not None
        assert (
            "Media source name(s) used by both an iOS and a std archive:"
            " main, trip [1]."
        ) in _render(troubleshoot)


class TestDerivedFailuresReport:
    def test_each_failure_is_listed_with_a_retry_command(self) -> None:
        report = derived_failures_report(
            (("main", JpegConversionFailure("IMG_0001 [a].HEIC", "sips failed")),),
            (("main", FaceFailure("0002", FaceFailureStage.DETECTION, "bad image")),),
            "2024 [trip]",
        )

        output = _render(report)

        assert "✗ jpeg: 1 file(s) could not be converted" in output
        assert "main/IMG_0001 [a].HEIC: sips failed" in output
        assert (
            "Run 'photree album refresh --refresh-jpeg --album-dir \"2024 [trip]\"'"
        ) in output
        assert "✗ face detection failed for 1 image(s)" in output
        assert "main/0002 (detection): bad image" in output
        assert "Run 'photree album detect-faces --album-dir \"2024 [trip]\"'" in output


class TestDuplicateIdsReport:
    def test_each_duplicated_id_lists_its_albums(self, tmp_path: Path) -> None:
        paths = [tmp_path / "2024 [a]", tmp_path / "2024 [b]"]

        report = duplicate_ids_report(
            "album",
            {"0123": paths},
            tmp_path,
            lambda album_id: f"album_{album_id}",
        )

        assert _render(report).splitlines() == [
            "✗ duplicate album id: album_0123",
            "    2024 [a]",
            "    2024 [b]",
        ]
