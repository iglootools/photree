"""``album detect-faces`` and ``albums detect-faces``, with fake face detection."""

from pathlib import Path

from photree.album.faces.store import load_face_data
from photree.album.id import generate_album_id
from photree.album.store.metadata import save_album_metadata
from photree.album.store.protocol import AlbumMetadata
from photree.albums.cmd_handler.detect_faces import batch_detect_faces
from tests.fakes import (
    FakeFaceDetector,
    fake_face_runtime,
    fake_make_thumbnail,
    invoke_cli,
)
from tests.testkit import write_file


def _album(base: Path, name: str, *images: str) -> Path:
    album = base / name
    (album / ".photree").mkdir(parents=True)
    for image in images:
        write_file(album / "ios-main" / "orig-img" / image)
    save_album_metadata(album, AlbumMetadata(id=generate_album_id()))
    return album


class TestAlbumDetectFaces:
    def test_detects_and_saves_faces(self, tmp_path: Path) -> None:
        album = _album(tmp_path, "2024-07-14 - Hiking", "IMG_0001.HEIC")

        result = invoke_cli(
            ["album", "detect-faces", "-a", str(album)],
            runtime=fake_face_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "main: 1 processed, 0 skipped, 1 face(s)" in result.output
        data = load_face_data(album, "main")
        assert data is not None
        assert list(data.keys) == ["0001"]

    def test_dry_run_saves_nothing(self, tmp_path: Path) -> None:
        album = _album(tmp_path, "2024-07-14 - Hiking", "IMG_0001.HEIC")

        result = invoke_cli(
            ["album", "detect-faces", "-a", str(album), "--dry-run"],
            runtime=fake_face_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert "main: 1 would be processed, 0 skipped" in result.output
        assert load_face_data(album, "main") is None

    def test_failed_image_is_listed_and_exits_one(self, tmp_path: Path) -> None:
        album = _album(
            tmp_path,
            "2024-07-14 - Hiking",
            "IMG_0001.HEIC",
            "IMG_0002.HEIC",
        )

        result = invoke_cli(
            ["album", "detect-faces", "-a", str(album)],
            runtime=fake_face_runtime(broken=frozenset({"0002"})),
        )

        assert result.exit_code == 1
        assert "main: 1 processed, 0 skipped, 1 face(s), 1 failed" in result.output
        assert "main/0002 (detection): cannot read image 0002.jpg" in result.output


class TestAlbumsDetectFaces:
    def test_album_with_a_failed_image_fails(self, tmp_path: Path) -> None:
        _album(tmp_path, "2024-07-14 - Hiking", "IMG_0001.HEIC")
        _album(tmp_path, "2024-08-01 - Beach", "IMG_0002.HEIC")

        result = invoke_cli(
            ["albums", "detect-faces", "-d", str(tmp_path)],
            runtime=fake_face_runtime(broken=frozenset({"0002"})),
        )

        assert result.exit_code == 1
        assert "1 album(s) processed, 1 failed." in result.output
        assert "2024-08-01 - Beach" in result.output
        assert "main/0002 (detection)" in result.output
        assert load_face_data(tmp_path / "2024-07-14 - Hiking", "main") is not None


class TestBatchDetectFaces:
    def test_failed_image_fails_its_album_with_the_reason(
        self,
        tmp_path: Path,
    ) -> None:
        good = _album(tmp_path, "2024-07-14 - Hiking", "IMG_0001.HEIC")
        bad = _album(tmp_path, "2024-08-01 - Beach", "IMG_0002.HEIC", "IMG_0003.HEIC")

        result = batch_detect_faces(
            [good, bad],
            analyzer_factory=FakeFaceDetector,
            make_thumbnail=fake_make_thumbnail(broken=frozenset({"0002"})),
        )

        assert result.succeeded == 1
        ((failure),) = result.failures
        assert failure.album_dir == bad
        assert failure.reason == "main/0002 (detection): cannot read image 0002.jpg"

    def test_model_is_shared_and_loaded_only_when_needed(
        self,
        tmp_path: Path,
    ) -> None:
        albums = [
            _album(tmp_path, "2024-07-01 - Empty"),
            _album(tmp_path, "2024-07-14 - Hiking", "IMG_0001.HEIC"),
            _album(tmp_path, "2024-08-01 - Beach", "IMG_0002.HEIC"),
        ]
        detector = FakeFaceDetector()
        calls: list[None] = []

        def factory() -> FakeFaceDetector:
            calls.append(None)
            return detector

        result = batch_detect_faces(
            albums,
            analyzer_factory=factory,
            make_thumbnail=fake_make_thumbnail(),
        )

        assert (result.succeeded, result.failures) == (3, ())
        assert len(calls) == 2, "invoked per album with images; memoizing is its job"
