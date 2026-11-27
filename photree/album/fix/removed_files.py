"""The result the fixes that only delete files return."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RemovedFiles:
    """
    The files a fix removed, per directory.

    *removed_by_dir* pairs each directory name with the files removed from
    it; directories with nothing removed are left out.
    """

    removed_by_dir: tuple[tuple[str, tuple[str, ...]], ...]

    @property
    def total(self) -> int:
        """Return the number of files removed."""
        return sum(len(files) for _, files in self.removed_by_dir)
