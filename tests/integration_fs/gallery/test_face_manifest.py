from pathlib import Path

import numpy as np
import pytest

from photree.gallery.faces.clustering import build_faiss_index, load_faiss_index
from photree.gallery.faces.manifest import (
    GalleryFaceState,
    clusters_path,
    faiss_index_path,
    gallery_faces_dir,
    load_manifest,
    save_face_state,
)
from photree.gallery.faces.protocol import (
    AlbumFaceChecksums,
    FaceClusteringResult,
    FaceManifest,
    FaceReference,
)


def _state(face_count: int) -> GalleryFaceState:
    embeddings = np.eye(face_count, 512, dtype=np.float32)
    return GalleryFaceState(
        index=build_faiss_index(embeddings),
        manifest=FaceManifest(
            faces=[
                FaceReference(
                    album_id="album",
                    media_source="main",
                    media_key=f"{i:04d}",
                    face_index=0,
                )
                for i in range(face_count)
            ],
        ),
        clusters=FaceClusteringResult(threshold=0.45, face_count=face_count),
        checksums=AlbumFaceChecksums(albums={"album": {"main": "checksum"}}),
    )


class TestSaveFaceState:
    def test_save_leaves_only_the_four_files(self, tmp_path: Path) -> None:
        save_face_state(tmp_path, _state(2))

        assert sorted(p.name for p in gallery_faces_dir(tmp_path).iterdir()) == [
            "album-checksums.yaml",
            "clusters.yaml",
            "face-index.faiss",
            "face-manifest.yaml",
        ]

    def test_save_failing_while_writing_keeps_the_previous_files(
        self,
        tmp_path: Path,
    ) -> None:
        save_face_state(tmp_path, _state(1))
        # A directory where the clusters are staged makes that write fail, after
        # the index and manifest are written.
        clusters_staging = clusters_path(tmp_path).with_name("clusters.yaml.tmp")
        clusters_staging.mkdir()

        with pytest.raises(IsADirectoryError):
            save_face_state(tmp_path, _state(2))

        index = load_faiss_index(faiss_index_path(tmp_path))
        manifest = load_manifest(tmp_path)
        assert index is not None
        assert manifest is not None
        assert (index.ntotal, len(manifest.faces)) == (1, 1)
