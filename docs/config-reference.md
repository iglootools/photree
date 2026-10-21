# Configuration Reference

Every field of photree's optional configuration file: where it is looked up, which commands read
it, each field's type, default and allowed values, and how invalid values are reported. For the
workflows these settings serve, see [usage.md](usage.md#configuration); for every command-line
option, see [cli-reference.md](cli-reference.md). A complete example is in
[config-examples/config.toml](config-examples/config.toml).

The file is TOML. Everything in it is optional, and every field has a command-line flag that
overrides it, so photree runs without one.

## Location

The first of these that exists is used:

1. the file passed with `--config <path>` — an error if it does not exist
2. `$XDG_CONFIG_HOME/photree/config.toml` (`~/.config/photree/config.toml` when
   `XDG_CONFIG_HOME` is unset)
3. the platform user config directory (macOS: `~/Library/Application Support/photree/config.toml`;
   on Linux the same path as 2)
4. the platform site config directory (macOS: `/Library/Application Support/photree/config.toml`)

## Which commands read it

| Section | Read by | Precedence |
|---|---|---|
| `[importer]` | `album import`, `album import-check`, `albums import`, `albums import-check` | `--source` > `image-capture-dir` > default |
| `[exporter.profiles.<name>]` | `album export`, `albums export`, `gallery export`, when `--profile <name>` is given | each flag (`--share-dir`, `--share-layout`, `--album-layout`, `--link-mode`) > profile value > default |

A searched-for file is read only when a command needs a value from it: an import given
`--source`, or an export given no `--profile`, does not read it, so a broken file elsewhere does
not block them. A file passed with `--config` is always read and validated, so a path typed by
hand is never silently ignored.

## Fields

Path values expand a leading `~` to the home directory. Keys photree does not know are ignored.

### `[importer]`

| Key | Type | Default | Meaning |
|---|---|---|---|
| `image-capture-dir` | string (path) | `~/Pictures/iPhone` | Directory where macOS Image Capture saves the files it imports from the phone. macOS names it after the device, with a typographic apostrophe (`’`), not an ASCII `'`. |

### `[exporter.profiles.<name>]`

One table per named export profile, selected with `--profile <name>`.

| Key | Type | Default | Allowed values |
|---|---|---|---|
| `share-dir` | string (path), **required** | — | Base directory to export into. |
| `share-layout` | string | `flat` | `flat`, `albums` (by year), `by-month` |
| `album-layout` | string | `browsable-jpg` | `browsable-jpg`, `browsable`, `all`, `archive` |
| `link-mode` | string | `hardlink` | `copy`, `hardlink`, `symlink` |

What each layout and link mode produces is described under `album export` in
[cli-reference.md](cli-reference.md#photree-album-export).

Two rules apply to the export settings once flags and the profile are combined, not to the file
on its own, and fail the export with exit code 1:

- `share-layout = "albums"` requires `album-layout = "all"`.
- `share-dir` must contain a `.photree-share` sentinel file, so an export cannot write into a
  directory that was not prepared for it.

## Errors

A configuration error stops the command with exit code 2, naming the key and profile at fault
(or the file, when it is missing or does not parse):

| Error | Cause |
|---|---|
| file not found | `--config` names a file that does not exist |
| invalid TOML | the file does not parse |
| missing key | a profile has no `share-dir` |
| invalid type | a section is not a table, or a value is not a string |
| invalid value | `share-layout`, `album-layout` or `link-mode` is not one of the allowed values |
