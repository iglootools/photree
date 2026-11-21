from rich.console import Console

from photree.common.formatting import CHECK, DRY_RUN_LABEL, format_dry_run


class TestFormatDryRun:
    def test_text_is_unchanged_when_not_dry_run(self) -> None:
        assert format_dry_run("Done.", dry_run=False) == "Done."

    def test_text_starts_with_label_when_dry_run(self) -> None:
        assert format_dry_run("Would rename A.", dry_run=True) == (
            f"{DRY_RUN_LABEL} Would rename A."
        )

    def test_label_follows_leading_newlines(self) -> None:
        assert format_dry_run("\n\nDone.", dry_run=True) == f"\n\n{DRY_RUN_LABEL} Done."

    def test_markup_label_survives_rich(self) -> None:
        console = Console(record=True, width=80)
        console.print(format_dry_run(f"{CHECK} done", dry_run=True, markup=True))
        assert console.export_text() == "[dry-run] ✓ done\n"
