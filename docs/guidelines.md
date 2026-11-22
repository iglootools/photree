# Project-Specific Guidelines

Where photree departs from the shared
[iglootools guidelines](https://github.com/iglootools/common/blob/main/guidelines/README.md),
and the rules it adds. Read it before any change; the
[area conventions](#area-conventions) and the
[task checklists](#adding-a-concept) it links are read when a change reaches
them.

<!-- toc -->
**On this page**

- [Deviations](#deviations)
  - [Defer an import inside the function that needs it, not with `lazy import`](#defer-an-import-inside-the-function-that-needs-it-not-with-lazy-import)
  - [Keep an accumulator for loop-carried state and per-item `try`/`except`](#keep-an-accumulator-for-loop-carried-state-and-per-item-tryexcept)
- [Rules](#rules)
  - [Read `.photree/*.yaml` through `metadata_io`](#read-photreeyaml-through-metadata_io)
  - [Add each new non-CLI domain subpackage to the CLI-layer contract](#add-each-new-non-cli-domain-subpackage-to-the-cli-layer-contract)
  - [Render errors and output with photree's helpers](#render-errors-and-output-with-photrees-helpers)
  - [Cover all new functionality with tests](#cover-all-new-functionality-with-tests)
- [Tests](#tests)
- [Area conventions](#area-conventions)
- [Adding a concept](#adding-a-concept)
- [Documentation](#documentation)
<!-- tocstop -->

## Deviations

### Defer an import inside the function that needs it, not with `lazy import`

Documented exception to
[python.md › Import at module level, and defer with `lazy import`](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#import-at-module-level-and-defer-with-lazy-import).
Defer an import only to break an import cycle or to keep the face ML stack
(`insightface`, `onnxruntime`, `cv2`, `faiss`, `sklearn`, `scipy`) out
of CLI startup: import it inside the function that uses it, or under
`TYPE_CHECKING` for an annotation, with a comment saying which case it is. An
in-function import carries `# noqa: PLC0415` with that reason on its line.

**Why:** `lazy import` needs Python 3.15, and photree is held on 3.14 because
onnxruntime publishes no cp315 wheels (the comment at `requires-python` in
`pyproject.toml`). Loading the ML stack at module level adds most of a second
to every CLI invocation.

- `tests/unit/test_cli_startup_imports.py` fails if `import photree.cli`
  loads any of the ML stack.
- **Retires when** photree moves to Python 3.15, once onnxruntime publishes
  cp315 wheels: these imports then become `lazy import`s.

### Keep an accumulator for loop-carried state and per-item `try`/`except`

Documented exception to
[python.md › Build a collection in one expression, not by appending](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#build-a-collection-in-one-expression-not-by-appending),
and to its filtering instead of `continue`, in two shapes only, each marked
with a `# Documented exception (docs/guidelines.md)` comment:

- **Loop-carried state.** Grouping a sorted sequence into contiguous runs
  (`collection/refresh/series.py::_group_contiguous_series`) needs the
  previous element to decide where the current group ends.
- **Per-item `try`/`except` in a batch.** A loop that records a failure and
  carries on cannot be a comprehension, which has nowhere to put the `except`.

**Why:** in these shapes the comprehension is harder to read, not easier: the
first needs `itertools.groupby` with a key function closing over mutable
state, and the second holds the loops that must not swallow errors, where
clarity matters most. Everywhere else the single-expression form applies.

This is structural rather than temporary: no condition retires it while a
comprehension can neither carry state between elements nor catch an exception
per item.

## Rules

### Read `.photree/*.yaml` through `metadata_io`

Read metadata through `foundation.metadata_io.load_yaml_mapping` /
`validate_metadata`: `None` means the file does not exist, and anything
present but unusable raises `InvalidMetadataError`.

**Why:** it is photree's form of
[general.md › Treat a file that exists but cannot be read as an error, never as absent](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#treat-a-file-that-exists-but-cannot-be-read-as-an-error-never-as-absent):
a truncated `album.yaml` read as absent gets a fresh ID, orphaning every
reference to the old one.

### Add each new non-CLI domain subpackage to the CLI-layer contract

A new subpackage of `album/`, `albums/`, `collection/` or `gallery/` that
is not CLI code goes on the source list of the "Domain code does not depend on
the CLI layer" contract in `pyproject.toml`.

**Why:** the contract enumerates its sources, so a subpackage left off it is
unchecked and the run still passes
([python-tooling.md › Prefer contracts whose coverage follows the code](https://github.com/iglootools/common/blob/main/guidelines/project-setup/python-tooling.md#prefer-contracts-whose-coverage-follows-the-code)).
What each contract protects is in
[architecture.md › Layering](./architecture.md#layering).

### Render errors and output with photree's helpers

The shared rules on presentation, errors and console output apply as written.
photree's helpers for them:

- **Rendering errors**: formatters in each package's `output.py` (or the CLI
  command) turn kinds and fields into messages, with paths through
  `common.fs.display_path`.
- **Indentation**: `common.formatting.indent` (`INDENT` is the unit).
- **Escaping user text in Rich markup**: `common.formatting.markup_escape`.
  Formatters that embed user text escape it themselves and are printed with
  markup on; progress bars (`clihelpers/progress.py`) escape the labels they
  are given, so callers pass plain text.

### Cover all new functionality with tests

Each new behaviour gets a test, written without patching as
[general.md › Testability](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#testability)
describes; photree's deciders, CLI runtime and fakes are in
[testing.md](./guidelines/testing.md).

## Tests

The patches the
[patching rule](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#patch-only-in-the-three-documented-cases-and-list-each-one)
allows, enforced as
[python-tooling.md › Enforce the patching rule](https://github.com/iglootools/common/blob/main/guidelines/project-setup/python-tooling.md#enforce-the-patching-rule)
sets up:

| File | What is replaced | Category | Why, and when to retire it |
|---|---|---|---|
| `tests/integration_fs/album/importer/test_preflight.py` | `PATH`, emptied | (c) | The test asserts that `run_preflight` does not read `PATH`, since its caller owns the probing. Changing the process's `PATH` is the only way to show that. |

## Area conventions

Read the linked document in full before changing files under these paths.

| Paths | Conventions |
|-------|-------------|
| `photree/cli/`, `photree/clihelpers/`, `photree/*/cli/`, `photree/albums/batchcli/` — and adding a command anywhere | [cli.md](./guidelines/cli.md) — command hierarchy, options, progress, exit codes, system dependencies, CSV, batch architecture, validation levels |
| `tests/` — and adding a parameter a test needs to control | [testing.md](./guidelines/testing.md) — deciders, the CLI runtime, fakes |

## Adding a concept

Run the checklist in [adding-a-concept.md](./guidelines/adding-a-concept.md)
before introducing a new concept that photree manages, such as collections or a
future entity type.

## Documentation

Before calling a change done, update the documents its kind of change reaches:

| Change | Update |
|---|---|
| CLI command, option or help text | `mise run clidocs` (cli-reference.md); usage.md for the workflow; features.md and the README summary for a new capability |
| Config field, default or validation rule | config-reference.md (hand-written: no generator), config-examples/config.toml, usage.md "Configuration" |
| Concept, entity, invariant, naming convention or ID format | domain.md |
| On-disk layout, `.photree/*.yaml` format, refresh/import/export algorithm, external command invoked | internals.md |
| New package or import edge | the contracts and architecture.md "Layering"; `mise run depgraph` |
| System requirement (exiftool, sips, …) | installation.md (the probe itself goes in `photree check system`) |
| mise task or CI workflow | building-and-testing.md |
| Toolchain, editor or Claude Code setup | setup-development-environment.md |
| Release or publish pipeline, trusted publisher | releasing-and-publishing.md |
| GitHub repository setting | building-and-testing.md "GitHub Config" |
| Major release | new scenarios in demo/demo.sh (see the Release Process) |
| Renaming or moving a document | every reference to it: `git grep` the old name, including the CONTRIBUTING.md line and the README's absolute URLs |
