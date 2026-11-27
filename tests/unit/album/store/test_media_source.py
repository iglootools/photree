from photree.album.store.media_source import ios_media_source, std_media_source


class TestMediaExtensions:
    def test_ios_source_holds_only_mov_videos(self) -> None:
        assert ios_media_source("main").vid_extensions == frozenset({".mov"})

    def test_std_source_holds_every_video_format(self) -> None:
        assert std_media_source("nelu").vid_extensions == frozenset(
            {".avi", ".mov", ".mp4", ".wmv"},
        )

    def test_media_extensions_are_images_and_videos(self) -> None:
        ms = ios_media_source("main")

        assert ms.media_extensions == ms.img_extensions | ms.vid_extensions
