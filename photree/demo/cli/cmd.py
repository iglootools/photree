"""CLI commands for demo and development purposes."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Annotated

import typer
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from ...album.check import output as preflight_output
from ...album.check.output import format_integrity_checks
from ...album.check.testkit import (
    INTEGRITY_FAILURES,
    INTEGRITY_OK,
    PREFLIGHT_FAILURES,
    PREFLIGHT_OK,
    PREFLIGHT_STD,
)
from ...album.fix.output import (
    rm_upstream_summary,
)
from ...album.importer import output as importer_output
from ...album.importer.testkit import SeedResult, seed_demo
from ...album.importer.testkit.preflight import (
    IC_CHECK_OK,
    IC_CHECK_WARNINGS,
)
from ...album.importer.testkit.preflight import (
    PREFLIGHT_FAILURES as IMPORT_PREFLIGHT_FAILURES,
)
from ...album.importer.testkit.preflight import (
    PREFLIGHT_OK as IMPORT_PREFLIGHT_OK,
)
from ...album.importer.testkit.validation import VALIDATION_ERRORS
from ...clihelpers.console import console

demo_app = typer.Typer(
    name="demo",
    help="Demo commands for development.",
    no_args_is_help=True,
)


def _panel(title: str, content: str) -> None:
    console.print(
        Panel(
            content,
            title=f"[bold]{title}[/bold]",
            title_align="left",
            border_style="cyan",
            padding=(0, 1),
            expand=False,
        )
    )
    console.print()


# (title, render) pairs, rendered lazily so ``photree --help`` does not build
# every sample. Grouped by the module whose output functions they exercise.
_SAMPLES: tuple[tuple[str, Callable[[], str]], ...] = (
    (
        "preflight_output.sips_check(available=True)",
        lambda: preflight_output.sips_check(True),
    ),
    (
        "preflight_output.sips_check(available=False)",
        lambda: preflight_output.sips_check(False),
    ),
    (
        "preflight_output.sips_troubleshoot()",
        lambda: preflight_output.sips_troubleshoot(),
    ),
    (
        "album_output.album_dir_check — album (all present)",
        lambda: preflight_output.album_dir_check(
            present=(
                "orig-img",
                "orig-vid",
                "edit-img",
                "edit-vid",
                "main-img",
                "main-vid",
                "main-jpg",
            ),
            missing=(),
        ),
    ),
    (
        "album_output.album_dir_check — album (some missing)",
        lambda: preflight_output.album_dir_check(
            present=("orig-img", "orig-vid", "main-img"),
            missing=(
                "edit-img",
                "edit-vid",
                "main-vid",
                "main-jpg",
            ),
        ),
    ),
    (
        "album_output.album_dir_check — import (to-import-ios-main present)",
        lambda: preflight_output.album_dir_check(
            present=("to-import-ios-main",),
            missing=(),
        ),
    ),
    (
        "album_output.album_dir_check — import (to-import-ios-main missing)",
        lambda: preflight_output.album_dir_check(
            present=(),
            missing=("to-import-ios-main",),
        ),
    ),
    (
        "album_output.rm_upstream_summary()",
        lambda: rm_upstream_summary(
            heic_jpeg=2,
            heic_browsable=3,
            heic_rendered=5,
            heic_orig=6,
            mov_rendered=1,
            mov_orig=1,
        ),
    ),
    (
        "integrity_output.format_integrity_checks (all ok)",
        lambda: format_integrity_checks(INTEGRITY_OK),
    ),
    (
        "integrity_output.format_integrity_checks (failures)",
        lambda: format_integrity_checks(INTEGRITY_FAILURES),
    ),
    (
        "album_output.format_album_preflight_checks (ios, all ok)",
        lambda: preflight_output.format_album_preflight_checks(PREFLIGHT_OK),
    ),
    (
        "album_output.format_album_preflight_checks (ios, failures)",
        lambda: preflight_output.format_album_preflight_checks(PREFLIGHT_FAILURES),
    ),
    (
        "album_output.format_album_preflight_checks (other)",
        lambda: preflight_output.format_album_preflight_checks(PREFLIGHT_STD),
    ),
    (
        "album_output.format_album_preflight_troubleshoot (failures)",
        lambda: (
            preflight_output.format_album_preflight_troubleshoot(
                PREFLIGHT_FAILURES, album_dir="/path/to/album"
            )
            or "(none)"
        ),
    ),
    (
        "album_output.format_album_preflight_troubleshoot (all ok — returns None)",
        lambda: (
            preflight_output.format_album_preflight_troubleshoot(
                PREFLIGHT_OK, album_dir="/path/to/album"
            )
            or "(none)"
        ),
    ),
    (
        "importer_output.import_tasks_check (ok)",
        lambda: importer_output.import_tasks_check(
            Path("/albums/trip-paris"), found=True
        ),
    ),
    (
        "importer_output.import_tasks_check (not found)",
        lambda: importer_output.import_tasks_check(
            Path("/albums/trip-paris"), found=False
        ),
    ),
    (
        "importer_output.import_tasks_check (empty)",
        lambda: importer_output.import_tasks_check(
            Path("/albums/trip-paris"), found=True, empty=True
        ),
    ),
    (
        "importer_output.import_tasks_troubleshoot",
        lambda: importer_output.import_tasks_troubleshoot(Path("/albums/trip-paris")),
    ),
    (
        "importer_output.image_capture_dir_check_output (not found)",
        lambda: importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=False
        ),
    ),
    (
        "importer_output.image_capture_dir_check_output (warnings)",
        lambda: importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, check=IC_CHECK_WARNINGS
        ),
    ),
    (
        "importer_output.image_capture_dir_check_output (ok)",
        lambda: importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, check=IC_CHECK_OK
        ),
    ),
    (
        "importer_output.image_capture_dir_check_output (preflight skipped)",
        lambda: importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, preflight_skipped=True
        ),
    ),
    (
        "importer_output.image_capture_dir_troubleshoot()",
        lambda: importer_output.image_capture_dir_troubleshoot(IC_CHECK_WARNINGS),
    ),
    (
        "importer_output.format_preflight_checks (all ok)",
        lambda: importer_output.format_preflight_checks(IMPORT_PREFLIGHT_OK),
    ),
    (
        "importer_output.format_preflight_checks (failures)",
        lambda: importer_output.format_preflight_checks(IMPORT_PREFLIGHT_FAILURES),
    ),
    (
        "importer_output.format_preflight_troubleshoot (failures)",
        lambda: (
            importer_output.format_preflight_troubleshoot(IMPORT_PREFLIGHT_FAILURES)
            or "(none)"
        ),
    ),
    (
        "importer_output.format_preflight_troubleshoot (all ok — returns None)",
        lambda: (
            importer_output.format_preflight_troubleshoot(IMPORT_PREFLIGHT_OK)
            or "(none)"
        ),
    ),
    (
        "importer_output.batch_album_importing()",
        lambda: importer_output.batch_album_importing("trip-paris"),
    ),
    (
        "importer_output.batch_album_skipped()",
        lambda: importer_output.batch_album_skipped(
            "empty-album", "no to-import-{ios,std}-<name> directory"
        ),
    ),
    (
        "importer_output.batch_summary()",
        lambda: importer_output.batch_summary(imported=5, skipped=2),
    ),
    (
        "importer_output.validation_errors()",
        lambda: importer_output.validation_errors("trip-paris", VALIDATION_ERRORS),
    ),
    (
        "importer_output.unprocessed_selection_files()",
        lambda: importer_output.unprocessed_selection_files(
            ("IMG_0001.HEIC", "IMG_0002.HEIC")
        ),
    ),
)


@demo_app.command("output")
def output_cmd() -> None:
    """Display all output/troubleshoot functions with fake data."""
    from ...album.stats.output import format_album_stats, format_albums_stats
    from ...album.stats.testkit import ALBUM_STATS, ALBUMS_STATS

    for title, render in _SAMPLES:
        _panel(title, render())

    console.print("\n[bold cyan]── format_album_stats ──[/bold cyan]\n")
    console.print(format_album_stats(ALBUM_STATS))
    console.print("\n[bold cyan]── format_albums_stats ──[/bold cyan]\n")
    console.print(format_albums_stats(ALBUMS_STATS))


def _summary_panel(result: SeedResult, album_name: str) -> Panel:
    """Aligned label/value table of what was seeded."""
    rows = [
        ("Seed directory", str(result.base_dir)),
        (
            "Image Capture",
            f"image-capture/ ({len(list(result.image_capture_dir.iterdir()))} files)",
        ),
        ("Album", f"{album_name}/"),
        (
            "Selection",
            f"to-import-ios-main/ ({len(list(result.selection_dir.iterdir()))} files)",
        ),
    ]
    label_w = max(len(label) for label, _ in rows)
    summary = Text("\n").join(
        Text.assemble((f"{label:<{label_w}}  ", "bold"), value) for label, value in rows
    )
    return Panel(summary, border_style="blue", padding=(0, 1))


def _demo_commands(base_dir: Path, album_name: str) -> str:
    """Copy-pasteable shell walkthrough of the seeded demo."""
    return dedent(f"""\
        DEMO="{base_dir}"
        IC="$DEMO/image-capture"
        ALBUM="$DEMO/{album_name}"
        SHARE="$DEMO/share"

        # Show the demo directory structure (brew install tree)
        tree "$DEMO"

        # Browse the Image Capture source directory
        ls "$IC"

        # Browse the album selection
        ls "$ALBUM/to-import-ios-main"

        cd "$ALBUM"

        # Import from Image Capture
        photree album import -s "$IC"

        # Browse the album after import
        tree .

        # Check album integrity
        photree album check

        # Export to a shared directory
        mkdir -p "$SHARE" && touch "$SHARE/.photree-share"
        photree album export --share-dir "$SHARE" --album-layout browsable-jpg

        # Show the album tree after export
        tree .""")


def _commands_panel(result: SeedResult, album_name: str) -> Panel:
    return Panel(
        Syntax(
            _demo_commands(result.base_dir, album_name),
            "bash",
            theme="monokai",
            background_color="default",
            word_wrap=True,
        ),
        title="[bold]Try[/bold]",
        border_style="green",
        padding=(0, 1),
    )


@demo_app.command("seed")
def seed_cmd(
    base_dir: Annotated[
        Path | None,
        typer.Option(
            "--base-dir",
            "-d",
            help="Directory to create the demo in. Default: creates a temp directory.",
            file_okay=False,
        ),
    ] = None,
    album_name: Annotated[
        str,
        typer.Option(
            "--album-name",
            help="Album name.",
        ),
    ] = "2024-06-15 - Demo Album",
) -> None:
    """Generate a demo environment with Image Capture files and an album."""
    resolved_base = (
        base_dir
        if base_dir is not None
        else Path(tempfile.mkdtemp(prefix="photree-demo-"))
    )
    result = seed_demo(resolved_base, album_name=album_name)
    console.print(_summary_panel(result, album_name))
    console.print(_commands_panel(result, album_name))
