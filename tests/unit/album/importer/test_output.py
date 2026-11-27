"""Tests for photree.album.importer.output."""

from dataclasses import replace
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from photree.album.check.std import OrphanEdits
from photree.album.importer.album_import import (
    AlbumImportResult,
    AlbumImportValidation,
    TaskIssue,
)
from photree.album.importer.image_capture import (
    DedupWarning,
    ImportPlan,
    IosSourceImportResult,
    ValidationError,
    ValidationErrorKind,
    ValidationWarning,
    ValidationWarningKind,
)
from photree.album.importer.output import (
    format_preflight_troubleshoot,
    format_task_issue,
    image_capture_dir_check_output,
    import_problems,
    unprocessed_selection_files,
    validation_errors,
    validation_warnings,
)
from photree.album.importer.preflight import ImageCaptureDirCheck
from photree.album.importer.std import StdNoMediaError, StdUnsupportedEntries
from photree.album.importer.testkit.preflight import (
    IC_CHECK_WARNINGS,
    PREFLIGHT_FAILURES,
    PREFLIGHT_OK,
)
from photree.album.importer.testkit.validation import VALIDATION_ERRORS
from photree.album.store.media_source import ios_media_source, std_media_source

_CWD = Path("/albums")


def _render(markup: str) -> str:
    """Print *markup* as the CLI does, and return what the user sees."""
    out = StringIO()
    Console(file=out, width=500, highlight=False, color_system=None).print(markup)
    return out.getvalue()


def _ios_issue(detail: ValidationError | ValidationWarning | DedupWarning) -> TaskIssue:
    return TaskIssue(ios_media_source("main"), detail)


class TestFormatTaskIssue:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                ValidationError("IMG_9.HEIC", ValidationErrorKind.NO_MATCHING_ORIGINAL),
                "IMG_9.HEIC: no matching original found in Image Capture directory",
            ),
            (
                ValidationError(
                    "IMG_1.HEIC",
                    ValidationErrorKind.MULTIPLE_ORIGINALS,
                    img_number="0001",
                    files=("IMG_0001.HEIC", "IMG_0001.JPG"),
                ),
                (
                    "expected 1 original media file for number 0001 but found 2: "
                    "IMG_0001.HEIC, IMG_0001.JPG."
                ),
            ),
            (
                ValidationError(
                    "IMG_1.HEIC",
                    ValidationErrorKind.MULTIPLE_RENDERED,
                    img_number="0001",
                    files=("IMG_E0001.HEIC", "IMG_E0001.JPG"),
                ),
                "expected at most 1 rendered media file for number 0001 but found 2",
            ),
            (
                ValidationError(
                    "IMG_1.HEIC",
                    ValidationErrorKind.ORPHAN_RENDERED_SIDECAR,
                    files=("IMG_O0001.AAE",),
                ),
                "rendered sidecar exists (IMG_O0001.AAE) but no rendered media file",
            ),
            (
                ValidationError(
                    "IMG_1.HEIC",
                    ValidationErrorKind.MULTIPLE_LIVE_PHOTO_COMPANIONS,
                    img_number="0001",
                    files=("IMG_0001.MOV", "IMG_0001.MP4"),
                ),
                "expected 1 Live Photo companion for number 0001 but found 2",
            ),
            (
                ValidationError(
                    "IMG_1.HEIC",
                    ValidationErrorKind.MULTIPLE_RENDERED_LIVE_PHOTO_COMPANIONS,
                    img_number="0001",
                    files=("IMG_E0001.MOV", "IMG_E0001.MP4"),
                ),
                "expected at most 1 rendered Live Photo companion for number 0001",
            ),
            (
                ValidationWarning(
                    "IMG_1.HEIC",
                    ValidationWarningKind.MISSING_ORIGINAL_SIDECAR,
                    "IMG_0001.HEIC",
                ),
                "IMG_1.HEIC: original HEIC (IMG_0001.HEIC) has no AAE sidecar",
            ),
            (
                ValidationWarning(
                    "IMG_1.HEIC",
                    ValidationWarningKind.MISSING_RENDERED_SIDECAR,
                    "IMG_E0001.HEIC",
                ),
                "rendered file (IMG_E0001.HEIC) has no rendered sidecar (IMG_O*.AAE)",
            ),
            (
                DedupWarning("0001", kept="IMG_0001.HEIC", dropped="IMG_0001.JPG"),
                "IMG_0001.JPG dropped in favor of IMG_0001.HEIC (duplicate number",
            ),
        ],
    )
    def test_ios_issue_rendered_with_its_prefix(
        self,
        error: ValidationError | ValidationWarning | DedupWarning,
        expected: str,
    ) -> None:
        rendered = _render(format_task_issue(_ios_issue(error)))
        assert rendered.startswith("[ios:main] ")
        assert expected in rendered

    def test_std_no_media(self) -> None:
        issue = TaskIssue(std_media_source("nelu"), StdNoMediaError())
        assert _render(format_task_issue(issue)) == (
            "[std:nelu] no media files found in orig/ or edit/\n"
        )

    def test_orphan_edits_named_with_the_way_out(self) -> None:
        issue = TaskIssue(std_media_source("nelu"), OrphanEdits("edit", ("b.jpg",)))
        assert _render(format_task_issue(issue)) == (
            "[std:nelu] edit/: no original with the same stem for b.jpg. Std "
            "sources need the original of every edit: put it in orig/ under the "
            "same stem, or move the edit there if it is the only version.\n"
        )

    def test_user_text_in_brackets_survives_rendering(self) -> None:
        issue = _ios_issue(
            ValidationError("[b]IMG_1.HEIC", ValidationErrorKind.NO_MATCHING_ORIGINAL),
        )
        assert "[ios:main] [b]IMG_1.HEIC:" in _render(format_task_issue(issue))

    def test_unsupported_entries_named_with_the_way_out(self) -> None:
        issue = TaskIssue(
            std_media_source("nelu"),
            StdUnsupportedEntries(("orig/sub/", "orig/x.CR2")),
        )
        message = format_task_issue(issue)
        assert "2 entry(ies) would not be imported: orig/sub/, orig/x.CR2" in message
        assert "move the others out of it first" in message

    def test_unsupported_entries_truncated_after_ten(self) -> None:
        entries = tuple(f"orig/{i:02}.txt" for i in range(12))
        issue = TaskIssue(std_media_source("nelu"), StdUnsupportedEntries(entries))
        message = format_task_issue(issue)
        assert "orig/09.txt and 2 more." in message
        assert "orig/10.txt" not in message


class TestValidationErrors:
    def test_every_issue_keeps_its_source_prefix_on_screen(self) -> None:
        rendered = _render(validation_errors("trip [paris]", VALIDATION_ERRORS))
        assert rendered.splitlines() == [
            "Validation failed for trip [paris]:",
            (
                "  - [ios:main] IMG_9999.HEIC: no matching original found in Image "
                "Capture directory"
            ),
            (
                "  - [ios:main] IMG_0410.HEIC: rendered sidecar exists "
                "(IMG_O0410.AAE) but no rendered media file"
            ),
            (
                "  - [std:nelu] orig/: stem photo1 has multiple media files: "
                "photo1.heic, photo1.jpg"
            ),
        ]


class TestValidationWarnings:
    def test_none_without_warnings(self) -> None:
        assert validation_warnings(AlbumImportValidation(album_dir=_CWD)) is None

    def test_dedup_section_comes_first(self) -> None:
        validation = AlbumImportValidation(
            album_dir=_CWD,
            warnings=(
                _ios_issue(
                    ValidationWarning(
                        "IMG_1.HEIC",
                        ValidationWarningKind.MISSING_ORIGINAL_SIDECAR,
                        "IMG_0001.HEIC",
                    ),
                ),
            ),
            dedup_warnings=(
                _ios_issue(DedupWarning("0002", "IMG_0002.HEIC", "IMG_0002.JPG")),
            ),
        )
        rendered = _render(validation_warnings(validation) or "")
        assert rendered.index("Dedup Warnings:") < rendered.index("\nWarnings:")
        assert "  - [ios:main] IMG_0002.JPG dropped" in rendered
        assert "  - [ios:main] IMG_1.HEIC: original HEIC" in rendered


class TestImportProblems:
    def test_none_for_a_clean_import(self) -> None:
        assert import_problems(AlbumImportResult(), "trip") is None

    def test_unprocessed_selection_entries_reported(self) -> None:
        result = AlbumImportResult(
            ios_results=(
                IosSourceImportResult(
                    media_source_name="main",
                    plan=ImportPlan(matches=(), unmatched=()),
                    processed=frozenset(),
                    unprocessed=("IMG_[1].HEIC",),
                ),
            ),
        )
        rendered = _render(import_problems(result, "trip") or "")
        assert "Remove them before the next import" in rendered
        assert "  - IMG_[1].HEIC" in rendered

    def test_unprocessed_selection_files_lists_each(self) -> None:
        rendered = _render(unprocessed_selection_files(("a.HEIC", "b.HEIC")))
        assert rendered.splitlines()[-2:] == ["  - a.HEIC", "  - b.HEIC"]


class TestImageCaptureDirCheckOutput:
    def test_failed_check_lists_every_reason(self) -> None:
        check = replace(IC_CHECK_WARNINGS, subdirectory_names=("[raw]", "temp"))
        rendered = _render(
            image_capture_dir_check_output(
                Path("/pictures/iPhone"),
                found=True,
                check=check,
                cwd=_CWD,
            ),
        )
        assert "Only 2/10 files (20%) have the IMG_ prefix" in rendered
        assert "Found 2 subdirectory(ies): [raw], temp." in rendered

    def test_no_media_reason(self) -> None:
        check = ImageCaptureDirCheck(
            has_media_files=False,
            img_prefixed_count=0,
            total_file_count=1,
            subdirectory_names=(),
        )
        rendered = _render(
            image_capture_dir_check_output(
                Path("/pictures/iPhone"),
                found=True,
                check=check,
                cwd=_CWD,
            ),
        )
        assert "No recognized media files found" in rendered


class TestFormatPreflightTroubleshoot:
    def test_none_when_every_check_passes(self) -> None:
        assert format_preflight_troubleshoot(PREFLIGHT_OK, cwd=_CWD) is None

    def test_failed_image_capture_check_points_to_force(self) -> None:
        troubleshoot = format_preflight_troubleshoot(PREFLIGHT_FAILURES, cwd=_CWD)
        rendered = _render(troubleshoot or "")
        assert "does not look like an Image Capture folder" in rendered
        assert "Only 2/10 files" in rendered
        assert "--force" in rendered

    def test_image_capture_check_ignored_without_an_ios_task(self) -> None:
        result = replace(PREFLIGHT_OK, image_capture_dir_check=IC_CHECK_WARNINGS)
        std_only = replace(result, ios_import_required=False)
        assert format_preflight_troubleshoot(std_only, cwd=_CWD) is None
        assert "--force" in (format_preflight_troubleshoot(result, cwd=_CWD) or "")
