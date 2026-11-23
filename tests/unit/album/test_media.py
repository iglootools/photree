from photree.album.media import compute_media_id_transfer
from photree.album.store.media_metadata import MediaMetadata, MediaSourceMediaMetadata

_IMAGE = False
_VIDEO = True


def _ids(
    images: dict[str, str] | None = None,
    videos: dict[str, str] | None = None,
) -> MediaSourceMediaMetadata:
    return MediaSourceMediaMetadata(images=images or {}, videos=videos or {})


class TestComputeMediaIdTransfer:
    def test_moved_image_id_leaves_source_and_joins_dest(self) -> None:
        source = MediaMetadata(
            media_sources={"main": _ids(images={"u1": "0001", "u2": "0002"})},
        )
        dest = MediaMetadata(media_sources={"main": _ids(images={"u3": "0003"})})

        source_after, dest_after = compute_media_id_transfer(
            source,
            dest,
            {("main", _IMAGE): frozenset({"0001"})},
        )

        assert source_after.media_sources["main"].images == {"u2": "0002"}
        assert dest_after.media_sources["main"].images == {
            "u3": "0003",
            "u1": "0001",
        }

    def test_image_and_video_with_one_key_move_separately(self) -> None:
        source = MediaMetadata(
            media_sources={
                "main": _ids(images={"img": "0001"}, videos={"vid": "0001"}),
            },
        )

        source_after, dest_after = compute_media_id_transfer(
            source,
            MediaMetadata(),
            {("main", _VIDEO): frozenset({"0001"})},
        )

        assert source_after.media_sources["main"] == _ids(images={"img": "0001"})
        assert dest_after.media_sources["main"] == _ids(videos={"vid": "0001"})

    def test_stale_dest_entry_for_moved_key_is_replaced(self) -> None:
        source = MediaMetadata(media_sources={"main": _ids(images={"u1": "0001"})})
        dest = MediaMetadata(media_sources={"main": _ids(images={"stale": "0001"})})

        _, dest_after = compute_media_id_transfer(
            source,
            dest,
            {("main", _IMAGE): frozenset({"0001"})},
        )

        assert dest_after.media_sources["main"].images == {"u1": "0001"}

    def test_dest_is_unchanged_when_source_has_no_ids(self) -> None:
        dest = MediaMetadata(media_sources={"other": _ids(images={"u9": "0009"})})

        source_after, dest_after = compute_media_id_transfer(
            MediaMetadata(),
            dest,
            {("main", _IMAGE): frozenset({"0001"})},
        )

        assert source_after == MediaMetadata()
        assert dest_after == dest

    def test_other_media_sources_are_untouched(self) -> None:
        source = MediaMetadata(
            media_sources={
                "main": _ids(images={"u1": "0001"}),
                "bruno": _ids(images={"u2": "0001"}),
            },
        )

        source_after, dest_after = compute_media_id_transfer(
            source,
            MediaMetadata(),
            {("main", _IMAGE): frozenset({"0001"})},
        )

        assert source_after.media_sources["bruno"] == _ids(images={"u2": "0001"})
        assert "bruno" not in dest_after.media_sources
