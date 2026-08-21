# Installation

## Supported Platforms

photree currently requires **macOS** due to its dependency on `sips` (Scriptable
Image Processing System) for HEIC/DNG-to-JPEG conversion and Image Capture for
iOS imports. Linux support could be added in the future for non-iOS albums and
imports that do not rely on these macOS-specific tools.

## System Requirements

- macOS
- Python 3.12+
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

The `check` commands are the exception: they degrade gracefully, reporting that
EXIF checks were skipped rather than failing.

## Install with uv

[uv](https://docs.astral.sh/uv/) installs CLI tools in isolated environments, keeping your system
Python clean:

```bash
uv tool install photree
```

To upgrade to the latest version:

```bash
uv tool upgrade photree
```

## Install with pipx

[pipx](https://pipx.pypa.io/) does the same thing, and is a fine alternative if you already have it:

```bash
pipx install photree
pipx upgrade photree
```

## Shell Completion

photree supports tab completion for Bash, Zsh, Fish, and PowerShell.

Install completion for your current shell:

```bash
photree --install-completion
```

Or target a specific shell:

```bash
photree --install-completion bash
photree --install-completion zsh
photree --install-completion fish
photree --install-completion powershell
```

To preview the completion script without installing it:

```bash
photree --show-completion
```

Restart your shell (or source the relevant config file) for completions to take effect.
