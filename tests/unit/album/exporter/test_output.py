import errno
from pathlib import Path

from photree.album.exporter.output import format_export_failure
from photree.album.exporter.settings import ResolvedExportSettings
from photree.foundation.linking import LinkMode
from photree.foundation.share_layout import AlbumShareLayout, ShareDirectoryLayout

_CWD = Path("/photos")


def _settings(
    album_layout: AlbumShareLayout,
    link_mode: LinkMode,
) -> ResolvedExportSettings:
    return ResolvedExportSettings(
        share_dir=Path("/Volumes/usb/share"),
        share_layout=ShareDirectoryLayout.ALBUMS,
        album_layout=album_layout,
        link_mode=link_mode,
    )


class TestFormatExportFailure:
    def test_refused_link_suggests_the_same_export_with_copies(self) -> None:
        exc = PermissionError(
            errno.EPERM,
            "Operation not permitted",
            "/Volumes/usb/share/2024/2024-07-14 - Trip/main-img/IMG_0001.HEIC",
        )

        text = format_export_failure(
            _CWD / "2024-07-14 - Trip",
            exc,
            _CWD,
            _settings(AlbumShareLayout.ALL, LinkMode.HARDLINK),
        )

        assert text.splitlines() == [
            (
                'Could not export "2024-07-14 - Trip": Operation not permitted:'
                " /Volumes/usb/share/2024/2024-07-14 - Trip/main-img/IMG_0001.HEIC."
            ),
            "If the share does not support hard links, export with copies:",
            (
                "  photree album export --album-dir '2024-07-14 - Trip'"
                " --share-dir /Volumes/usb/share --share-layout albums"
                " --album-layout all --link-mode copy"
            ),
        ]

    def test_copying_layout_suggests_checking_the_share(self) -> None:
        exc = OSError(errno.ENOSPC, "No space left on device", "/share/a/x.jpg")

        text = format_export_failure(
            _CWD / "a",
            exc,
            _CWD,
            _settings(AlbumShareLayout.BROWSABLE_JPG, LinkMode.HARDLINK),
        )

        assert text.splitlines() == [
            'Could not export "a": No space left on device: /share/a/x.jpg.',
            (
                "Check that the share is mounted, writable and has free space,"
                " then run the export again."
            ),
        ]

    def test_error_without_errno_keeps_its_message(self) -> None:
        text = format_export_failure(
            _CWD / "a",
            OSError("copy failed"),
            _CWD,
            _settings(AlbumShareLayout.ALL, LinkMode.COPY),
        )

        assert text.splitlines()[0] == 'Could not export "a": copy failed.'
