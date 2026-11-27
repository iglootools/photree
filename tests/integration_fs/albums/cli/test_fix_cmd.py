from pathlib import Path

from photree.album.store.metadata import load_album_metadata
from tests.fakes import invoke_cli
from tests.testkit import add_emptied_std_media_source, make_album


def _album_id(album: Path) -> str | None:
    meta = load_album_metadata(album)
    return meta.id if meta is not None else None


class TestAlbumsFix:
    def test_rm_upstream_refusal_then_force(self, tmp_path: Path) -> None:
        """Batch rm-upstream refuses an emptied archive unless --force is given."""
        album = tmp_path / "2024-07-14 - Trip"
        add_emptied_std_media_source(album)
        args = ["albums", "fix", "--rm-upstream", "--album-dir", str(album)]

        refused = invoke_cli(args)

        assert refused.exit_code == 1
        assert (album / "std-nelu/orig-vid/clip.mov").exists()
        assert "--rm-upstream --force" not in refused.output
        assert "--rm-upstream" in refused.output  # retry command keeps the fix flag

        forced = invoke_cli([*args, "--force"])

        assert forced.exit_code == 0, forced.output
        assert not (album / "std-nelu/orig-vid/clip.mov").exists()

    def test_new_id_on_a_scan_exits_2(self, tmp_path: Path) -> None:
        # Regression: a scan gave every album found a new ID, orphaning every
        # collection and face reference to them.
        album, album_id = make_album(tmp_path, "2024-07-14 - Trip")

        result = invoke_cli(["albums", "fix", "--new-id", "--dir", str(tmp_path)])

        assert result.exit_code == 2
        assert "'photree albums fix --new-id --album-dir <album>'" in result.output
        assert _album_id(album) == album_id

    def test_new_id_changes_only_the_named_albums(self, tmp_path: Path) -> None:
        named, named_id = make_album(tmp_path, "2024-07-14 - Trip copy")
        other, other_id = make_album(tmp_path, "2024-07-14 - Trip")

        result = invoke_cli(["albums", "fix", "--new-id", "--album-dir", str(named)])

        assert result.exit_code == 0, result.output
        assert _album_id(named) not in (None, named_id)
        assert _album_id(other) == other_id
