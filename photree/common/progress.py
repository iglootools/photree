"""Callbacks that report the end of one unit of work, with its success named."""

from typing import Protocol


class FileEnd(Protocol):
    """Called when the work on one file ends, saying whether it succeeded."""

    def __call__(  # noqa: DC02 -- a Protocol member, called through FileEnd
        self,
        name: str,
        /,
        *,
        success: bool,
    ) -> None:
        """Report that the work on file *name* ended, with its *success*."""
        ...


class ItemEnd(Protocol):
    """Called when the work on one item ends, with the labels of what failed."""

    def __call__(  # noqa: DC02 -- a Protocol member, called through ItemEnd
        self,
        name: str,
        /,
        *,
        success: bool,
        error_labels: tuple[str, ...],
    ) -> None:
        """Report that item *name* ended, with its *success* and *error_labels*."""
        ...


class CheckedItemEnd(Protocol):
    """Called when the check of one item ends, with its errors and warnings."""

    def __call__(  # noqa: DC02 -- a Protocol member, called through CheckedItemEnd
        self,
        name: str,
        /,
        *,
        success: bool,
        error_labels: tuple[str, ...],
        warning_labels: tuple[str, ...],
    ) -> None:
        """Report that item *name*'s check ended, with its success and labels."""
        ...
