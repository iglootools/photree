"""Tests for photree.common.sips module — parallel execution."""

from photree.common.sips import run_parallel


class TestRunParallel:
    def test_empty_tasks_returns_empty(self) -> None:
        assert run_parallel([]) == []

    def test_runs_all_tasks(self) -> None:
        results: list[str] = []
        tasks: list[tuple[str, object]] = [
            ("a", lambda: results.append("a")),
            ("b", lambda: results.append("b")),
            ("c", lambda: results.append("c")),
        ]
        parallel_results = run_parallel(tasks, max_workers=2)

        assert sorted(results) == ["a", "b", "c"]
        assert all(r.success for r in parallel_results)
        assert len(parallel_results) == 3

    def test_captures_errors(self) -> None:
        def fail() -> None:
            raise RuntimeError("boom")

        tasks: list[tuple[str, object]] = [("fail", fail)]
        parallel_results = run_parallel(tasks, max_workers=1)

        assert len(parallel_results) == 1
        assert not parallel_results[0].success
        assert parallel_results[0].error == "boom"

    def test_calls_on_start_and_on_end(self) -> None:
        started: list[str] = []
        ended: list[tuple[str, bool]] = []

        tasks: list[tuple[str, object]] = [("x", lambda: None)]
        run_parallel(
            tasks,
            max_workers=1,
            on_start=lambda k: started.append(k),
            on_end=lambda k, s: ended.append((k, s)),
        )

        assert started == ["x"]
        assert ended == [("x", True)]

    def test_on_end_called_on_failure(self) -> None:
        ended: list[tuple[str, bool]] = []

        def fail() -> None:
            raise ValueError("oops")

        tasks: list[tuple[str, object]] = [("f", fail)]
        run_parallel(
            tasks,
            max_workers=1,
            on_end=lambda k, s: ended.append((k, s)),
        )

        assert ended == [("f", False)]

    def test_single_worker_runs_sequentially(self) -> None:
        order: list[str] = []
        tasks: list[tuple[str, object]] = [
            ("1", lambda: order.append("1")),
            ("2", lambda: order.append("2")),
        ]
        run_parallel(tasks, max_workers=1)

        assert sorted(order) == ["1", "2"]
