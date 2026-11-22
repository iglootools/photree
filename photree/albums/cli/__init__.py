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
from . import check_cmd as check_cmd
from . import detect_faces_cmd as detect_faces_cmd
from . import export_cmd as export_cmd
from . import fix_cmd as fix_cmd
from . import fix_ios_cmd as fix_ios_cmd
from . import import_check_cmd as import_check_cmd
from . import import_cmd as import_cmd
from . import init_cmd as init_cmd
from . import list_cmd as list_cmd
from . import list_media_cmd as list_media_cmd
from . import refresh_cmd as refresh_cmd
from . import rename_from_csv_cmd as rename_from_csv_cmd
from . import stats_cmd as stats_cmd
