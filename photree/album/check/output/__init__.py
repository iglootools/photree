"""
Output formatting for album checks, one module per audience.

One album's check (:mod:`.album`), its troubleshooting
(:mod:`.troubleshoot`), a check over many albums (:mod:`.batch`), and the
per-file failures of a refresh of derived data (:mod:`.derived`).

Formatters return unindented lines; nested detail lines are indented relative
to their heading with :func:`~photree.common.formatting.indent`, and the call
site decides how deep the whole block sits.

Formatters return Rich markup: every user-derived value (album and media
source names, paths, filenames, issue messages) is escaped with
:func:`~photree.common.formatting.markup_escape` here, so callers print the
result with markup enabled and must not escape it again.
"""
