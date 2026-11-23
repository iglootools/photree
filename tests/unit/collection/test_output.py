from photree.album.id import format_album_external_id, generate_album_id
from photree.collection.check import CollectionCheckIssue, CollectionIssueCode
from photree.collection.output import format_collection_issue
from photree.collection.store.protocol import (
    CollectionLifecycle,
    CollectionMembers,
    CollectionStrategy,
    MemberType,
)


class TestFormatCollectionIssue:
    def test_missing_member_shows_external_id(self) -> None:
        album_id = generate_album_id()
        issue = CollectionCheckIssue(
            CollectionIssueCode.MISSING_ALBUM,
            member_type=MemberType.ALBUM,
            member_id=album_id,
        )

        assert format_collection_issue(issue) == (
            f"album {format_album_external_id(album_id)} not found in gallery"
        )

    def test_invalid_member_id_is_shown_as_written(self) -> None:
        issue = CollectionCheckIssue(
            CollectionIssueCode.MISSING_IMAGE,
            member_type=MemberType.IMAGE,
            member_id="not-a-uuid",
        )

        assert format_collection_issue(issue) == "image not-a-uuid not found in gallery"

    def test_date_not_covered_names_both_dates(self) -> None:
        issue = CollectionCheckIssue(
            CollectionIssueCode.DATE_NOT_COVERED,
            member_type=MemberType.COLLECTION,
            member_id="x",
            member_date="2023-05",
            collection_date="2024",
        )

        assert format_collection_issue(issue) == (
            "collection x date 2023-05 outside collection range 2024"
        )

    def test_invalid_config_names_the_combination(self) -> None:
        issue = CollectionCheckIssue(
            CollectionIssueCode.INVALID_COLLECTION_CONFIG,
            config=(
                CollectionMembers.MANUAL,
                CollectionLifecycle.IMPLICIT,
                CollectionStrategy.IMPORT,
            ),
        )

        assert format_collection_issue(issue).startswith(
            "invalid combination: members=manual, lifecycle=implicit, strategy=import.",
        )
