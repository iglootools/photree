"""Face state validation — verify face data consistency with album contents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..faces.protocol import DEFAULT_MODEL_NAME, DEFAULT_MODEL_VERSION
from ..faces.store import (
    data_path,
    load_face_data,
    load_face_state,
    state_path,
    thumbs_dir,
)
from ..store.media_sources import dedup_media_dict
from ..store.media_sources_discovery import discover_media_sources
from ..store.protocol import IMG_EXTENSIONS, IOS_IMG_EXTENSIONS
from ...common.fs import list_files


@dataclass(frozen=True)
class FaceStateCheck:
    """Result of face state validation for an album."""

    unprocessed: tuple[str, ...]
    stale_entries: tuple[str, ...]
    missing_thumbs: tuple[str, ...]
    stale_thumbs: tuple[str, ...]
    model_mismatch: bool
    npz_yaml_sync_errors: tuple[str, ...]

    @property
    def success(self) -> bool:
        return (
            len(self.unprocessed) == 0
            and len(self.stale_entries) == 0
            and len(self.missing_thumbs) == 0
            and len(self.stale_thumbs) == 0
            and not self.model_mismatch
            and len(self.npz_yaml_sync_errors) == 0
        )

    @property
    def issue_count(self) -> int:
        return (
            len(self.unprocessed)
            + len(self.stale_entries)
            + len(self.missing_thumbs)
            + len(self.stale_thumbs)
            + (1 if self.model_mismatch else 0)
            + len(self.npz_yaml_sync_errors)
        )


def check_face_state(
    album_dir: Path,
    *,
    model_name: str = DEFAULT_MODEL_NAME,
    model_version: str = DEFAULT_MODEL_VERSION,
) -> FaceStateCheck | None:
    """Validate face detection state for an album.

    Returns ``None`` if no face data exists (not an error — just means
    face detection hasn't been run yet).
    """
    media_sources = discover_media_sources(album_dir)
    if not media_sources:
        return None

    # Check if any face data exists at all
    has_any_face_data = any(
        state_path(album_dir, ms.name).is_file()
        or data_path(album_dir, ms.name).is_file()
        for ms in media_sources
    )
    if not has_any_face_data:
        return None

    all_unprocessed: list[str] = []
    all_stale_entries: list[str] = []
    all_missing_thumbs: list[str] = []
    all_stale_thumbs: list[str] = []
    all_npz_yaml_errors: list[str] = []
    any_model_mismatch = False

    for ms in media_sources:
        state = load_face_state(album_dir, ms.name)
        if state is None:
            # No state file but data exists for other sources — skip
            continue

        # Check model version
        if state.model_name != model_name or state.model_version != model_version:
            any_model_mismatch = True

        # Scan current images on disk
        img_ext = IOS_IMG_EXTENSIONS if ms.is_ios else IMG_EXTENSIONS
        current_files = dedup_media_dict(
            list_files(album_dir / ms.orig_img_dir), img_ext, ms.key_fn
        )
        current_keys = set(current_files.keys())
        processed_keys = set(state.processed_keys.keys())

        # Unprocessed images
        unprocessed = sorted(current_keys - processed_keys)
        all_unprocessed.extend(f"{ms.name}:{k}" for k in unprocessed)

        # Stale entries (in state but not on disk)
        stale = sorted(processed_keys - current_keys)
        all_stale_entries.extend(f"{ms.name}:{k}" for k in stale)

        # Thumbnail checks
        thumb_dir = thumbs_dir(album_dir, ms.name)
        for key, entry in state.processed_keys.items():
            if key not in current_keys:
                continue  # already caught as stale
            thumb = thumb_dir / f"{key}.jpg"
            if not thumb.is_file():
                all_missing_thumbs.append(f"{ms.name}:{key}")
            else:
                orig = album_dir / ms.orig_img_dir / entry.file_name
                if orig.is_file() and orig.stat().st_mtime != entry.mtime:
                    all_stale_thumbs.append(f"{ms.name}:{key}")

        # .npz / .yaml sync check
        face_data = load_face_data(album_dir, ms.name)
        if face_data is not None:
            npz_keys = set(face_data.keys)
            state_keys_with_faces = {
                k for k, v in state.processed_keys.items() if v.face_count > 0
            }
            if npz_keys != state_keys_with_faces:
                all_npz_yaml_errors.append(
                    f"{ms.name}: .npz keys don't match .yaml processed-keys"
                )

            # Array length consistency
            if not (
                len(face_data.keys)
                == len(face_data.face_indices)
                == len(face_data.det_scores)
                == face_data.bboxes.shape[0]
                == face_data.landmarks.shape[0]
                == face_data.embeddings.shape[0]
            ):
                all_npz_yaml_errors.append(
                    f"{ms.name}: .npz array lengths inconsistent"
                )

    return FaceStateCheck(
        unprocessed=tuple(all_unprocessed),
        stale_entries=tuple(all_stale_entries),
        missing_thumbs=tuple(all_missing_thumbs),
        stale_thumbs=tuple(all_stale_thumbs),
        model_mismatch=any_model_mismatch,
        npz_yaml_sync_errors=tuple(all_npz_yaml_errors),
    )
