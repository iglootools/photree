from contextlib import chdir
from pathlib import Path

import pytest
import typer

from photree.clihelpers.paths import check_user_path


class TestCheckUserPath:
    def test_tilde_is_expanded_before_resolving(self) -> None:
        # Regression: resolve_path turned "~/x" into "<cwd>/~/x".
        assert check_user_path(Path("~/x")) == Path.home() / "x"

    def test_unresolved_path_keeps_relative_parts(self) -> None:
        assert check_user_path(Path("a/b"), resolve=False) == Path("a/b")

    def test_relative_path_resolves_against_cwd(self, tmp_path: Path) -> None:
        with chdir(tmp_path):
            assert check_user_path(Path("a")) == tmp_path.resolve() / "a"

    def test_missing_path_is_rejected_when_it_must_exist(self, tmp_path: Path) -> None:
        with pytest.raises(typer.BadParameter, match="does not exist"):
            check_user_path(tmp_path / "missing", exists=True)

    def test_file_is_rejected_where_a_directory_is_expected(
        self,
        tmp_path: Path,
    ) -> None:
        file = tmp_path / "f.txt"
        file.write_text("", encoding="utf-8")
        with pytest.raises(typer.BadParameter, match=r"Directory .* is a file"):
            check_user_path(file, file_okay=False)

    def test_directory_is_rejected_where_a_file_is_expected(
        self,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(typer.BadParameter, match=r"File .* is a directory"):
            check_user_path(tmp_path, dir_okay=False)
