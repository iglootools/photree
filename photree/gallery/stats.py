"""Gallery-level enrichment of album statistics.

Lives here rather than in the shared batch wrapper because it is the only
gallery-aware part of ``stats``: collection totals and the gallery-level face
index have no meaning for a bare batch of albums. Keeping it in ``albums/``
was what made ``albums`` depend on ``gallery``, closing a cycle with the
``gallery -> albums`` dependency that the batch commands legitimately need.
"""

from __future__ import annotations

from pathlib import Path

from ..album.stats import models as stats_models
from ..album.stats.aggregate import merge_size_stats
from ..album.stats.scan import scan_directory_size
from ..collection.stats import compute_gallery_collection_stats
from .faces.manifest import gallery_faces_dir


def enrich_gallery_stats(
    result: stats_models.GalleryStats, gallery_dir: Path
) -> stats_models.GalleryStats:
    """Add collection stats and gallery-level cache storage to *result*."""
    gallery_face_size = scan_directory_size(gallery_faces_dir(gallery_dir))
    cache_storage = merge_size_stats(
        [s for s in [result.cache_storage, gallery_face_size] if s.file_count > 0]
    )

    return stats_models.GalleryStats(
        album_count=result.album_count,
        by_album=result.by_album,
        aggregate=result.aggregate,
        unique_media_source_names=result.unique_media_source_names,
        by_year=result.by_year,
        collection_stats=compute_gallery_collection_stats(gallery_dir),
        cache_storage=cache_storage if cache_storage.file_count > 0 else None,
    )
