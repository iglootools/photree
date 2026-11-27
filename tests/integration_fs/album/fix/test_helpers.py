from pathlib import Path

import pytest

from photree.album.fix.helpers import NotAnIosMediaSourceError
from photree.album.fix.ios import (
    MiscategorizedAction,
    prefer_higher_quality_when_dups,
    rm_orphan_sidecar,
)
from photree.album.fix.ios.miscategorized import fix_miscategorized
from photree.album.store.media_source import std_media_source
from tests.testkit import file_names, write_files

STD = std_media_source("nelu")


class TestIosOnlyFixesRefuseStdSources:
    def test_prefer_higher_quality_refuses_a_std_source(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["DSC_0001.HEIC", "DSC_0001.JPG"])

        with pytest.raises(NotAnIosMediaSourceError) as exc_info:
            prefer_higher_quality_when_dups(tmp_path, STD)

        assert exc_info.value.media_source == "nelu"
        assert len(file_names(tmp_path / "std-nelu/orig-img")) == 2

    def test_rm_orphan_sidecar_refuses_a_std_source(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["DSC_0001.AAE"])

        with pytest.raises(NotAnIosMediaSourceError):
            rm_orphan_sidecar(tmp_path, STD)

        assert file_names(tmp_path / "std-nelu/orig-img") == {"DSC_0001.AAE"}

    def test_miscategorized_refuses_a_std_source(self, tmp_path: Path) -> None:
        write_files(tmp_path / "std-nelu/orig-img", ["IMG_E0001.HEIC"])

        with pytest.raises(NotAnIosMediaSourceError):
            fix_miscategorized(
                tmp_path,
                [STD],
                action=MiscategorizedAction.RM,
                dry_run=False,
            )

        assert file_names(tmp_path / "std-nelu/orig-img") == {"IMG_E0001.HEIC"}
