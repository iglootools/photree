"""The ``photree albums`` command group, with every command registered."""

# Imported for their side effect: each module registers its commands on `app`.
# The redundant `x as x` alias tells ruff and pyright the import is intentional.
from photree.albums.cli import (
    check_cmd as check_cmd,
    detect_faces_cmd as detect_faces_cmd,
    export_cmd as export_cmd,
    fix_cmd as fix_cmd,
    fix_ios_cmd as fix_ios_cmd,
    import_check_cmd as import_check_cmd,
    import_cmd as import_cmd,
    init_cmd as init_cmd,
    list_cmd as list_cmd,
    list_media_cmd as list_media_cmd,
    refresh_cmd as refresh_cmd,
    rename_from_csv_cmd as rename_from_csv_cmd,
    stats_cmd as stats_cmd,
)
from photree.albums.cli.app import app

__all__ = ["app"]
