"""Tests for photree.album.faces.detect — analyzer factory injection."""

from __future__ import annotations

import pytest

from photree.album.faces import detect


class TestMemoizedFaceAnalyzerFactory:
    def test_loads_lazily_and_caches(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The factory builds the analyzer on first call and reuses it after."""
        calls = 0
        sentinel = object()

        def _fake_create(model_name: str = "buffalo_l") -> object:
            nonlocal calls
            calls += 1
            return sentinel

        monkeypatch.setattr(detect, "create_face_analyzer", _fake_create)

        factory = detect.memoized_face_analyzer_factory()
        # Not built until first invocation.
        assert calls == 0

        first = factory()
        second = factory()

        assert first is sentinel
        assert second is sentinel
        assert calls == 1  # loaded once, shared across calls


class TestSelectProviders:
    def test_keeps_preferred_order_when_all_available(self) -> None:
        available = [
            "CoreMLExecutionProvider",
            "AzureExecutionProvider",
            "CPUExecutionProvider",
        ]
        assert detect.select_providers(available) == [
            "CoreMLExecutionProvider",
            "CPUExecutionProvider",
        ]

    def test_drops_coreml_when_unavailable(self) -> None:
        """On Linux, requesting CoreML makes onnxruntime warn once per model."""
        available = ["AzureExecutionProvider", "CPUExecutionProvider"]
        assert detect.select_providers(available) == ["CPUExecutionProvider"]
