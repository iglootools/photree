"""Foundation layer — the small set of types every other package builds on.

Depends only on ``common``, ``dates`` and third-party libraries, never on a
domain package, so album, collection, gallery, config and the CLI helpers can
all import it without creating a cycle.

- ``model`` — :class:`PhotreeModel`, the base for ``.photree/*.yaml`` models
- ``metadata_io`` — YAML read/validate/write and :class:`InvalidMetadataError`
- ``layout`` — fixed directory and sentinel names
- ``linking`` — :class:`LinkMode`
- ``share_layout`` — export layout enums
- ``gallery_metadata`` — ``gallery.yaml`` model, I/O and gallery resolution
"""
