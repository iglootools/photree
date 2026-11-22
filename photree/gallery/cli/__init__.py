import typer

app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)

from . import metadata

app.add_typer(metadata.app)

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from . import check_cmd as check_cmd
from . import cluster_faces_cmd as cluster_faces_cmd
from . import export_cmd as export_cmd
from . import fix_cmd as fix_cmd
from . import fix_ios_cmd as fix_ios_cmd
from . import import_all_cmd as import_all_cmd
from . import import_cmd as import_cmd
from . import init_cmd as init_cmd
from . import list_albums_cmd as list_albums_cmd
from . import list_collections_cmd as list_collections_cmd
from . import list_media_cmd as list_media_cmd
from . import refresh_cmd as refresh_cmd
from . import rename_from_csv_cmd as rename_from_csv_cmd
from . import show_cmd as show_cmd
from . import stats_cmd as stats_cmd
