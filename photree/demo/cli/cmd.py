"""CLI commands for demo and development purposes."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from ...album import output as album_output
from ...album.integrity.output import format_integrity_checks
from ...album.preflight import output as preflight_output
from ...album.integrity.testkit import (
    FULL_INTEGRITY_FAILURES,
    FULL_INTEGRITY_OK,
)
from ...album.preflight.testkit import PREFLIGHT_FAILURES, PREFLIGHT_OK, PREFLIGHT_OTHER
from ...album.importer import output as importer_output
from ...album.importer.testkit.preflight import (
    IC_CHECK_OK,
    IC_CHECK_WARNINGS,
    PREFLIGHT_FAILURES as IMPORT_PREFLIGHT_FAILURES,
    PREFLIGHT_OK as IMPORT_PREFLIGHT_OK,
)
from ...album.importer.testkit.validation import VALIDATION_ERRORS

console = Console()

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


@demo_app.command("output")
def output_cmd() -> None:
    """Display all output/troubleshoot functions with fake data."""

    # ── album.output ─────────────────────────────────────────────

    _panel(
        "preflight_output.sips_check(available=True)",
        preflight_output.sips_check(True),
    )

    _panel(
        "preflight_output.sips_check(available=False)",
        preflight_output.sips_check(False),
    )

    _panel(
        "preflight_output.sips_troubleshoot()",
        preflight_output.sips_troubleshoot(),
    )

    _panel(
        "album_output.album_dir_check — album (all present)",
        preflight_output.album_dir_check(
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
    )

    _panel(
        "album_output.album_dir_check — album (some missing)",
        preflight_output.album_dir_check(
            present=("orig-img", "orig-vid", "main-img"),
            missing=(
                "edit-img",
                "edit-vid",
                "main-vid",
                "main-jpg",
            ),
        ),
    )

    _panel(
        "album_output.album_dir_check — import (to-import present)",
        preflight_output.album_dir_check(
            present=("to-import",),
            missing=(),
        ),
    )

    _panel(
        "album_output.album_dir_check — import (to-import missing)",
        preflight_output.album_dir_check(
            present=(),
            missing=("to-import",),
        ),
    )

    _panel(
        "album_output.refresh_jpeg_summary()",
        album_output.refresh_jpeg_summary(converted=12, copied=3, skipped=1),
    )

    _panel(
        "album_output.refresh_browsable_summary()",
        album_output.refresh_browsable_summary(
            heic_copied=15,
            mov_copied=3,
            jpeg_converted=12,
            jpeg_copied=3,
            jpeg_skipped=1,
        ),
    )

    _panel(
        "album_output.rm_upstream_summary()",
        album_output.rm_upstream_summary(
            heic_jpeg=2,
            heic_browsable=3,
            heic_rendered=5,
            heic_orig=6,
            mov_rendered=1,
            mov_orig=1,
        ),
    )

    # ── format_album_preflight_checks / format_album_preflight_troubleshoot ──

    _panel(
        "integrity_output.format_integrity_checks (all ok)",
        format_integrity_checks(FULL_INTEGRITY_OK),
    )

    _panel(
        "integrity_output.format_integrity_checks (failures)",
        format_integrity_checks(FULL_INTEGRITY_FAILURES),
    )

    _panel(
        "album_output.format_album_preflight_checks (ios, all ok)",
        preflight_output.format_album_preflight_checks(PREFLIGHT_OK),
    )

    _panel(
        "album_output.format_album_preflight_checks (ios, failures)",
        preflight_output.format_album_preflight_checks(PREFLIGHT_FAILURES),
    )

    _panel(
        "album_output.format_album_preflight_checks (other)",
        preflight_output.format_album_preflight_checks(PREFLIGHT_OTHER),
    )

    _panel(
        "album_output.format_album_preflight_troubleshoot (failures)",
        preflight_output.format_album_preflight_troubleshoot(
            PREFLIGHT_FAILURES, album_dir="/path/to/album"
        )
        or "(none)",
    )

    _panel(
        "album_output.format_album_preflight_troubleshoot (all ok — returns None)",
        preflight_output.format_album_preflight_troubleshoot(
            PREFLIGHT_OK, album_dir="/path/to/album"
        )
        or "(none)",
    )

    # ── importer.output ──────────────────────────────────────────

    _panel(
        "importer_output.selection_dir_check (ok)",
        importer_output.selection_dir_check(
            Path("/albums/trip-paris/to-import"), found=True
        ),
    )

    _panel(
        "importer_output.selection_dir_check (not found)",
        importer_output.selection_dir_check(
            Path("/albums/trip-paris/to-import"), found=False
        ),
    )

    _panel(
        "importer_output.selection_dir_check (empty)",
        importer_output.selection_dir_check(
            Path("/albums/trip-paris/to-import"), found=True, empty=True
        ),
    )

    _panel(
        "importer_output.selection_dir_troubleshoot (not found)",
        importer_output.selection_dir_troubleshoot(
            Path("/albums/trip-paris/to-import"), found=False
        ),
    )

    _panel(
        "importer_output.selection_dir_troubleshoot (empty)",
        importer_output.selection_dir_troubleshoot(
            Path("/albums/trip-paris/to-import"), found=True
        ),
    )

    _panel(
        "importer_output.image_capture_dir_check_output (not found)",
        importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=False
        ),
    )

    _panel(
        "importer_output.image_capture_dir_check_output (warnings)",
        importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, check=IC_CHECK_WARNINGS
        ),
    )

    _panel(
        "importer_output.image_capture_dir_check_output (ok)",
        importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, check=IC_CHECK_OK
        ),
    )

    _panel(
        "importer_output.image_capture_dir_check_output (preflight skipped)",
        importer_output.image_capture_dir_check_output(
            Path("~/Pictures/iPhone"), found=True, preflight_skipped=True
        ),
    )

    _panel(
        "importer_output.image_capture_dir_troubleshoot()",
        importer_output.image_capture_dir_troubleshoot(IC_CHECK_WARNINGS),
    )

    # ── format_preflight_checks / format_preflight_troubleshoot ──

    _panel(
        "importer_output.format_preflight_checks (all ok)",
        importer_output.format_preflight_checks(IMPORT_PREFLIGHT_OK),
    )

    _panel(
        "importer_output.format_preflight_checks (failures)",
        importer_output.format_preflight_checks(IMPORT_PREFLIGHT_FAILURES),
    )

    _panel(
        "importer_output.format_preflight_troubleshoot (failures)",
        importer_output.format_preflight_troubleshoot(IMPORT_PREFLIGHT_FAILURES)
        or "(none)",
    )

    _panel(
        "importer_output.format_preflight_troubleshoot (all ok — returns None)",
        importer_output.format_preflight_troubleshoot(IMPORT_PREFLIGHT_OK) or "(none)",
    )

    _panel(
        "importer_output.batch_album_importing()",
        importer_output.batch_album_importing("trip-paris"),
    )

    _panel(
        "importer_output.batch_album_skipped()",
        importer_output.batch_album_skipped("empty-album", "no to-import/ folder"),
    )

    _panel(
        "importer_output.batch_summary()",
        importer_output.batch_summary(imported=5, skipped=2),
    )

    _panel(
        "importer_output.validation_errors()",
        importer_output.validation_errors("trip-paris", VALIDATION_ERRORS),
    )

    _panel(
        "importer_output.unprocessed_selection_files()",
        importer_output.unprocessed_selection_files(("IMG_0001.HEIC", "IMG_0002.HEIC")),
    )

    # ── album stats ─────────────────────────────────────────────

    from ...album.stats.output import format_album_stats, format_gallery_stats
    from ...album.stats.testkit import ALBUM_STATS, GALLERY_STATS

    console.print("\n[bold cyan]── format_album_stats ──[/bold cyan]\n")
    console.print(format_album_stats(ALBUM_STATS))

    # ── gallery stats ───────────────────────────────────────────

    console.print("\n[bold cyan]── format_gallery_stats ──[/bold cyan]\n")
    console.print(format_gallery_stats(GALLERY_STATS))


@demo_app.command("seed")
def seed_cmd(
    base_dir: Annotated[
        Optional[Path],
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
    from textwrap import dedent

    from rich.syntax import Syntax
    from rich.text import Text

    from ...album.importer.testkit import seed_demo

    resolved_base = (
        base_dir
        if base_dir is not None
        else Path(tempfile.mkdtemp(prefix="photree-demo-"))
    )

    result = seed_demo(resolved_base, album_name=album_name)

    ic_count = len(list(result.image_capture_dir.iterdir()))
    sel_count = len(list(result.selection_dir.iterdir()))

    # Summary panel
    rows = [
        ("Seed directory", str(result.base_dir)),
        ("Image Capture", f"image-capture/ ({ic_count} files)"),
        ("Album", f"{album_name}/"),
        ("Selection", f"to-import/ ({sel_count} files)"),
    ]
    label_w = max(len(label) for label, _ in rows)
    summary = Text("\n").join(
        Text.assemble(
            (f"{label:<{label_w}}  ", "bold"),
            value,
        )
        for label, value in rows
    )
    console.print(Panel(summary, border_style="blue", padding=(0, 1)))

    # Commands panel
    commands = dedent(f"""\
        DEMO="{result.base_dir}"
        IC="$DEMO/image-capture"
        ALBUM="$DEMO/{album_name}"
        SHARE="$DEMO/share"

        # Show the demo directory structure (brew install tree)
        tree "$DEMO"

        # Browse the Image Capture source directory
        ls "$IC"

        # Browse the album selection
        ls "$ALBUM/to-import"

        cd "$ALBUM"

        # Import from Image Capture
        photree album import -s "$IC"

        # Browse the album after import
        tree .

        # Check album integrity
        photree album check

        # Optimize (replace copies with symlinks)
        photree album optimize --link-mode symlink

        # Export to a shared directory
        mkdir -p "$SHARE" && touch "$SHARE/.photree-share"
        photree export album --share-dir "$SHARE" --album-layout main-jpg

        # Show the album tree after export
        tree .""")
    console.print(
        Panel(
            Syntax(
                commands,
                "bash",
                theme="monokai",
                background_color="default",
                word_wrap=True,
            ),
            title="[bold]Try[/bold]",
            border_style="green",
            padding=(0, 1),
        )
    )
