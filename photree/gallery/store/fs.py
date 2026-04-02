"""Gallery persistence — backward-compatible re-export.

Note: During the facade migration phase, gallery functions are defined
in fs/repo.py and re-exported here. Once callers migrate to
gallery.store.fs directly (Phase F), the definitions will move here.
"""

from __future__ import annotations

from ...fs.repo import (  # noqa: F401
    load_gallery_metadata,
    resolve_gallery_dir,
    resolve_gallery_metadata,
    resolve_link_mode,
    save_gallery_metadata,
)
