from pathlib import Path

import pytest

from photree.gallery.cli.check_cmd import format_face_issue
from photree.gallery.faces.check import (
    AlbumFaceDataChanged,
    AlbumFaceDataNotIndexed,
    ClusterIndexOutOfBounds,
    FaceClusterIssue,
    FaceCountMismatch,
    FaceIndexSizeMismatch,
)

_CWD = Path("/gallery")
_ALBUM = _CWD / "albums" / "2024" / "2024-06-15 - Hiking"


class TestFormatFaceIssue:
    @pytest.mark.parametrize(
        ("issue", "expected"),
        [
            (
                ClusterIndexOutOfBounds(cluster_id="c7", count=3),
                "cluster c7: 3 face index(es) out of bounds",
            ),
            (
                FaceCountMismatch(recorded=10, manifest_size=12),
                "face count mismatch: clusters.yaml says 10, manifest has 12",
            ),
            (
                FaceIndexSizeMismatch(index_rows=9, manifest_size=12),
                (
                    "face index size mismatch: face-index.faiss has 9 row(s),"
                    " manifest has 12"
                ),
            ),
            (
                AlbumFaceDataNotIndexed(album_dir=_ALBUM, media_source="main"),
                (
                    "albums/2024/2024-06-15 - Hiking (main):"
                    " face data not in gallery index"
                ),
            ),
            (
                AlbumFaceDataChanged(album_dir=_ALBUM, media_source="main"),
                (
                    "albums/2024/2024-06-15 - Hiking (main): checksum mismatch"
                    " (album face data changed)"
                ),
            ),
        ],
    )
    def test_each_issue_kind_has_its_own_wording(
        self,
        issue: FaceClusterIssue,
        expected: str,
    ) -> None:
        assert format_face_issue(issue, _CWD) == expected
