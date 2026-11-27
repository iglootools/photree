from pathlib import Path

from photree.album.id import format_album_external_id, format_image_external_id
from photree.album.naming import NamingIssue, NamingIssueCode
from photree.collection.id import format_collection_external_id
from photree.collection.refresh.result import (
    CollectionRefreshError,
    CollectionRefreshErrorKind,
    CollectionRefreshResult,
)
from photree.gallery.browsable_refresh import (
    BrowsableRefreshError,
    BrowsableRefreshErrorKind,
    DanglingMember,
    DanglingMemberKind,
)
from photree.gallery.cli.refresh_output import (
    format_browsable_error,
    format_collection_changes,
    format_collection_refresh_error,
    format_dangling_members,
)

CWD = Path("/gallery")
ALBUM = CWD / "albums" / "2024" / "2024-07-14 - Trip"
COLLECTION = CWD / "collections" / "2024" / "2024-07 - Summer"
SOME_ID = "00000000-0000-0000-0000-000000000001"
ALBUM_CHECK = "'photree album check --album-dir \"albums/2024/2024-07-14 - Trip\"'"
COLLECTION_CHECK = (
    "'photree collection check --dir \"collections/2024/2024-07 - Summer\"'"
)


class TestFormatCollectionChanges:
    def test_deleted_collection_with_kept_directory_says_so(self) -> None:
        result = CollectionRefreshResult(
            deleted=("2024-07-14 - Gone", "2024-07-15 - Kept"),
            kept_directories=("2024-07-15 - Kept",),
        )

        assert format_collection_changes(result) == [
            "deleted: 2024-07-14 - Gone",
            "deleted: 2024-07-15 - Kept (directory kept: it holds other files)",
        ]

    def test_no_change_says_so(self) -> None:
        assert format_collection_changes(CollectionRefreshResult()) == [
            "no changes",
        ]

    def test_every_change_and_album_rename_is_listed(self) -> None:
        result = CollectionRefreshResult(
            created=("A",),
            updated=("B",),
            renamed=(("C", "D"),),
            album_renames=(("old", "new"),),
        )

        assert format_collection_changes(result) == [
            "created: A",
            "updated: B",
            "renamed: C -> D",
            "",
            "Album title sync:",
            "old -> new",
        ]


class TestFormatCollectionRefreshError:
    def test_album_naming_lists_each_issue(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.ALBUM_NAMING,
            path=ALBUM,
            naming_issues=(NamingIssue(NamingIssueCode.INVALID_DATE, "invalid date"),),
        )

        assert format_collection_refresh_error(error, CWD) == (
            "album albums/2024/2024-07-14 - Trip: name breaks the naming "
            "convention\n"
            "  invalid date\n"
            f"Rename the album; run {ALBUM_CHECK} for details."
        )

    def test_album_missing_metadata(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.ALBUM_MISSING_METADATA,
            path=ALBUM,
        )

        assert format_collection_refresh_error(error, CWD) == (
            "album albums/2024/2024-07-14 - Trip: album metadata cannot be read\n"
            f"Run {ALBUM_CHECK} to investigate."
        )

    def test_collection_unreadable_metadata(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_UNREADABLE_METADATA,
            path=COLLECTION,
        )

        assert format_collection_refresh_error(error, CWD) == (
            "collection collections/2024/2024-07 - Summer: collection metadata "
            f"cannot be read\nRun {COLLECTION_CHECK} to investigate."
        )

    def test_date_collision_names_the_albums(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.DATE_COLLISION,
            name="2024-07-14",
            album_names=("2024-07-14 - A", "2024-07-14 - B"),
        )

        assert format_collection_refresh_error(error, CWD) == (
            "date collision on 2024-07-14: 2024-07-14 - A, 2024-07-14 - B\n"
            "Add part numbers to disambiguate; run 'photree gallery check' for "
            "the full report."
        )

    def test_album_rename_conflict_names_the_taken_target(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.ALBUM_RENAME_CONFLICT,
            path=ALBUM,
            target=CWD / "albums" / "2024" / "2024-07-14 - Hike",
        )

        assert format_collection_refresh_error(error, CWD) == (
            "album albums/2024/2024-07-14 - Trip: cannot sync its title, "
            "albums/2024/2024-07-14 - Hike is already taken\n"
            "Rename one of the two albums, then run 'photree gallery refresh'."
        )

    def test_collection_target_exists_on_rename(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
            path=COLLECTION,
            target=CWD / "collections" / "2024" / "2024-07 - Taken",
        )

        assert format_collection_refresh_error(error, CWD) == (
            "cannot rename collections/2024/2024-07 - Summer: "
            "collections/2024/2024-07 - Taken already exists\n"
            "Move the existing directory away, then run 'photree gallery refresh'."
        )

    def test_collection_target_exists_on_create(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_TARGET_EXISTS,
            target=COLLECTION,
        )

        assert format_collection_refresh_error(error, CWD).startswith(
            "cannot create implicit collection: "
            "collections/2024/2024-07 - Summer already exists\n",
        )

    def test_series_name_conflict(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.SERIES_NAME_CONFLICT,
            name="2024-07 - Trip",
        )

        assert format_collection_refresh_error(error, CWD) == (
            "implicit collection '2024-07 - Trip' is claimed by two separate "
            "runs of the same series on the same dates\n"
            "Give the runs distinct series names, then run "
            "'photree gallery refresh'."
        )

    def test_collection_move_failed_lists_what_is_stranded(self) -> None:
        stranded = COLLECTION.with_name(".photree-moving-x")
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.COLLECTION_MOVE_FAILED,
            path=COLLECTION,
            target=CWD / "collections" / "2025" / "2025-07 - Summer",
            reason="File exists",
            stranded=(stranded,),
        )

        failure = (
            "cannot rename collections/2024/2024-07 - Summer to "
            "collections/2025/2025-07 - Summer: File exists"
        )
        assert format_collection_refresh_error(error, CWD).split("\n")[:2] == [
            failure,
            "  left under a temporary name: collections/2024/.photree-moving-x",
        ]

    def test_stranded_collection_move(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.STRANDED_COLLECTION_MOVE,
            path=COLLECTION.with_name(".photree-moving-x"),
        )

        assert format_collection_refresh_error(error, CWD).startswith(
            "collection collections/2024/.photree-moving-x was left under a "
            "temporary name by an interrupted refresh\n",
        )


class TestFormatCollectionFilesystemError:
    def test_names_both_paths_and_says_earlier_changes_were_applied(self) -> None:
        error = CollectionRefreshError(
            CollectionRefreshErrorKind.FILESYSTEM_ERROR,
            path=ALBUM,
            target=ALBUM.with_name("2024-07-14 - Hike"),
            reason="Permission denied",
        )

        assert format_collection_refresh_error(error, CWD) == (
            "cannot write albums/2024/2024-07-14 - Trip -> "
            "albums/2024/2024-07-14 - Hike: Permission denied\n"
            "The changes listed above were applied. Fix the cause, then run "
            "'photree gallery refresh'."
        )


class TestFormatBrowsableError:
    def test_regular_file(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.REGULAR_FILE,
            CWD / "browsable" / "notes.txt",
        )

        assert format_browsable_error(error, CWD) == (
            "browsable/ contains a regular file: browsable/notes.txt\n"
            "Expected only directories and symlinks. Remove the file (or "
            "browsable/), then run 'photree gallery refresh'."
        )

    def test_filesystem_error_says_the_tree_is_incomplete(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.FILESYSTEM_ERROR,
            CWD / "browsable",
            reason="Permission denied",
        )

        assert format_browsable_error(error, CWD) == (
            "cannot write browsable: Permission denied\n"
            "browsable/ is left incomplete. Fix the cause, then run "
            "'photree gallery refresh'."
        )

    def test_duplicate_album_id_names_every_album_and_the_fix(self) -> None:
        copy = ALBUM.with_name("2024-07-15 - Trip copy")
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.DUPLICATE_ALBUM_ID,
            ALBUM,
            album_id=SOME_ID,
            albums=(ALBUM, copy),
        )

        assert format_browsable_error(error, CWD) == (
            "Duplicate album IDs found:\n"
            f"  {format_album_external_id(SOME_ID)}:\n"
            "    albums/2024/2024-07-14 - Trip\n"
            "    albums/2024/2024-07-15 - Trip copy\n"
            "\n"
            "Run 'photree albums fix --new-id --album-dir "
            '"albums/2024/2024-07-15 - Trip copy"\' to give new IDs to all but '
            "the first album of each ID.\n"
            "If collections or faces refer to another of them, name the others "
            "instead.\n"
            "Then run 'photree gallery refresh'."
        )

    def test_album_missing_metadata(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_MISSING_METADATA,
            ALBUM,
        )

        assert format_browsable_error(error, CWD) == (
            "album albums/2024/2024-07-14 - Trip: album metadata cannot be read\n"
            f"Run {ALBUM_CHECK} to investigate."
        )

    def test_album_unparseable_name(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.ALBUM_UNPARSEABLE_NAME,
            ALBUM,
        )

        assert format_browsable_error(error, CWD) == (
            "album albums/2024/2024-07-14 - Trip: name has no parseable date\n"
            f"Rename the album; run {ALBUM_CHECK} for details."
        )

    def test_collection_unreadable_metadata(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.COLLECTION_UNREADABLE_METADATA,
            COLLECTION,
        )

        assert format_browsable_error(error, CWD) == (
            "collection collections/2024/2024-07 - Summer: collection metadata "
            f"cannot be read\nRun {COLLECTION_CHECK} to investigate."
        )

    def test_cycle_names_the_collection_by_its_external_id(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.CYCLE,
            COLLECTION,
            collection_id=SOME_ID,
        )

        assert format_browsable_error(error, CWD) == (
            "cycle detected: collection collections/2024/2024-07 - Summer "
            f"({format_collection_external_id(SOME_ID)}) contains itself "
            f"through its members\nRun {COLLECTION_CHECK} to investigate."
        )

    def test_link_collision_names_the_link_and_every_target(self) -> None:
        error = BrowsableRefreshError(
            BrowsableRefreshErrorKind.LINK_COLLISION,
            CWD / "browsable" / "public" / "Trip" / "main-jpg",
            targets=(
                CWD / "albums" / "a" / "Trip" / "main-jpg",
                CWD / "albums" / "b" / "Trip" / "main-jpg",
            ),
        )

        assert format_browsable_error(error, CWD) == (
            "browsable link browsable/public/Trip/main-jpg would point to more "
            "than one target:\n"
            "  albums/a/Trip/main-jpg\n"
            "  albums/b/Trip/main-jpg\n"
            "Two albums or collections share a name there: rename one of them, "
            "then run 'photree gallery refresh'."
        )


class TestFormatDanglingMembers:
    def test_lists_each_member_and_one_check_per_collection(self) -> None:
        members = (
            DanglingMember(COLLECTION, DanglingMemberKind.ALBUM, SOME_ID),
            DanglingMember(COLLECTION, DanglingMemberKind.IMAGE, SOME_ID),
        )

        assert format_dangling_members(members, CWD) == (
            "2 collection member(s) not found in the gallery (skipped):\n"
            "  collections/2024/2024-07 - Summer: album "
            f"{format_album_external_id(SOME_ID)}\n"
            "  collections/2024/2024-07 - Summer: image "
            f"{format_image_external_id(SOME_ID)}\n"
            "To investigate, run:\n"
            f"  {COLLECTION_CHECK}"
        )
