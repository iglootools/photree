"""Batch CLI layer shared by the ``albums`` and ``gallery`` command groups.

Each ``run_batch_*`` function creates progress bars, calls the corresponding
command handler (``albums.cmd_handler``), displays results, and raises
``typer.Exit``. ``resolution`` turns ``--dir``/``--album-dir`` options into an
album list. Both ``albums`` and ``gallery`` commands delegate here, which is
why it is a sibling of ``albums.cli`` rather than part of it: the ``gallery``
CLI depends on this shared layer, never on the ``albums`` command group. It
stays inside ``albums`` because it presents ``albums.cmd_handler`` results
and builds on ``albums.index``; a top-level package would make ``albums``
and it depend on each other.

Import the specific module rather than this package: these operations have
very different dependencies — refresh pulls in sips and exiftool, list pulls
in neither — and a single module holding all of them made every command look
like it depended on everything.
"""
