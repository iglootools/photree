"""Filesystem integration tests — full import/check/export workflow."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_fs


class _FakeFaceAnalyzer:
    """Stand-in for InsightFace ``FaceAnalysis`` — detects no faces.

    The integration_fs suite never asserts on real face data (synthetic test
    images aren't decodable by ``cv2.imread`` anyway), so loading the ~288 MB
    ``buffalo_l`` model is pure overhead. Returning an empty result from
    ``get`` matches what real detection would produce on these fixtures.
    """

    def get(self, _img: object) -> list[object]:
        return []


# Modules that import ``create_face_analyzer`` by name. Each ``from ... import
# create_face_analyzer`` binds its own module-level reference, so patching the
# source module alone would not rebind these — patch each one.
_FACE_ANALYZER_MODULES = (
    "photree.album.faces.refresh",
    "photree.album.cli.refresh_cmd",
    "photree.albums.cmd_handler.refresh",
    "photree.albums.cli.detect_faces_cmd",
    "photree.gallery.cmd_handler.importer",
)


@pytest.fixture(autouse=True)
def fake_face_analyzer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``create_face_analyzer`` with a fast no-face fake everywhere.

    Keeps the import/refresh wiring exercised end-to-end without loading or
    running the real InsightFace model.
    """
    import importlib

    for module_path in _FACE_ANALYZER_MODULES:
        module = importlib.import_module(module_path)
        monkeypatch.setattr(
            module, "create_face_analyzer", lambda *_a, **_k: _FakeFaceAnalyzer()
        )
