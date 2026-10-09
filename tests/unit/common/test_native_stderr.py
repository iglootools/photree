"""Tests for photree.common.native_stderr."""

from __future__ import annotations

import os

import pytest

from photree.common.native_stderr import filter_native_stderr


class TestFilterNativeStderr:
    def test_drops_noise_and_keeps_other_fd_writes(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        # os.write on fd 2 stands in for a native library bypassing sys.stderr.
        with filter_native_stderr(lambda line: "noise" in line):
            os.write(2, b"noise: ignore me\nreal problem\n")

        assert capfd.readouterr().err == "real problem\n"

    def test_restores_stderr_when_block_raises(
        self, capfd: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(RuntimeError), filter_native_stderr(lambda _: False):
            os.write(2, b"before failure\n")
            raise RuntimeError

        os.write(2, b"after\n")
        assert capfd.readouterr().err == "before failure\nafter\n"
