from pathlib import Path

from tests.fakes import invoke_cli


class TestGalleryFix:
    def test_new_id_is_not_an_option(self, tmp_path: Path) -> None:
        result = invoke_cli(
            ["gallery", "fix", "--new-id", "--gallery-dir", str(tmp_path)],
        )

        assert result.exit_code == 2
        assert "No such option" in result.output

    def test_invalid_flags_suggest_help(self, tmp_path: Path) -> None:
        result = invoke_cli(["gallery", "fix", "--gallery-dir", str(tmp_path)])

        assert result.exit_code == 2
        assert "'photree gallery fix --help'" in result.output
