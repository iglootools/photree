from pathlib import Path

from photree.album.check import check_album_integrity
from photree.album.store.media_sources_discovery import discover_media_sources
from photree.foundation.linking import LinkMode
from tests.testkit import add_consistent_ios_album


class TestCheckIosAlbumIntegrity:
    def test_correct_album_passes(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)

        result = check_album_integrity(
            album,
            link_mode=LinkMode.COPY,
            checksum=True,
            media_sources=discover_media_sources(album),
        )
        assert result.success

    def test_calls_on_file_checked(self, tmp_path: Path) -> None:
        album = tmp_path / "album"
        add_consistent_ios_album(album)

        checked: list[tuple[str, bool]] = []

        def record_checked(name: str, *, success: bool) -> None:
            checked.append((name, success))

        check_album_integrity(
            album,
            link_mode=LinkMode.COPY,
            checksum=False,
            on_file_checked=record_checked,
            media_sources=discover_media_sources(album),
        )
        assert len(checked) > 0
        assert all(ok for _, ok in checked)
