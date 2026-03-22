# Project-Specific Guidelines

A set of [implementation checklists](./implementation-checklists.md) serve as a reminder for things to check when implementing new features or making changes to the codebase.

For general coding, Python, and tooling guidelines, see the [common guidelines](https://github.com/iglootools/common-guidelines).

## Coding
- **Naming Conventions**
  - `kebab-case` for CLI commands
- **CLI**
  - Use `typer` for CLI implementation (argument parsing, formatting, etc.)
  - Progress bars labels that log an item for each step: 
    - "Checking..." during the operation
    - "\u2713 check" for a successfully completed step (see `CHECK`)
    - "\u2717 check" for a failed step (see `CROSS`)
- **Printing/Logging**
  - Print/Log relative paths when paths relative to the current working directory, using `display_path`