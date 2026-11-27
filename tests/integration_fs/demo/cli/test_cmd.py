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

    def test_refuses_a_non_empty_base_dir(self, tmp_path: Path) -> None:
        # Regression: seeding overwrote files with the demo's names.
        existing = tmp_path / "image-capture" / "IMG_0001.HEIC"
        existing.parent.mkdir()
        existing.write_bytes(b"mine")

        result = invoke_cli(
            ["demo", "seed", "--base-dir", str(tmp_path)],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 1
        assert "--force" in result.output
        assert existing.read_bytes() == b"mine"

    def test_force_seeds_a_non_empty_base_dir(self, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("mine", encoding="utf-8")

        result = invoke_cli(
            ["demo", "seed", "--base-dir", str(tmp_path), "--force"],
            runtime=fake_runtime(),
        )

        assert result.exit_code == 0, result.output
        assert any((tmp_path / "image-capture").iterdir())
