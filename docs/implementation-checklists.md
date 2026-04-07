# Implementation Checklists

These checklists serve as a reminder for things to check when implementing new features or making changes to the codebase.

## Guidelines
- Follow the [common guidelines](https://github.com/iglootools/common-guidelines) and [project-specific guidelines](./guidelines.md)

## Build and CI
- Keep Github workflows and mise tasks in sync with each other

## Documentation
- Keep the documentation in sync with the codebase.

## Tests
- Ensure that all new functionality is covered by tests.

## New Concepts (e.g., collections, future entity types)

When introducing a new concept that is managed by photree:

- [ ] **Metadata model**: `.photree/<entity>.yaml` with Pydantic model, load/save I/O
- [ ] **ID system**: generate/format/parse functions with `<type>_<base58>` external form
- [ ] **Naming convention**: parser, reconstructor, validation
- [ ] **Discovery**: `is_<entity>`, `discover_<entities>` functions
- [ ] **CLI commands at all three levels**: single (`<entity> <op>`), batch (`<entities> <op>`), gallery (`gallery <op>`)
- [ ] **Standard operations**: init, show, check, import, metadata set, list (with CSV output), stats
- [ ] **Stats**: disk usage and content statistics at all three levels (single, batch, gallery)
- [ ] **Gallery integration**: gallery check includes the new entity, gallery refresh manages derived state
- [ ] **Progress indicators**: spinners for single operations, BatchProgressBar for batch, StageProgressBar for multi-stage
- [ ] **Validation**: light check (naming) as gate for refresh/import, full check for check commands
- [ ] **Documentation**: internals.md (design), usage.md (workflow), cli-reference.md (regenerate), architecture.md (depgraph)
