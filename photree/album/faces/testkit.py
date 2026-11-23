"""Face cache files for tests: the legacy format photree no longer reads."""

from pathlib import Path

import numpy as np

from photree.album.faces.protocol import EMBEDDING_DIM
from photree.album.faces.store import data_path


def write_legacy_face_data(
    album_dir: Path,
    media_source_name: str,
    keys: np.ndarray,
) -> Path:
    """
    Write a face data file as older photree did, with ``keys`` an object array.

    numpy pickles an object array, so reading the file back needs unpickling.
    Returns the file's path.
    """
    path = data_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = len(keys)
    np.savez_compressed(
        path,
        keys=keys.astype(object),
        face_indices=np.zeros(n, dtype=np.int32),
        det_scores=np.zeros(n, dtype=np.float32),
        bboxes=np.zeros((n, 4), dtype=np.float32),
        landmarks=np.zeros((n, 5, 2), dtype=np.float32),
        embeddings=np.zeros((n, EMBEDDING_DIM), dtype=np.float32),
    )
    return path
