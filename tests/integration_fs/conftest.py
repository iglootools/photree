"""Filesystem integration tests — full import/check/export workflow.

Face detection is an injected capability: the import/refresh library
functions skip it unless a caller passes ``analyzer_factory`` (see
``photree.album.faces.detect.memoized_face_analyzer_factory``). These tests
drive those functions directly and inject nothing, so the ~288 MB InsightFace
model is never loaded. CLI composition-root tests stub the factory at the
command boundary where needed.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration_fs


@pytest.fixture
def stub_sips_on_path(tmp_path_factory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a deliberately-failing ``sips`` stub at the front of PATH.

    Import/refresh CLI commands gate on ``sips`` before doing any work, but
    ``sips`` only exists on macOS while CI runs on Linux. Tests that exercise
    control flow which never reaches a real conversion satisfy the gate with a
    stub rather than skipping on non-macOS, so the paths stay covered on both.

    The stub exits non-zero: a test that unexpectedly does reach conversion
    fails loudly instead of silently producing a corrupt JPEG.
    """
    return _stub_binary_on_path("sips", tmp_path_factory, monkeypatch)


def _stub_binary_on_path(
    name: str,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    bin_dir = tmp_path_factory.mktemp(f"stub-{name}-bin")
    stub = bin_dir / name
    stub.write_text(
        f'#!/bin/sh\necho "stub {name}: not expected to be invoked" >&2\nexit 1\n'
    )
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return stub
