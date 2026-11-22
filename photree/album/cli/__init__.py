import typer

app = typer.Typer(
    name="album",
    help="Album management commands.",
    no_args_is_help=True,
)

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from . import check_cmd as check_cmd
from . import detect_faces_cmd as detect_faces_cmd
from . import export_cmd as export_cmd
from . import fix_cmd as fix_cmd
from . import fix_exif_cmd as fix_exif_cmd
from . import fix_ios_cmd as fix_ios_cmd
from . import import_check_cmd as import_check_cmd
from . import import_cmd as import_cmd
from . import init_cmd as init_cmd
from . import list_media_cmd as list_media_cmd
from . import mv_media_cmd as mv_media_cmd
from . import refresh_cmd as refresh_cmd
from . import rm_media_cmd as rm_media_cmd
from . import show_cmd as show_cmd
from . import stats_cmd as stats_cmd
