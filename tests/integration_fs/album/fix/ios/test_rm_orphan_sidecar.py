from pathlib import Path

from photree.album.fix.ios import (
    rm_orphan_sidecar,
)
from photree.album.store.media_source import MAIN_MEDIA_SOURCE
from tests.testkit import write_files

MC = MAIN_MEDIA_SOURCE


class TestRmOrphanSidecar:
    def test_removes_orphan_aae_in_orig(self, tmp_path: Path) -> None:
        write_files(
            tmp_path / "ios-main/orig-img",
            ["IMG_0001.HEIC", "IMG_0001.AAE", "IMG_9999.AAE"],
        )
        write_files(tmp_path / "ios-main/edit-img", [])

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 1
        assert not (tmp_path / "ios-main/orig-img" / "IMG_9999.AAE").exists()
        assert (tmp_path / "ios-main/orig-img" / "IMG_0001.AAE").exists()

    def test_removes_orphan_o_aae_in_rendered(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        write_files(
            tmp_path / "ios-main/edit-img",
            ["IMG_E0001.HEIC", "IMG_O0001.AAE", "IMG_O9999.AAE"],
        )

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 1
        assert not (tmp_path / "ios-main/edit-img" / "IMG_O9999.AAE").exists()
        assert (tmp_path / "ios-main/edit-img" / "IMG_O0001.AAE").exists()

    def test_nothing_to_remove(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_0001.HEIC", "IMG_0001.AAE"])
        write_files(tmp_path / "ios-main/edit-img", ["IMG_E0001.HEIC", "IMG_O0001.AAE"])

        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 0

    def test_dry_run_does_not_modify(self, tmp_path: Path) -> None:
        write_files(tmp_path / "ios-main/orig-img", ["IMG_9999.AAE"])
        write_files(tmp_path / "ios-main/edit-img", [])

        result = rm_orphan_sidecar(tmp_path, MC, dry_run=True)
        assert result.total == 1
        assert (tmp_path / "ios-main/orig-img" / "IMG_9999.AAE").exists()

    def test_missing_dirs_are_safe(self, tmp_path: Path) -> None:
        result = rm_orphan_sidecar(tmp_path, MC)
        assert result.total == 0
