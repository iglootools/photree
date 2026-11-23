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
from tests.fakes import fake_which


class TestIsAvailable:
    def test_present(self) -> None:
        assert is_available(
            SystemDependency.SIPS,
            which=fake_which(SystemDependency.SIPS),
        )

    def test_absent(self) -> None:
        assert not is_available(SystemDependency.SIPS, which=fake_which())


class TestCheckSystemDependencies:
    def test_reports_each_dependency(self) -> None:
        statuses = check_system_dependencies(
            (SystemDependency.SIPS, SystemDependency.EXIFTOOL),
            which=fake_which(SystemDependency.EXIFTOOL),
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
            which=fake_which(),
        )
        assert [s.dependency for s in statuses] == [
            SystemDependency.EXIFTOOL,
            SystemDependency.SIPS,
        ]

    def test_empty(self) -> None:
        assert check_system_dependencies((), which=fake_which()) == ()


class TestMissingDependencies:
    def test_only_absent_ones(self) -> None:
        statuses = check_system_dependencies(
            tuple(SystemDependency),
            which=fake_which(SystemDependency.SIPS),
        )
        assert missing_dependencies(statuses) == (SystemDependency.EXIFTOOL,)

    def test_none_missing(self) -> None:
        statuses = check_system_dependencies(
            tuple(SystemDependency),
            which=fake_which(*SystemDependency),
        )
        assert missing_dependencies(statuses) == ()


class TestRequire:
    def test_passes_when_all_present(self) -> None:
        require(tuple(SystemDependency), which=fake_which(*SystemDependency))

    def test_raises_with_structured_missing_list(self) -> None:
        with pytest.raises(MissingSystemDependencyError) as exc_info:
            require(tuple(SystemDependency), which=fake_which(SystemDependency.SIPS))

        assert exc_info.value.missing == (SystemDependency.EXIFTOOL,)


class TestMetadata:
    @pytest.mark.parametrize("dependency", list(SystemDependency))
    def test_every_dependency_documents_itself(
        self,
        dependency: SystemDependency,
    ) -> None:
        assert purpose(dependency)
        assert install_hint(dependency)
