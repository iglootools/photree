# Adding a Concept

The checklist to run when introducing a new concept that photree manages, such
as collections or a future entity type. Read it before adding one.

- [ ] **Metadata model**: `.photree/<entity>.yaml` with Pydantic model,
      load/save I/O
- [ ] **ID system**: generate/format/parse functions with `<type>_<base58>`
      external form
- [ ] **Naming convention**: parser, reconstructor, validation (reuse
  `photree/dates.py` for any date component rather than re-deriving ranges)
- [ ] **Discovery**: `is_<entity>`, `discover_<entities>` functions
- [ ] **CLI commands at all three levels**: single (`<entity> <op>`), batch
      (`<entities> <op>`), gallery (`gallery <op>`), following
      [cli.md](./cli.md)
- [ ] **Standard operations**: init, show, check, import, metadata set, list
      (with CSV output), stats
- [ ] **Stats**: disk usage and content statistics at all three levels (single,
      batch, gallery)
- [ ] **Gallery integration**: gallery check includes the new entity, gallery
      refresh manages derived state
- [ ] **Progress indicators**: spinners for single operations, BatchProgressBar
      for batch, StageProgressBar for multi-stage
- [ ] **Validation**: light check (naming) as gate for refresh/import, full
      check for check commands
- [ ] **Documentation**: domain.md (concepts), internals.md (design), usage.md
      (workflow), cli-reference.md (regenerate), architecture.md (depgraph)
