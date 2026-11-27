import os
from pathlib import Path

import pytest

from photree.foundation.gallery_metadata import (
    load_gallery_metadata,
)
from photree.foundation.metadata_io import (
    InvalidMetadataError,
    load_yaml_mapping,
    write_yaml,
)


class TestYamlMetadataIO:
    def test_absent_file_is_none(self, tmp_path: Path) -> None:
        assert load_yaml_mapping(tmp_path / "missing.yaml") is None

    @pytest.mark.parametrize("content", ["", "- a\n- b\n", "key: [unclosed\n"])
    def test_present_but_unusable_file_raises(
        self,
        tmp_path: Path,
        content: str,
    ) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(InvalidMetadataError) as info:
            load_yaml_mapping(path)
        assert info.value.path == path

    def test_file_that_is_not_utf8_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_bytes(b"title: \xff\n")
        with pytest.raises(InvalidMetadataError) as info:
            load_yaml_mapping(path)
        assert info.value.path == path

    @pytest.mark.skipif(
        os.geteuid() == 0,
        reason="root reads a file whatever its permissions",
    )
    def test_file_that_cannot_be_read_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "album.yaml"
        path.write_text("id: x\n", encoding="utf-8")
        path.chmod(0)
        try:
            with pytest.raises(InvalidMetadataError) as info:
                load_yaml_mapping(path)
        finally:
            path.chmod(0o600)
        assert (info.value.path, info.value.reason) == (
            path,
            "cannot be read (Permission denied)",
        )

    def test_corrupt_gallery_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "gallery.yaml"
        path.write_text("link-mode: teleport\n", encoding="utf-8")
        with pytest.raises(InvalidMetadataError) as info:
            load_gallery_metadata(path)
        assert info.value.path == path

    def test_round_trips_non_ascii(self, tmp_path: Path) -> None:
        path = tmp_path / "x.yaml"
        write_yaml(path, {"title": "Été à Montréal"})
        assert load_yaml_mapping(path) == {"title": "Été à Montréal"}

    def test_write_replaces_the_file_instead_of_truncating_it(
        self,
        tmp_path: Path,
    ) -> None:
        # A hard link to the old file keeps its content only when the write
        # renames a new file over the path rather than rewriting it in place,
        # which is what spares the old content from an interrupted write.
        path = tmp_path / "x.yaml"
        write_yaml(path, {"id": "old"})
        old_link = tmp_path / "old-link.yaml"
        old_link.hardlink_to(path)

        write_yaml(path, {"id": "new"})

        assert load_yaml_mapping(path) == {"id": "new"}
        assert load_yaml_mapping(old_link) == {"id": "old"}

    def test_write_leaves_no_temporary_file(self, tmp_path: Path) -> None:
        path = tmp_path / "x.yaml"
        write_yaml(path, {"id": "a"})
        write_yaml(path, {"id": "b"})
        assert [p.name for p in tmp_path.iterdir()] == ["x.yaml"]

    def test_failed_write_removes_its_temporary_file(self, tmp_path: Path) -> None:
        # A directory cannot be replaced by a file.
        path = tmp_path / "x.yaml"
        (path / "occupied").mkdir(parents=True)
        with pytest.raises(IsADirectoryError):
            write_yaml(path, {"id": "a"})
        assert [p.name for p in tmp_path.iterdir()] == ["x.yaml"]
