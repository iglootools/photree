"""Remove the staging directories an import has emptied."""

from pathlib import Path


def remove_dir_if_only_hidden_files(directory: Path) -> None:
    """
    Remove *directory* when it holds nothing but hidden files (``.DS_Store``).

    Hidden files are what Finder leaves behind, never media an import would
    copy, so they do not keep a consumed staging directory alive. Does nothing
    when *directory* does not exist or holds anything else.
    """
    entries = list(directory.iterdir()) if directory.is_dir() else None
    if entries is not None and all(
        p.name.startswith(".") and p.is_file() for p in entries
    ):
        for p in entries:
            p.unlink()
        directory.rmdir()
