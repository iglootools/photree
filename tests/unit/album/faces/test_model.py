import hashlib
import io
import socket
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from photree.album.faces.detect import memoized_face_analyzer_factory
from photree.album.faces.model import (
    BUFFALO_L,
    VERIFIED_MARKER,
    ModelArchive,
    ModelChecksumError,
    ModelDownloadError,
    ModelDownloadFailureKind,
    UnknownModelError,
    download_url,
    ensure_model,
    resolve_model_archive,
)
from photree.cli import main


def _zip_bytes(**files: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, content in files.items():
            zf.writestr(f"{name}.onnx", content)
    return buffer.getvalue()


_ARCHIVE_BYTES = _zip_bytes(det_10g=b"detector")
_ARCHIVE = ModelArchive(
    name="buffalo_l",
    url="https://example.invalid/buffalo_l.zip",
    sha256=hashlib.sha256(_ARCHIVE_BYTES).hexdigest(),
)


class _FakeDownload:
    """Serves *content* for any URL and counts the downloads."""

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.urls: list[str] = []

    def __call__(self, url: str, dst: Path) -> None:
        self.urls.append(url)
        dst.write_bytes(self.content)


class TestEnsureModel:
    def test_downloads_verifies_and_extracts(self, tmp_path: Path) -> None:
        download = _FakeDownload(_ARCHIVE_BYTES)

        model_dir = ensure_model(tmp_path, _ARCHIVE, download=download)

        assert download.urls == [_ARCHIVE.url]
        assert model_dir == tmp_path / "models" / "buffalo_l"
        assert (model_dir / "det_10g.onnx").read_bytes() == b"detector"
        assert (model_dir / VERIFIED_MARKER).read_text().strip() == _ARCHIVE.sha256

    def test_verified_model_is_not_downloaded_again(self, tmp_path: Path) -> None:
        ensure_model(tmp_path, _ARCHIVE, download=_FakeDownload(_ARCHIVE_BYTES))
        download = _FakeDownload(_ARCHIVE_BYTES)

        ensure_model(tmp_path, _ARCHIVE, download=download)

        assert download.urls == []

    def test_mismatched_archive_raises_and_installs_nothing(
        self,
        tmp_path: Path,
    ) -> None:
        tampered = _zip_bytes(det_10g=b"something else")

        with pytest.raises(ModelChecksumError) as exc_info:
            ensure_model(tmp_path, _ARCHIVE, download=_FakeDownload(tampered))

        assert exc_info.value.url == _ARCHIVE.url
        assert exc_info.value.expected == _ARCHIVE.sha256
        assert exc_info.value.actual == hashlib.sha256(tampered).hexdigest()
        assert list((tmp_path / "models").iterdir()) == []

    def test_matching_archive_left_by_insightface_is_reused(
        self,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "models").mkdir()
        (tmp_path / "models" / "buffalo_l.zip").write_bytes(_ARCHIVE_BYTES)
        download = _FakeDownload(_ARCHIVE_BYTES)

        model_dir = ensure_model(tmp_path, _ARCHIVE, download=download)

        assert download.urls == []
        assert (model_dir / "det_10g.onnx").is_file()

    def test_unverified_model_dir_is_replaced(self, tmp_path: Path) -> None:
        """A directory insightface extracted unchecked is re-extracted."""
        model_dir = tmp_path / "models" / "buffalo_l"
        model_dir.mkdir(parents=True)
        (model_dir / "planted.onnx").write_bytes(b"planted")
        (tmp_path / "models" / "buffalo_l.zip").write_bytes(b"not the archive")

        ensure_model(tmp_path, _ARCHIVE, download=_FakeDownload(_ARCHIVE_BYTES))

        assert sorted(p.name for p in model_dir.iterdir()) == [
            VERIFIED_MARKER,
            "det_10g.onnx",
        ]


class TestResolveModelArchive:
    def test_default_model_is_pinned(self) -> None:
        assert resolve_model_archive("buffalo_l") == BUFFALO_L
        assert len(BUFFALO_L.sha256) == 64

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(UnknownModelError):
            resolve_model_archive("antelopev2")


class TestMemoizedFactoryOnChecksumError:
    def test_failed_checksum_is_not_retried(self) -> None:
        calls: list[str] = []
        error = ModelChecksumError(url="u", expected="e", actual="a")

        def _create(model_name: str) -> Any:  # noqa: ANN401 - stands in for insightface's untyped FaceAnalysis
            calls.append(model_name)
            raise error

        factory = memoized_face_analyzer_factory(create=_create)

        for _ in range(2):
            with pytest.raises(ModelChecksumError):
                factory()

        assert calls == ["buffalo_l"]


def test_entry_point_reports_checksum_mismatch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(**_: object) -> None:
        raise ModelChecksumError(
            url="https://example.invalid/buffalo_l.zip",
            expected="aaa",
            actual="bbb",
        )

    with pytest.raises(SystemExit) as exc_info:
        main(run=_raise)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "https://example.invalid/buffalo_l.zip" in err
    assert "expected: aaa" in err
    assert "actual:   bbb" in err


@pytest.fixture
def silent_server() -> Iterator[str]:
    """Yield the URL of a server that accepts connections and never answers."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()
        host, port = server.getsockname()
        yield f"http://{host}:{port}/buffalo_l.zip"


@pytest.fixture
def closed_port_url() -> str:
    """Return a URL on a local port nothing listens on."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        host, port = probe.getsockname()
    return f"http://{host}:{port}/buffalo_l.zip"


class TestDownloadUrl:
    def test_stalled_server_times_out(self, silent_server: str, tmp_path: Path) -> None:
        with pytest.raises(ModelDownloadError) as exc_info:
            download_url(silent_server, tmp_path / "a.zip", timeout_seconds=0.2)

        assert exc_info.value.kind == ModelDownloadFailureKind.TIMED_OUT
        assert exc_info.value.url == silent_server

    def test_refused_connection_is_unreachable(
        self,
        closed_port_url: str,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ModelDownloadError) as exc_info:
            download_url(closed_port_url, tmp_path / "a.zip", timeout_seconds=5)

        assert exc_info.value.kind == ModelDownloadFailureKind.UNREACHABLE


class TestMemoizedFactoryOnDownloadError:
    def test_failed_download_is_not_retried(self) -> None:
        calls: list[str] = []
        error = ModelDownloadError(
            url="u",
            kind=ModelDownloadFailureKind.TIMED_OUT,
            detail="timed out",
        )

        def _create(model_name: str) -> Any:  # noqa: ANN401 - stands in for insightface's untyped FaceAnalysis
            calls.append(model_name)
            raise error

        factory = memoized_face_analyzer_factory(create=_create)

        for _ in range(2):
            with pytest.raises(ModelDownloadError):
                factory()

        assert calls == ["buffalo_l"]


def test_entry_point_reports_download_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _raise(**_: object) -> None:
        raise ModelDownloadError(
            url="https://example.invalid/buffalo_l.zip",
            kind=ModelDownloadFailureKind.TIMED_OUT,
            detail="timed out",
        )

    with pytest.raises(SystemExit) as exc_info:
        main(run=_raise)

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "timed out" in err
    assert "https://example.invalid/buffalo_l.zip" in err
    assert "run the command again" in err
