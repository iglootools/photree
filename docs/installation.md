# Installation

<!-- toc -->
**On this page**

- [Supported Platforms](#supported-platforms)
- [System Requirements](#system-requirements)
  - [exiftool](#exiftool)
  - [Verifying prerequisites](#verifying-prerequisites)
  - [When a dependency is missing](#when-a-dependency-is-missing)
- [Install with uv](#install-with-uv)
- [Install with pipx](#install-with-pipx)
- [Shell Completion](#shell-completion)
<!-- tocstop -->

## Supported Platforms

photree currently requires **macOS** due to its dependency on `sips` (Scriptable
Image Processing System) for HEIC/DNG-to-JPEG conversion and Image Capture for
iOS imports. Linux support could be added in the future for non-iOS albums and
imports that do not rely on these macOS-specific tools.

## System Requirements

- macOS
- Python 3.14
- `sips` (ships with macOS)
- [exiftool](https://exiftool.org/)

### exiftool

photree uses exiftool to read and write EXIF timestamps: validating that media
file timestamps match album dates, populating the EXIF timestamp cache during
a refresh, and resolving collection selections.

**macOS** (Homebrew):

```bash
brew install exiftool
```

Verify the installation:

```bash
exiftool -ver
```

### Verifying prerequisites

```bash
photree check system
```

It prints one line per external binary and exits 1 if any is missing.

### When a dependency is missing

Commands that need an external binary probe for it **before** doing any work
and abort the whole run if it is absent — a missing binary is a property of the
machine, not of the album being processed, so a batch fails up front rather
than once per album, halfway through. See
[Internals — System Dependencies](internals.md#system-dependencies) for which
command requires what.

The `check` commands only partly follow this. Without `exiftool` they report
that the EXIF checks were skipped rather than failing. `albums check` and
`gallery check` still require `sips`, and `exiftool` too with
`--refresh-exif-cache`, and abort without them; `album check` reports a missing
`sips` as a failed check instead. The
[Internals table](internals.md#system-dependencies) lists each case.

## Install with uv

[uv](https://docs.astral.sh/uv/) installs CLI tools in isolated environments,
keeping your system Python clean:

```bash
uv tool install photree
```

photree requires Python 3.14. If no 3.14 interpreter is installed, uv downloads
a managed one for the tool's environment, so this works regardless of your
system Python.

To upgrade to the latest version:

```bash
uv tool upgrade photree
```

Upgrading from 0.12.0 or earlier, reinstall instead:

```bash
uv tool install --reinstall photree
```

Those versions installed OpenCV's headless build alongside the full one that
insightface requires. Both write the same `cv2` package, so the upgrade's
removal of the headless build deletes files the full build still needs, and
face commands then fail with `No module named 'cv2'`. `pipx upgrade` keeps
the old build installed and is not affected.

## Install with pipx

[pipx](https://pipx.pypa.io/) does the same thing, and is a fine alternative if
you already have it. Unlike uv, pipx does not fetch an interpreter by default:
it uses the Python it was installed with, so point it at a 3.14 interpreter
explicitly unless that is already 3.14:

```bash
pipx install --python python3.14 photree
pipx upgrade photree
```

## Shell Completion

photree supports tab completion for Bash, Zsh, Fish, and PowerShell.

Install completion for your current shell:

```bash
photree --install-completion
```

The option takes no argument: it detects the shell it runs in, so to set up
completion for another shell, run it from that shell.

To preview the completion script without installing it:

```bash
photree --show-completion
```

Restart your shell (or source the relevant config file) for completions to take
effect.
