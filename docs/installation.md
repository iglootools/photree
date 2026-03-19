# Installation

## System Requirements

- Python 3.12+

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
