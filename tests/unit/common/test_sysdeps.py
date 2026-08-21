"""Tests for photree.common.sysdeps — external binary discovery."""

from __future__ import annotations

import pytest

from photree.common.sysdeps import (
    MissingSystemDependencyError,
    SystemDependency,
    check_system_dependencies,
    install_hint,
    is_available,
    missing_dependencies,
    purpose,
    require,
)


def _which(*present: SystemDependency):
    """Build a ``which`` stub that resolves only *present* dependencies."""
    names = {str(d) for d in present}
    return lambda name: f"/usr/bin/{name}" if name in names else None


class TestIsAvailable:
    def test_present(self) -> None:
        assert is_available(SystemDependency.SIPS, which=_which(SystemDependency.SIPS))

    def test_absent(self) -> None:
        assert not is_available(SystemDependency.SIPS, which=_which())


class TestCheckSystemDependencies:
    def test_reports_each_dependency(self) -> None:
        statuses = check_system_dependencies(
            (SystemDependency.SIPS, SystemDependency.EXIFTOOL),
            which=_which(SystemDependency.EXIFTOOL),
        )
        assert [(s.dependency, s.available) for s in statuses] == [
            (SystemDependency.SIPS, False),
            (SystemDependency.EXIFTOOL, True),
        ]

    def test_deduplicates_preserving_order(self) -> None:
        statuses = check_system_dependencies(
            (
                SystemDependency.EXIFTOOL,
                SystemDependency.SIPS,
                SystemDependency.EXIFTOOL,
            ),
            which=_which(),
        )
        assert [s.dependency for s in statuses] == [
            SystemDependency.EXIFTOOL,
            SystemDependency.SIPS,
        ]

    def test_empty(self) -> None:
        assert check_system_dependencies((), which=_which()) == ()


class TestMissingDependencies:
    def test_only_absent_ones(self) -> None:
        statuses = check_system_dependencies(
            tuple(SystemDependency), which=_which(SystemDependency.SIPS)
        )
        assert missing_dependencies(statuses) == (SystemDependency.EXIFTOOL,)

    def test_none_missing(self) -> None:
        statuses = check_system_dependencies(
            tuple(SystemDependency), which=_which(*SystemDependency)
        )
        assert missing_dependencies(statuses) == ()


class TestRequire:
    def test_passes_when_all_present(self) -> None:
        require(tuple(SystemDependency), which=_which(*SystemDependency))

    def test_raises_with_structured_missing_list(self) -> None:
        with pytest.raises(MissingSystemDependencyError) as exc_info:
            require(tuple(SystemDependency), which=_which(SystemDependency.SIPS))

        assert exc_info.value.missing == (SystemDependency.EXIFTOOL,)


class TestMetadata:
    @pytest.mark.parametrize("dependency", list(SystemDependency))
    def test_every_dependency_documents_itself(
        self, dependency: SystemDependency
    ) -> None:
        assert purpose(dependency)
        assert install_hint(dependency)
