"""The ``photree gallery`` command group, with every command registered on it."""

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.gallery.cli import (
    check_cmd as check_cmd,
    cluster_faces_cmd as cluster_faces_cmd,
    export_cmd as export_cmd,
    fix_cmd as fix_cmd,
    fix_ios_cmd as fix_ios_cmd,
    import_all_cmd as import_all_cmd,
    import_cmd as import_cmd,
    init_cmd as init_cmd,
    list_albums_cmd as list_albums_cmd,
    list_collections_cmd as list_collections_cmd,
    list_media_cmd as list_media_cmd,
    refresh_cmd as refresh_cmd,
    rename_from_csv_cmd as rename_from_csv_cmd,
    show_cmd as show_cmd,
    stats_cmd as stats_cmd,
)
from photree.gallery.cli.app import app

__all__ = ["app"]
