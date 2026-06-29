"""Filesystem integration tests — full import/check/export workflow.

Face detection is an injected capability: the import/refresh library
functions skip it unless a caller passes ``analyzer_factory`` (see
``photree.album.faces.detect.memoized_face_analyzer_factory``). These tests
drive those functions directly and inject nothing, so the ~288 MB InsightFace
model is never loaded. CLI composition-root tests stub the factory at the
command boundary where needed.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration_fs
