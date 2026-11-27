from pathlib import Path

from photree.albums.cmd_handler import BatchFailure
from photree.albums.cmd_handler.check import (
    BatchCheckResult,
    CrossAlbumCheckResult,
    compute_batch_check_summary,
)

_A, _B, _C, _D = (Path(name) for name in ("A", "B", "C", "D"))


def _cross_album(
    *,
    colliding: frozenset[Path] = frozenset(),
    unreadable: frozenset[Path] = frozenset(),
    duplicate_album_ids: dict[str, tuple[Path, ...]] | None = None,
) -> CrossAlbumCheckResult:
    return CrossAlbumCheckResult(
        naming_result=None,
        colliding_albums=colliding,
        unreadable_albums=unreadable,
        duplicate_album_ids=duplicate_album_ids or {},
        duplicate_media_ids={},
    )


class TestCrossAlbumCheckResult:
    def test_failed_albums_joins_every_cross_album_failure(self) -> None:
        result = _cross_album(
            colliding=frozenset({_A}),
            unreadable=frozenset({_B}),
            duplicate_album_ids={"x": (_C, _D)},
        )

        assert result.failed_albums == {_A, _B, _C, _D}


class TestComputeBatchCheckSummary:
    def test_album_failing_several_ways_is_counted_once(self) -> None:
        summary = compute_batch_check_summary(
            [_A, _B, _C],
            BatchCheckResult(passed=2, warned=0, failed_albums=(_A,)),
            _cross_album(colliding=frozenset({_A})),
            (BatchFailure(_A, "boom"),),
        )

        assert (summary.passed, summary.failed_albums) == (2, (_A,))

    def test_failed_album_is_not_counted_as_warned(self) -> None:
        summary = compute_batch_check_summary(
            [_A, _B],
            BatchCheckResult(passed=2, warned=2, warned_albums=(_A, _B)),
            _cross_album(unreadable=frozenset({_B})),
        )

        assert (summary.passed, summary.warned) == (1, 1)
        assert not summary.success

    def test_failed_albums_are_sorted(self) -> None:
        summary = compute_batch_check_summary(
            [_A, _B, _C],
            BatchCheckResult(passed=3, warned=0),
            _cross_album(duplicate_album_ids={"x": (_C, _A)}),
        )

        assert summary.failed_albums == (_A, _C)

    def test_succeeds_when_nothing_failed(self) -> None:
        summary = compute_batch_check_summary(
            [_A],
            BatchCheckResult(passed=1, warned=0),
            _cross_album(),
        )

        assert summary.success
        assert summary.passed == 1
