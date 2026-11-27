from pathlib import Path

from photree.album.id import generate_album_id
from photree.album.store.metadata import load_album_metadata, save_album_metadata
from photree.album.store.protocol import ALBUM_YAML, AlbumMetadata
from photree.foundation.layout import PHOTREE_DIR
from tests.fakes import invoke_cli
from tests.testkit import add_ios_media_source, mark_album


class TestAlbumInit:
    def test_creates_album_yaml(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        result = invoke_cli(["album", "init", "-a", str(album)])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert "Album ID:" in result.output
        assert load_album_metadata(album) is not None

    def test_generates_valid_id(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        invoke_cli(["album", "init", "-a", str(album)])
        metadata = load_album_metadata(album)
        assert metadata is not None
        assert metadata.id

    def test_fails_if_already_initialized(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        mark_album(album)
        result = invoke_cli(["album", "init", "-a", str(album)])
        assert result.exit_code == 1
        assert "already initialized" in result.output

    def test_does_not_overwrite_existing_id(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        original_id = generate_album_id()
        save_album_metadata(album, AlbumMetadata(id=original_id))
        invoke_cli(["album", "init", "-a", str(album)])
        metadata = load_album_metadata(album)
        assert metadata is not None
        assert metadata.id == original_id

    def test_creates_photree_dir(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()
        invoke_cli(["album", "init", "-a", str(album)])
        assert (album / PHOTREE_DIR / ALBUM_YAML).is_file()

    def test_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Hiking"
        album.mkdir()

        result = invoke_cli(["album", "init", "-a", str(album), "--dry-run"])

        assert result.exit_code == 0
        assert result.output.startswith("[dry-run] Would create ")
        assert not (album / PHOTREE_DIR).exists()


class TestAlbumsInit:
    def test_initializes_multiple_albums(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        add_ios_media_source(a1)
        add_ios_media_source(a2)

        result = invoke_cli(["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None
        assert load_album_metadata(a2) is not None

    def test_already_initialized_album_is_skipped_not_failed(
        self,
        tmp_path: Path,
    ) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        add_ios_media_source(a1)
        add_ios_media_source(a2)
        mark_album(a1)

        result = invoke_cli(["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "2024-07-14 - Trip A (already initialized: album_" in result.output
        assert (
            "1 album(s) initialized, 1 already initialized (skipped), 0 failed."
        ) in result.output
        assert load_album_metadata(a2) is not None

    def test_does_not_overwrite_existing_ids(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        add_ios_media_source(a1)
        original_id = generate_album_id()
        save_album_metadata(a1, AlbumMetadata(id=original_id))

        invoke_cli(["albums", "init", "-d", str(tmp_path)])
        metadata = load_album_metadata(a1)
        assert metadata is not None
        assert metadata.id == original_id

    def test_dry_run_does_not_create_files(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        add_ios_media_source(a1)

        result = invoke_cli(["albums", "init", "-d", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is None

    def test_dry_run_labels_batch_summary(self, tmp_path: Path) -> None:
        add_ios_media_source(tmp_path / "2024-07-14 - Trip A")

        result = invoke_cli(["albums", "init", "-d", str(tmp_path), "--dry-run"])

        assert result.exit_code == 0
        assert "[dry-run] 1 album(s) would be initialized, 0 failed." in result.output

    def test_explicit_album_dirs(self, tmp_path: Path) -> None:
        a1 = tmp_path / "2024-07-14 - Trip A"
        a2 = tmp_path / "2024-07-15 - Trip B"
        a1.mkdir()
        a2.mkdir()

        result = invoke_cli(["albums", "init", "-a", str(a1), "-a", str(a2)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None
        assert load_album_metadata(a2) is not None

    def test_discovers_albums_without_album_yaml(self, tmp_path: Path) -> None:
        """--dir finds directories with media sources even without album.yaml."""
        a1 = tmp_path / "2024-07-14 - Trip A"
        add_ios_media_source(a1)
        # No _mark_album — album.yaml does not exist yet

        result = invoke_cli(["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert load_album_metadata(a1) is not None

    def test_no_albums_found(self, tmp_path: Path) -> None:
        result = invoke_cli(["albums", "init", "-d", str(tmp_path)])
        assert result.exit_code == 0
        assert "No albums found" in result.output

    def test_dir_and_album_dir_mutually_exclusive(self, tmp_path: Path) -> None:
        a1 = tmp_path / "album"
        a1.mkdir()
        result = invoke_cli(["albums", "init", "-d", str(tmp_path), "-a", str(a1)])
        assert result.exit_code == 2
        assert "mutually exclusive" in result.output


class TestAlbumFixId:
    def test_dry_run_labels_the_action_line(self, tmp_path: Path) -> None:
        album = tmp_path / "2024-07-14 - Trip A"
        add_ios_media_source(album)

        result = invoke_cli(
            ["album", "fix", "--id", "--dry-run", "--album-dir", str(album)],
        )

        assert result.exit_code == 0
        assert result.output == "[dry-run] Would generate album ID.\n"
        assert load_album_metadata(album) is None
