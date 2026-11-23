"""Success paths of ``album fix`` and ``album fix-ios``: output and side effects."""

from pathlib import Path

from photree.album.id import format_album_external_id
from photree.album.store.metadata import load_album_metadata
from tests.fakes import fake_runtime, invoke_cli


def _write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"data-{path.name}", encoding="utf-8")


def _invoke(*args: str) -> tuple[int, str]:
    result = invoke_cli(["album", *args], runtime=fake_runtime())
    return result.exit_code, result.output


def _album_with_curated_photo(album: Path) -> None:
    """b.jpg is in the archive but was deleted from nelu-img/ and nelu-jpg/."""
    for name in (
        "std-nelu/orig-img/a.jpg",
        "std-nelu/orig-img/b.jpg",
        "nelu-img/a.jpg",
        "nelu-jpg/a.jpg",
    ):
        _write(album / name)


class TestAlbumFixRmUpstream:
    def test_rm_upstream_removes_the_curated_photo(self, tmp_path: Path) -> None:
        _album_with_curated_photo(tmp_path)

        code, output = _invoke("fix", "--rm-upstream", "--album-dir", str(tmp_path))

        assert code == 0
        assert output.splitlines() == [
            "Skipped nelu-vid as a deletion signal: directory is missing.",
            "Done. Removed heic: 0 jpeg, 0 main, 0 edit, 1 orig.",
        ]
        assert not (tmp_path / "std-nelu/orig-img/b.jpg").exists()
        assert (tmp_path / "std-nelu/orig-img/a.jpg").exists()

    def test_rm_upstream_dry_run_removes_nothing(self, tmp_path: Path) -> None:
        _album_with_curated_photo(tmp_path)

        code, output = _invoke(
            "fix",
            "--rm-upstream",
            "--dry-run",
            "--album-dir",
            str(tmp_path),
        )

        assert code == 0
        assert "[dry-run] Would remove heic: 0 jpeg, 0 main, 0 edit, 1 orig." in (
            output.splitlines()
        )
        assert (tmp_path / "std-nelu/orig-img/b.jpg").exists()


class TestAlbumFixRmOrphan:
    def test_rm_orphan_removes_the_edit_without_original(
        self,
        tmp_path: Path,
    ) -> None:
        for name in (
            "std-nelu/orig-img/a.jpg",
            "std-nelu/edit-img/a.jpg",
            "std-nelu/edit-img/b.jpg",
        ):
            _write(tmp_path / name)

        code, output = _invoke("fix", "--rm-orphan", "--album-dir", str(tmp_path))

        assert code == 0
        assert output.splitlines() == ["Done. Removed 1 orphan(s): 1 from edit-img."]
        assert not (tmp_path / "std-nelu/edit-img/b.jpg").exists()
        assert (tmp_path / "std-nelu/edit-img/a.jpg").exists()


class TestAlbumFixId:
    def test_id_generates_a_missing_album_id(self, tmp_path: Path) -> None:
        code, output = _invoke("fix", "--id", "--album-dir", str(tmp_path))

        metadata = load_album_metadata(tmp_path)
        assert code == 0
        assert metadata is not None
        assert output.splitlines() == [
            f"Generated album ID: {format_album_external_id(metadata.id)}",
        ]

    def test_id_keeps_an_existing_album_id(self, tmp_path: Path) -> None:
        _invoke("fix", "--id", "--album-dir", str(tmp_path))
        first = load_album_metadata(tmp_path)

        code, output = _invoke("fix", "--id", "--album-dir", str(tmp_path))

        assert code == 0
        assert first is not None
        assert load_album_metadata(tmp_path) == first
        assert output.splitlines() == [
            f"Album already has an ID: {format_album_external_id(first.id)}",
        ]

    def test_id_dry_run_writes_nothing(self, tmp_path: Path) -> None:
        code, output = _invoke("fix", "--id", "--dry-run", "--album-dir", str(tmp_path))

        assert code == 0
        assert output.splitlines() == ["[dry-run] Would generate album ID."]
        assert load_album_metadata(tmp_path) is None


class TestAlbumFixIos:
    def test_mv_miscategorized_moves_the_edit(self, tmp_path: Path) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "ios-main/orig-img/IMG_E0001.HEIC")

        code, output = _invoke(
            "fix-ios",
            "--mv-miscategorized",
            "--album-dir",
            str(tmp_path),
        )

        assert code == 0
        assert output.splitlines() == [
            "Done. Moved 1 miscategorized file(s): 1 edited file(s) from orig-img.",
        ]
        assert (tmp_path / "ios-main/edit-img/IMG_E0001.HEIC").exists()
        assert not (tmp_path / "ios-main/orig-img/IMG_E0001.HEIC").exists()

    def test_mv_miscategorized_dry_run_moves_nothing(self, tmp_path: Path) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "ios-main/orig-img/IMG_E0001.HEIC")

        code, output = _invoke(
            "fix-ios",
            "--mv-miscategorized",
            "--dry-run",
            "--album-dir",
            str(tmp_path),
        )

        assert code == 0
        assert output.splitlines() == [
            (
                "[dry-run] Would move 1 miscategorized file(s): "
                "1 edited file(s) from orig-img."
            ),
        ]
        assert (tmp_path / "ios-main/orig-img/IMG_E0001.HEIC").exists()

    def test_mv_conflict_names_the_target_and_suggests_rm_safe(
        self,
        tmp_path: Path,
    ) -> None:
        _write(tmp_path / "ios-main/orig-img/IMG_0001.HEIC")
        _write(tmp_path / "ios-main/orig-img/IMG_E0001.HEIC")
        _write(tmp_path / "ios-main/edit-img/IMG_E0001.HEIC")

        code, output = _invoke(
            "fix-ios",
            "--mv-miscategorized",
            "--album-dir",
            str(tmp_path),
        )

        assert code == 1
        assert "already in ios-main/edit-img: IMG_E0001.HEIC" in output
        assert "--rm-miscategorized-safe" in output
