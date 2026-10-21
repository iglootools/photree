# Project-Specific Guidelines

A set of [implementation checklists](#implementation-checklists) serve as a reminder for things to check when implementing new features or making changes to the codebase.

For general coding, Python, and tooling guidelines, see the [common guidelines](https://github.com/iglootools/common).

## Coding
- **Naming Conventions**
  - `kebab-case` for CLI commands
- **Printing/Logging**
  - Print/Log relative paths when paths relative to the current working directory, using `display_path`
- **Imports**
  - Import at module level. A function-level import is reserved for two cases,
    each with a comment saying which: breaking an import cycle, or deferring a
    heavy ML dependency.
  - The face ML stack (`insightface`, `onnxruntime`, `cv2`, `faiss`, `sklearn`,
    `scipy`) is imported only inside the functions that use it, or under
    `TYPE_CHECKING` for annotations: loading it at module level adds most of a
    second to every CLI invocation. `tests/unit/test_cli_startup_imports.py`
    fails if `import photree.cli` loads any of them.
- **Module boundaries**
  - The import-linter contracts in `pyproject.toml` (`[tool.importlinter]`) are
    the source of truth for which package may import which;
    [architecture.md — Layering](./architecture.md#layering)
    explains them, and `mise run boundaries-check` (part of `mise run check`)
    enforces them.
  - When a change needs a new edge, decide whether it belongs: move the code
    to the layer that may own it rather than bending the contract. If the
    architecture itself changes, update the contracts deliberately, in the
    same commit as the restructuring, together with the Layering
    section. Do not add an `ignore_imports` entry to make an edge pass; if one
    is truly unavoidable, comment why next to it.
  - A new subpackage of `album/`, `albums/`, `collection/` or `gallery/` that
    is not CLI code must be added to the source list of the "Domain code does
    not depend on the CLI layer" contract.

### Documented exception: mutable accumulators in scan/group loops

The [common Python guidelines](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md)
ask for lists built as a single expression rather than `errors = []` plus
`append`, and for `continue` to be replaced by filtering. photree keeps the
accumulator form in two specific shapes, because the comprehension is harder
to read, not easier:

- **Loop-carried state.** Grouping a sorted sequence into contiguous runs
  (`collection/refresh/series.py::_group_contiguous_series`) needs the previous
  element to decide where the current group ends. Expressed as a
  comprehension it requires `itertools.groupby` plus a key function that
  closes over mutable state — strictly more machinery for the same result.
- **Per-item try/except in a batch.** A loop that must record a failure and
  carry on cannot be a comprehension, because a comprehension has nowhere to
  put the `except`. These loops are exactly the ones that must not swallow
  errors, so clarity there matters more than form.

Everywhere else, prefer the single-expression form: building a result from
independent branches, filtering, mapping, and conditional inclusion all read
better as `[*(...), *(...)]` and comprehensions, and that is the majority of
list construction in this codebase.

**This exception retires** if a case appears where the accumulator hides a
bug the comprehension would have prevented — the reason it is written down is
so that trade-off can be re-examined rather than assumed.

### Errors and Output

The shared rules apply as written: *Presentation at the Edges* and structured
errors under *Testability* in the common
[general.md](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md),
and *Data Classes* (plain exception classes), *Errors* and *Console Output*
in [python.md](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md).
photree's helpers for them:

- **Rendering errors**: formatters in each package's `output.py` (or the CLI
  command) turn kinds and fields into messages, with paths through
  `common.fs.display_path`.
- **Indentation**: `common.formatting.indent` (`INDENT` is the unit).
- **Escaping user text in Rich markup**: `common.formatting.markup_escape`.
  Formatters that embed user text escape it themselves and are printed with
  markup on; progress bars (`clihelpers/progress.py`) escape the labels they
  are given, so callers pass plain text.
- **Corrupt metadata is never "absent".** Read `.photree/*.yaml` through
  `foundation.metadata_io.load_yaml_mapping` / `validate_metadata`: `None` means the file
  does not exist, and anything present but unusable raises
  `InvalidMetadataError`. Treating corruption as absence is how a truncated
  `album.yaml` used to get a fresh ID and orphan every reference to the old
  one.

## Area conventions

Conventions for one part of the code live in their own document, so they are read when a
change reaches that part rather than loaded into every session. Read the linked document in
full before changing files under these paths.

| Paths | Conventions |
|-------|-------------|
| `photree/cli/`, `photree/clihelpers/`, `photree/*/cli/`, `photree/albums/batchcli/` — and adding a command anywhere | [cli-conventions.md](./cli-conventions.md) — command hierarchy, standard operations, options, progress, exit codes, system dependencies, CSV, batch architecture, validation levels |

## Implementation Checklists

These checklists serve as a reminder for things to check when implementing new features or making changes to the codebase.

### Build and CI
- Keep Github workflows and mise tasks in sync with each other

### Documentation
- Keep the documentation in sync with the codebase.

### Tests
- Ensure that all new functionality is covered by tests.

### New Concepts (e.g., collections, future entity types)

When introducing a new concept that is managed by photree:

- [ ] **Metadata model**: `.photree/<entity>.yaml` with Pydantic model, load/save I/O
- [ ] **ID system**: generate/format/parse functions with `<type>_<base58>` external form
- [ ] **Naming convention**: parser, reconstructor, validation (reuse
  `photree/dates.py` for any date component rather than re-deriving ranges)
- [ ] **Discovery**: `is_<entity>`, `discover_<entities>` functions
- [ ] **CLI commands at all three levels**: single (`<entity> <op>`), batch (`<entities> <op>`), gallery (`gallery <op>`), following [cli-conventions.md](./cli-conventions.md)
- [ ] **Standard operations**: init, show, check, import, metadata set, list (with CSV output), stats
- [ ] **Stats**: disk usage and content statistics at all three levels (single, batch, gallery)
- [ ] **Gallery integration**: gallery check includes the new entity, gallery refresh manages derived state
- [ ] **Progress indicators**: spinners for single operations, BatchProgressBar for batch, StageProgressBar for multi-stage
- [ ] **Validation**: light check (naming) as gate for refresh/import, full check for check commands
- [ ] **Documentation**: domain.md (concepts), internals.md (design), usage.md (workflow), cli-reference.md (regenerate), architecture.md (depgraph)
