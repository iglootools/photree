"""Reading and writing an album's face cache under ``.photree/cache/faces/``."""

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING

from photree.album.faces.protocol import (
    EMBEDDING_DIM,
    FACES_DATA_SUFFIX,
    FACES_DIR,
    FACES_STATE_SUFFIX,
    THUMBS_DIR_SUFFIX,
    FaceProcessingState,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.metadata_io import (
    InvalidMetadataError,
    load_yaml_mapping,
    validate_metadata,
    write_yaml,
)

if TYPE_CHECKING:
    # Annotations only: numpy is imported in the functions that use it, since
    # `album check` reaches this module at CLI startup.
    import numpy as np


def faces_dir(album_dir: Path) -> Path:
    """Return the album's face cache directory."""
    return album_dir / PHOTREE_DIR / FACES_DIR


def state_path(album_dir: Path, media_source_name: str) -> Path:
    """Return the path of a media source's face processing state YAML."""
    return faces_dir(album_dir) / f"{media_source_name}{FACES_STATE_SUFFIX}"


def data_path(album_dir: Path, media_source_name: str) -> Path:
    """Return the path of a media source's face data ``.npz`` file."""
    return faces_dir(album_dir) / f"{media_source_name}{FACES_DATA_SUFFIX}"


def thumbs_dir(album_dir: Path, media_source_name: str) -> Path:
    """Return the directory holding a media source's face thumbnails."""
    return faces_dir(album_dir) / f"{media_source_name}{THUMBS_DIR_SUFFIX}"


@dataclass(frozen=True)
class FaceData:
    """All arrays have length ``N`` (total detected faces across all images)."""

    keys: np.ndarray  # (N,) fixed-width unicode — media key per face
    face_indices: np.ndarray  # (N,) int32 — 0-based face index within image
    det_scores: np.ndarray  # (N,) float32 — detection confidence
    bboxes: np.ndarray  # (N, 4) float32 — bounding boxes [x1, y1, x2, y2]
    landmarks: np.ndarray  # (N, 5, 2) float32 — 5-point landmarks
    embeddings: np.ndarray  # (N, 512) float32 — ArcFace embeddings

    @property
    def count(self) -> int:
        """Return the number of faces held."""
        return len(self.keys)

    @staticmethod
    def empty() -> FaceData:
        """Return face data holding no faces."""
        import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

        return FaceData(
            keys=np.array([], dtype=np.str_),
            face_indices=np.array([], dtype=np.int32),
            det_scores=np.array([], dtype=np.float32),
            bboxes=np.empty((0, 4), dtype=np.float32),
            landmarks=np.empty((0, 5, 2), dtype=np.float32),
            embeddings=np.empty((0, EMBEDDING_DIM), dtype=np.float32),
        )


class LegacyFaceDataError(InvalidMetadataError):
    """
    A face data file written before ``keys`` was stored as strings.

    Older photree saved ``keys`` as an object array, which numpy reads back
    only by unpickling it, and unpickling runs whatever code a crafted file
    holds. Such a file is never read: the refresh detects the faces again.
    """

    def __init__(self, path: Path) -> None:
        """Build the error from the path of the outdated face data file."""
        super().__init__(
            path,
            "written by an older photree in a format it no longer reads",
            derived=True,
        )


def _face_data_error(path: Path, reason: str) -> InvalidMetadataError:
    return InvalidMetadataError(path, reason, derived=True)


def read_face_count(path: Path) -> int:
    """
    Return the number of faces in the face data file at *path*.

    Reads only the header of its ``keys`` array, so it neither decompresses
    the embeddings nor unpickles anything, and counts a legacy file too.
    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError`,
    marked ``derived``, when the file cannot be read.
    """
    shape, _ = _read_keys_header(path)
    return shape[0] if shape else 0


def _read_npy_header(f: IO[bytes]) -> tuple[tuple[int, ...], np.dtype[np.generic]]:
    import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

    version = np.lib.format.read_magic(f)
    read_header = {
        (1, 0): np.lib.format.read_array_header_1_0,
        (2, 0): np.lib.format.read_array_header_2_0,
    }.get(version)
    if read_header is None:
        message = f"unsupported .npy version {version}"
        raise ValueError(message)
    shape, _, dtype = read_header(f)
    return shape, dtype


def _read_keys_header(path: Path) -> tuple[tuple[int, ...], np.dtype[np.generic]]:
    """Return the shape and dtype of the ``keys`` array, without loading it."""
    try:
        with zipfile.ZipFile(path) as archive, archive.open("keys.npy") as f:
            return _read_npy_header(f)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, EOFError) as exc:
        raise _face_data_error(path, f"not a readable face data file ({exc})") from exc


def has_legacy_face_data(album_dir: Path, media_source_name: str) -> bool:
    """
    Return whether the media source's face data file is in the legacy format.

    ``False`` when the file is absent. Reads only the header of ``keys``; raises
    :class:`~photree.foundation.metadata_io.InvalidMetadataError`, marked
    ``derived``, when the file cannot be read.
    """
    path = data_path(album_dir, media_source_name)
    return path.is_file() and _read_keys_header(path)[1].hasobject


def load_face_data(album_dir: Path, media_source_name: str) -> FaceData | None:
    """
    Load ``.photree/cache/faces/{name}.npz``, or return ``None`` if missing.

    Never unpickles. Raises :class:`LegacyFaceDataError` for a file in the
    legacy format, and
    :class:`~photree.foundation.metadata_io.InvalidMetadataError`, marked
    ``derived``, for one that cannot be read: ``--redetect-faces`` or deleting
    the file rebuilds either.
    """
    path = data_path(album_dir, media_source_name)
    if not path.is_file():
        return None
    if has_legacy_face_data(album_dir, media_source_name):
        raise LegacyFaceDataError(path)
    import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

    try:
        with np.load(path, allow_pickle=False) as npz:
            return FaceData(
                keys=npz["keys"],
                face_indices=npz["face_indices"],
                det_scores=npz["det_scores"],
                bboxes=npz["bboxes"],
                landmarks=npz["landmarks"],
                embeddings=npz["embeddings"],
            )
    except (zipfile.BadZipFile, KeyError, ValueError, OSError, EOFError) as exc:
        raise _face_data_error(path, f"not a readable face data file ({exc})") from exc


def save_face_data(album_dir: Path, media_source_name: str, data: FaceData) -> None:
    """
    Write *data* to the media source's ``.npz`` file, replacing it.

    Creates the face cache directory when missing. ``keys`` is written as
    fixed-width unicode whatever its dtype in *data*, so reading it back never
    needs unpickling.
    """
    import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

    path = data_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        keys=data.keys.astype(np.str_),
        face_indices=data.face_indices,
        det_scores=data.det_scores,
        bboxes=data.bboxes,
        landmarks=data.landmarks,
        embeddings=data.embeddings,
    )


def load_face_state(
    album_dir: Path,
    media_source_name: str,
) -> FaceProcessingState | None:
    """
    Load the face state, or return ``None`` when it is absent.

    Raises :class:`~photree.foundation.metadata_io.InvalidMetadataError`,
    marked ``derived``, when present but corrupt (``--redetect-faces`` or
    deleting the file rebuilds it).
    """
    path = state_path(album_dir, media_source_name)
    try:
        raw = load_yaml_mapping(path)
        return (
            validate_metadata(path, FaceProcessingState, raw)
            if raw is not None
            else None
        )
    except InvalidMetadataError as exc:
        raise InvalidMetadataError(exc.path, exc.reason, derived=True) from exc


def save_face_state(
    album_dir: Path,
    media_source_name: str,
    state: FaceProcessingState,
) -> None:
    """
    Write *state* to the media source's state YAML, replacing it.

    Creates the face cache directory when missing.
    """
    path = state_path(album_dir, media_source_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml(path, state.model_dump(by_alias=True, mode="json"))


def filter_face_data(data: FaceData, *, keep_keys: set[str]) -> FaceData:
    """Return *data* restricted to the faces of the images in *keep_keys*."""
    import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

    if data.count == 0:
        return data
    mask = np.isin(data.keys, list(keep_keys))
    return FaceData(
        keys=data.keys[mask],
        face_indices=data.face_indices[mask],
        det_scores=data.det_scores[mask],
        bboxes=data.bboxes[mask],
        landmarks=data.landmarks[mask],
        embeddings=data.embeddings[mask],
    )


def merge_face_data(existing: FaceData, new: FaceData) -> FaceData:
    """Return the faces of *existing* followed by those of *new*."""
    import numpy as np  # noqa: PLC0415 - numpy, kept out of CLI startup

    if existing.count == 0:
        return new
    if new.count == 0:
        return existing
    return FaceData(
        keys=np.concatenate([existing.keys, new.keys]),
        face_indices=np.concatenate([existing.face_indices, new.face_indices]),
        det_scores=np.concatenate([existing.det_scores, new.det_scores]),
        bboxes=np.concatenate([existing.bboxes, new.bboxes]),
        landmarks=np.concatenate([existing.landmarks, new.landmarks]),
        embeddings=np.concatenate([existing.embeddings, new.embeddings]),
    )
