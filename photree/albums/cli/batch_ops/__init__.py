"""Batch CLI wrappers, one module per operation.

Each ``run_batch_*`` function creates progress bars, calls the corresponding
command handler, displays results, and raises ``typer.Exit``. Both ``albums``
and ``gallery`` commands delegate here.

Import the specific module rather than this package: these operations have
very different dependencies — refresh pulls in sips and exiftool, list pulls
in neither — and a single module holding all of them made every command look
like it depended on everything.

Album resolution helpers live in :mod:`photree.albums.cli.ops`.
"""
