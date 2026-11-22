import typer

app = typer.Typer(
    name="gallery",
    help="Batch operations on multiple albums.",
    no_args_is_help=True,
)

from photree.gallery.cli import metadata

app.add_typer(metadata.app)

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.gallery.cli import check_cmd as check_cmd
from photree.gallery.cli import cluster_faces_cmd as cluster_faces_cmd
from photree.gallery.cli import export_cmd as export_cmd
from photree.gallery.cli import fix_cmd as fix_cmd
from photree.gallery.cli import fix_ios_cmd as fix_ios_cmd
from photree.gallery.cli import import_all_cmd as import_all_cmd
from photree.gallery.cli import import_cmd as import_cmd
from photree.gallery.cli import init_cmd as init_cmd
from photree.gallery.cli import list_albums_cmd as list_albums_cmd
from photree.gallery.cli import list_collections_cmd as list_collections_cmd
from photree.gallery.cli import list_media_cmd as list_media_cmd
from photree.gallery.cli import refresh_cmd as refresh_cmd
from photree.gallery.cli import rename_from_csv_cmd as rename_from_csv_cmd
from photree.gallery.cli import show_cmd as show_cmd
from photree.gallery.cli import stats_cmd as stats_cmd
