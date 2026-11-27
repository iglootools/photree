from pathlib import Path

import pytest
import yaml

from photree.foundation.gallery_metadata import (
    GalleryMetadata,
    GalleryNotFoundError,
    load_gallery_metadata,
    resolve_gallery_dir,
    resolve_gallery_metadata,
    resolve_link_mode,
    save_gallery_metadata,
)
from photree.foundation.layout import PHOTREE_DIR
from photree.foundation.linking import LinkMode
from photree.foundation.metadata_io import (
    InvalidMetadataError,
    write_yaml,
)


class TestGalleryMetadata:
    def test_yaml_roundtrip(self, tmp_path: Path) -> None:
        path = tmp_path / PHOTREE_DIR / "gallery.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            yaml.safe_dump(
                GalleryMetadata(link_mode=LinkMode.SYMLINK).model_dump(
                    by_alias=True,
                    mode="json",
                ),
                default_flow_style=False,
                sort_keys=False,
            ),
        )

        loaded = load_gallery_metadata(path)
        assert loaded.link_mode == LinkMode.SYMLINK

    def test_yaml_uses_kebab_case(self) -> None:
        meta = GalleryMetadata(link_mode=LinkMode.COPY)
        dumped = yaml.safe_dump(
            meta.model_dump(by_alias=True, mode="json"),
            default_flow_style=False,
            sort_keys=False,
        )
        assert "link-mode" in dumped
        assert "link_mode" not in dumped

    def test_default_link_mode_is_hardlink(self) -> None:
        meta = GalleryMetadata()
        assert meta.link_mode == LinkMode.HARDLINK

    @pytest.mark.parametrize("threshold", [0.0, 1.0])
    def test_load_accepts_threshold_bounds(
        self,
        tmp_path: Path,
        threshold: float,
    ) -> None:
        path = tmp_path / "gallery.yaml"
        write_yaml(path, {"face-cluster-threshold": threshold})
        assert load_gallery_metadata(path).face_cluster_threshold == threshold

    @pytest.mark.parametrize("threshold", [-0.1, 1.5, 5])
    def test_load_rejects_threshold_out_of_range(
        self,
        tmp_path: Path,
        threshold: float,
    ) -> None:
        path = tmp_path / "gallery.yaml"
        write_yaml(path, {"face-cluster-threshold": threshold})
        with pytest.raises(InvalidMetadataError) as info:
            load_gallery_metadata(path)
        assert info.value.path == path


class TestResolveGalleryMetadata:
    def test_no_gallery_yaml_returns_none(self, tmp_path: Path) -> None:
        assert resolve_gallery_metadata(tmp_path) is None

    def test_finds_gallery_yaml_in_parent(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        child = tmp_path / "subdir"
        child.mkdir()

        result = resolve_gallery_metadata(child)
        assert result is not None
        assert result.link_mode == LinkMode.SYMLINK

    def test_finds_gallery_yaml_in_grandparent(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: copy\n")

        grandchild = tmp_path / "a" / "b"
        grandchild.mkdir(parents=True)

        result = resolve_gallery_metadata(grandchild)
        assert result is not None
        assert result.link_mode == LinkMode.COPY


class TestResolveLinkMode:
    def test_explicit_overrides_gallery(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        assert resolve_link_mode(LinkMode.COPY, tmp_path) == LinkMode.COPY

    def test_gallery_overrides_default(self, tmp_path: Path) -> None:
        gallery_yaml = tmp_path / PHOTREE_DIR / "gallery.yaml"
        gallery_yaml.parent.mkdir(parents=True)
        gallery_yaml.write_text("link-mode: symlink\n")

        assert resolve_link_mode(None, tmp_path) == LinkMode.SYMLINK

    def test_fallback_to_hardlink(self, tmp_path: Path) -> None:
        assert resolve_link_mode(None, tmp_path) == LinkMode.HARDLINK


class TestResolveGalleryDir:
    def test_explicit_dir_with_gallery_yaml(self, tmp_path: Path) -> None:
        save_gallery_metadata(tmp_path, GalleryMetadata())
        assert resolve_gallery_dir(tmp_path, start_dir=tmp_path) == tmp_path

    def test_explicit_dir_without_gallery_yaml_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GalleryNotFoundError) as info:
            resolve_gallery_dir(tmp_path, start_dir=tmp_path)
        assert info.value.explicit == tmp_path

    def test_resolves_by_walking_up_from_start_dir(self, tmp_path: Path) -> None:
        save_gallery_metadata(tmp_path, GalleryMetadata())
        child = tmp_path / "subdir"
        child.mkdir()
        assert resolve_gallery_dir(None, start_dir=child) == tmp_path.resolve()

    def test_no_gallery_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(GalleryNotFoundError) as info:
            resolve_gallery_dir(None, start_dir=tmp_path)
        assert info.value.explicit is None
        assert info.value.searched_from == tmp_path.resolve()
