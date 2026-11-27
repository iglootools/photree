import re
from pathlib import Path
from uuid import uuid4

from tests.fakes import invoke_cli


def _squashed(text: str) -> str:
    """Drop whitespace and Rich's panel borders, which wrap long messages."""
    return re.sub(r"[\s│╭╮╰╯─]", "", text)


class TestTildeExpansion:
    def test_path_option_expands_tilde_before_checking(self) -> None:
        # Regression: "~/x" was resolved to "<cwd>/~/x" and reported as missing.
        name = f".photree-missing-{uuid4().hex[:8]}"

        result = invoke_cli(["albums", "list", f"--dir=~/{name}"])

        assert result.exit_code == 2
        assert _squashed(str(Path.home() / name)) in _squashed(result.output)
        assert "/~/" not in _squashed(result.output)

    def test_config_option_expands_tilde(self, tmp_path: Path) -> None:
        name = f".photree-missing-{uuid4().hex[:8]}.toml"

        result = invoke_cli(
            ["albums", "export", "--dir", str(tmp_path), f"--config=~/{name}"],
        )

        assert result.exit_code == 2
        assert _squashed(str(Path.home() / name)) in _squashed(result.output)
