# Project-Specific Guidelines

Where photree departs from the shared
[iglootools guidelines](https://github.com/iglootools/common/blob/main/guidelines/README.md),
and the rules it adds. Read it before any change; the
[area conventions](#area-conventions) it links are read when a change reaches
them.

<!-- toc -->
**On this page**

- [Area conventions](#area-conventions)
- [Exceptions](#exceptions)
  - [Defer an import inside the function that needs it, not with `lazy import`](#defer-an-import-inside-the-function-that-needs-it-not-with-lazy-import)
  - [Keep an accumulator for loop-carried state and per-item `try`/`except`](#keep-an-accumulator-for-loop-carried-state-and-per-item-tryexcept)
  - [Select the output format with `--format text|csv`, and write a file with `-o/--output`](#select-the-output-format-with---format-textcsv-and-write-a-file-with--o--output)
- [Rules](#rules)
  - [Read `.photree/*.yaml` through `metadata_io`](#read-photreeyaml-through-metadata_io)
  - [Add each new non-CLI domain subpackage to the CLI-layer contract](#add-each-new-non-cli-domain-subpackage-to-the-cli-layer-contract)
  - [Render errors and output with photree's helpers](#render-errors-and-output-with-photrees-helpers)
- [Tests](#tests)
- [Documentation](#documentation)
<!-- tocstop -->

## Area conventions

Read the linked document in full before changing files under these paths.

| Paths | Conventions |
|-------|-------------|
| `photree/cli/`, `photree/clihelpers/`, `photree/*/cli/`, `photree/albums/batchcli/` — and adding a command anywhere | [cli.md](./guidelines/cli.md) — command hierarchy, options, progress, exit codes, system dependencies, CSV, batch architecture, validation levels |
| `tests/` — and adding a parameter a test needs to control | [testing.md](./guidelines/testing.md) — deciders, the CLI runtime, fakes |
| Introducing a new concept photree manages, such as collections or a future entity type | [adding-a-concept.md](./guidelines/adding-a-concept.md) — the checklist to run first |

## Exceptions

### Defer an import inside the function that needs it, not with `lazy import`

Overrides
[python.md › Import at module level, and defer with `lazy import`](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#import-at-module-level-and-defer-with-lazy-import):
photree defers an import only to break an import cycle or to keep the face ML
stack (`insightface`, `onnxruntime`, `cv2`, `faiss`, `sklearn`, `scipy`, and
the `numpy` beneath them) out of CLI startup, by importing it inside the
function that uses it, or under `TYPE_CHECKING` for an annotation, with a
comment saying which case it is. An in-function import carries
`# noqa: PLC0415` with that reason on its line, and
`tests/unit/test_cli_startup_imports.py` fails if `import photree.cli` loads
any of the ML stack.

**Why:** `lazy import` needs Python 3.15, and photree is held on 3.14 because
onnxruntime publishes no cp315 wheels (the comment at `requires-python` in
`pyproject.toml`). Loading the ML stack at module level adds most of a second
to every CLI invocation.

**Retires when:** photree moves to Python 3.15, once onnxruntime publishes
cp315 wheels: these imports then become `lazy import`s.

### Keep an accumulator for loop-carried state and per-item `try`/`except`

Overrides
[python.md › Build a collection in one expression, not by appending](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#build-a-collection-in-one-expression-not-by-appending),
and its filtering instead of `continue`: photree keeps an accumulator in two
shapes only, each marked with a `# Documented exception (docs/guidelines.md)`
comment:

- **Loop-carried state.** Deduplicating files by inode while stat'ing them
  (`album/stats/scan.py::_stat_files`) needs every inode seen before to decide
  whether the current one is new.
- **Per-item `try`/`except` in a batch.** A loop that records a failure and
  carries on cannot be a comprehension, which has nowhere to put the `except`.

Everywhere else the single-expression form applies.

**Why:** in these shapes the comprehension is harder to read, not easier: the
first has to thread the growing state through every element, and the second
holds the loops that must not swallow errors, where clarity matters most.

**Never retires:** a comprehension can neither carry state between elements
nor catch an exception per item.

### Select the output format with `--format text|csv`, and write a file with `-o/--output`

Overrides
[general.md › Select the output format with `-o/--output`, and write a file with `-f/--file`](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#select-the-output-format-with--o--output-and-write-a-file-with--f--file):
photree's listing commands select their format with `--format`, `text` (the
default) or `csv`, and write the output to a file with `-o/--output FILE`.

**Why:** the flags predate the shared rule, and renaming them breaks every
script and alias that passes them, which only a major release may do.

**Retires when:** photree's next major release, which moves the format to
`-o/--output` (`human`, the default, and `csv`) and the file to `-f/--file`.

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

A new subpackage of `album/`, `albums/`, `collection/`, `collections/`,
`gallery/`, `check/` or `demo/` that is not CLI code goes on the source list
of the "Domain code does not depend on the CLI layer" contract in
`pyproject.toml`. A new top-level package with a `cli/` subpackage goes on the
"Domain package roots" contract too.

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

## Tests

Every new behaviour gets a test, as
[general.md › Give every new behaviour a test](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#give-every-new-behaviour-a-test)
asks: [testing.md](./guidelines/testing.md) says which suite it goes in, and
holds photree's deciders, CLI runtime and fakes.

The patches the
[patching rule](https://github.com/iglootools/common/blob/main/guidelines/coding/general.md#patch-only-in-the-three-documented-cases-and-list-each-one)
allows, enforced as
[python-tooling.md › Enforce the patching rule](https://github.com/iglootools/common/blob/main/guidelines/project-setup/python-tooling.md#enforce-the-patching-rule)
sets up:

| File | What it replaces | Category | Why | Retires when |
|---|---|---|---|---|
| `tests/integration_fs/album/importer/test_preflight.py` | `PATH`, emptied | (c) | The test asserts that `run_preflight` does not read `PATH`, since its caller owns the probing: it takes process-global state away from the developer's machine to show the outcome does not depend on it. | Never, while the test exists: changing the process's `PATH` is the only way to show that a function ignores it. |

## Documentation

Before calling a change done, update the documents its kind of change reaches:

| Change | Update |
|---|---|
| CLI command, option or help text | `mise run clidocs` (cli-reference.md); usage.md for the workflow; features.md and the README summary for a new capability |
| Config field, default or validation rule | the field's `metadata` in config/protocol.py, then `mise run configdocs` (config-reference.md's field tables; the prose around them, such as the Errors table, by hand), config-examples/config.toml, usage.md "Configuration" |
| Concept, entity, invariant, naming convention or ID format | domain.md |
| On-disk layout, `.photree/*.yaml` format, refresh/import/export algorithm, external command invoked | internals.md |
| New package or import edge | the contracts and architecture.md "Layering"; `mise run depgraph` |
| System requirement (exiftool, sips, …) | installation.md (the probe itself goes in `photree check system`) |
| mise task or CI workflow | building-and-testing.md |
| Toolchain, editor or Claude Code setup | setup-development-environment.md |
| Release or publish pipeline, trusted publisher | releasing-and-publishing.md |
| GitHub repository setting | building-and-testing.md "GitHub Config" |
| Major release | new scenarios in demo/demo.sh (see [releasing-and-publishing.md › Release a Version](./releasing-and-publishing.md#release-a-version)) |
| Renaming or moving a document | every file that points at it, as [layout.md › Write the documents the project's shape calls for, one name per role](https://github.com/iglootools/common/blob/main/guidelines/documentation/layout.md#write-the-documents-the-projects-shape-calls-for-one-name-per-role) lists |
