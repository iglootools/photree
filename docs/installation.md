# Installation

## Supported Platforms

photree currently requires **macOS** due to its dependency on `sips` (Scriptable
Image Processing System) for HEIC/DNG-to-JPEG conversion and Image Capture for
iOS imports. Linux support could be added in the future for non-iOS albums and
imports that do not rely on these macOS-specific tools.

## System Requirements

- macOS
- Python 3.12+
- [exiftool](https://exiftool.org/) (optional, for EXIF timestamp validation)

### exiftool

photree uses exiftool to validate that media file timestamps match album dates.
If exiftool is not installed, EXIF checks are skipped gracefully.

**macOS** (Homebrew):

```bash
brew install exiftool
```

Verify the installation:

```bash
exiftool -ver
```

## Install with pipx

[pipx](https://pipx.pypa.io/) installs CLI tools in isolated environments, keeping your system Python clean:

```bash
pipx install photree
```

To upgrade to the latest version:

```bash
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
