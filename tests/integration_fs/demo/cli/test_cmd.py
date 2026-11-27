from pathlib import Path

from tests.fakes import fake_runtime, invoke_cli


class TestDemoOutput:
    def test_every_sample_renders(self) -> None:
        result = invoke_cli(["demo", "output"])

        assert result.exit_code == 0, result.output
        assert "format_albums_stats" in result.output


class TestDemoSeed:
    def test_seeds_the_album_and_image_capture_dir(self, tmp_path: Path) -> None:
        base = tmp_path / "demo"

        result = invoke_cli(
            ["demo", "seed", "--base-dir", str(base), "--album-name", "2024 - Demo"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert any((base / "image-capture").iterdir())
        assert any((base / "2024 - Demo" / "to-import-ios-main").iterdir())
