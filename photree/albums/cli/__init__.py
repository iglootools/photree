from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    name="albums",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)


DIR_OPTION = Annotated[
    Path | None,
    typer.Option(
        "--dir",
        "-d",
        help="Base directory to recursively scan for albums.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]

ALBUM_DIR_OPTION = Annotated[
    list[Path] | None,
    typer.Option(
        "--album-dir",
        "-a",
        help="Album directory (repeatable).",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.albums.cli import check_cmd as check_cmd
from photree.albums.cli import detect_faces_cmd as detect_faces_cmd
from photree.albums.cli import export_cmd as export_cmd
from photree.albums.cli import fix_cmd as fix_cmd
from photree.albums.cli import fix_ios_cmd as fix_ios_cmd
from photree.albums.cli import import_check_cmd as import_check_cmd
from photree.albums.cli import import_cmd as import_cmd
from photree.albums.cli import init_cmd as init_cmd
from photree.albums.cli import list_cmd as list_cmd
from photree.albums.cli import list_media_cmd as list_media_cmd
from photree.albums.cli import refresh_cmd as refresh_cmd
from photree.albums.cli import rename_from_csv_cmd as rename_from_csv_cmd
from photree.albums.cli import stats_cmd as stats_cmd
