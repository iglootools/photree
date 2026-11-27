from photree.album.check import AlbumCheckFailureKind, AlbumCheckWarningKind
from photree.album.check.output.album import format_check_label, format_check_labels


class TestFormatCheckLabel:
    def test_every_kind_has_its_own_label(self) -> None:
        kinds = [*AlbumCheckFailureKind, *AlbumCheckWarningKind]

        labels = format_check_labels(kinds)

        assert len(set(labels)) == len(kinds)
        assert all(labels)

    def test_label_is_prose_not_the_token(self) -> None:
        assert format_check_label(AlbumCheckFailureKind.MISSING_DIRS) == "missing dirs"
        assert (
            format_check_label(AlbumCheckWarningKind.EXIF_DATE_MISMATCH)
            == "exif date mismatch"
        )
