"""Filesystem integration tests — full import/check/export workflow.

Face detection is an injected capability: the import/refresh library
functions skip it unless a caller passes ``analyzer_factory`` (see
``photree.album.faces.detect.memoized_face_analyzer_factory``). These tests
drive those functions directly and inject nothing, so the ~288 MB InsightFace
model is never loaded.

CLI tests satisfy the system-dependency gate with a fake runtime
(``tests.fakes.ALL_DEPS_RUNTIME``) rather than skipping where ``sips`` is
missing (it only exists on macOS, while CI runs on Linux). A command that then
reaches a conversion fails on the test's fake media either way: real ``sips``
cannot read it, and a missing one raises ``FileNotFoundError``.
"""

import pytest

pytestmark = pytest.mark.integration_fs
