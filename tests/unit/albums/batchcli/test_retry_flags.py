"""The flags each batch command repeats on its suggested retry commands."""

import inspect
from collections.abc import Callable

import pytest
import typer
from typer.core import TyperGroup, TyperOption

from photree.albums.batchcli.check import check_retry_flags
from photree.albums.batchcli.detect_faces import detect_faces_retry_flags
from photree.albums.batchcli.fix import fix_ios_retry_flags, fix_retry_flags
from photree.albums.batchcli.refresh import refresh_retry_flags
from photree.cli.app import app

type RetryFlagsFn = Callable[..., list[tuple[str, bool]]]


def _flag_names(retry_flags: RetryFlagsFn) -> list[str]:
    """Return every flag *retry_flags* can repeat, with each of its options set."""
    every_option = dict.fromkeys(inspect.signature(retry_flags).parameters, True)
    return [flag for flag, _ in retry_flags(**every_option)]


def _options_of(group: str, command: str) -> set[str]:
    root = typer.main.get_command(app)
    assert isinstance(root, TyperGroup)
    command_group = root.commands[group]
    assert isinstance(command_group, TyperGroup)
    return {
        opt
        for param in command_group.commands[command].params
        if isinstance(param, TyperOption)
        for opt in (*param.opts, *param.secondary_opts)
    }


@pytest.mark.parametrize(
    ("command", "retry_flags"),
    [
        ("check", check_retry_flags),
        ("fix", fix_retry_flags),
        ("fix-ios", fix_ios_retry_flags),
        ("refresh", refresh_retry_flags),
        ("detect-faces", detect_faces_retry_flags),
    ],
)
@pytest.mark.parametrize("group", ["album", "albums"])
def test_every_retry_flag_is_an_option_of_the_suggested_command(
    group: str,
    command: str,
    retry_flags: RetryFlagsFn,
) -> None:
    missing = set(_flag_names(retry_flags)) - _options_of(group, command)

    assert not missing, f"'photree {group} {command}' has no {sorted(missing)}"
