"""Rich rendering of ``gallery stats``: the albums report plus the collection table."""

from rich.console import Group
from rich.text import Text

from photree.album.cli.stats_output import LEGEND, albums_stats_renderables
from photree.collection.cli.stats_output import format_collections_overview
from photree.gallery.stats import GalleryStats


def format_gallery_stats(stats: GalleryStats) -> Group:
    """Format gallery statistics: the albums report plus the collection table."""
    collections = stats.collection_stats
    return Group(
        *albums_stats_renderables(stats.albums, cache_storage=stats.cache_storage),
        *(
            [Text(""), format_collections_overview(collections)]
            if collections is not None and collections.total > 0
            else []
        ),
        Text(""),
        LEGEND,
    )
