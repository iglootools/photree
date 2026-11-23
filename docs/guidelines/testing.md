# Testing

How photree's tests get what they need without patching: its deciders, the CLI
runtime, the shared fakes and factories. Read it before writing a test, or
adding a parameter a test needs to control. The patching exceptions are listed
in
[guidelines.md › Tests](../guidelines.md#tests).

- **Deciders**, such as `import_problems` (album import), `import_failure_of`
  and `import_all_failed` (gallery import), tested with real result objects.
- **The CLI runtime** (`photree/clihelpers/runtime.py`): everything a command
  reads from the machine or the process: `which` (installed binaries), `cwd`,
  `home`, `environ`, the platform config directories, and `cpu_count`;
  `load_config` loads the config file from them. Commands read them with
  `runtime_of(ctx)` and pass the values on; `main()` hands the real one to the
  app, and tests run the CLI with `invoke_cli(args, runtime=...)`, which
  always passes a fake (`ALL_DEPS_RUNTIME` by default); ruff bans
  `CliRunner` everywhere else, so no test reaches the developer's `PATH`,
  home or config file. Below the
  commands, nothing reads the environment: CLI helpers take `cwd` (or the
  runtime) as a parameter, and a domain function that would otherwise read it
  takes a keyword parameter defaulting to the real value
  (`which=shutil.which`, `load=load_config`, `cpu_count=os.cpu_count`) that
  the command overrides. `cwd` stays the process's working directory, since
  the OS resolves relative arguments against it: tests change it with the
  `chdir` fixture. Album operations a command runs are album-level ports, on
  `AlbumRuntime` (`photree/album/cli/runtime.py`), since `clihelpers` sits
  below `album`: `album_runtime_of(ctx)` widens the shared runtime with the
  real ones.
- **Fakes**, in `tests/fakes.py`: `fake_runtime(*present)` (only *present*
  binaries installed, a home that does not exist, an empty environment, no
  config file), `ALL_DEPS_RUNTIME`, `invoke_cli`, `fake_which`, and
  `fake_album_runtime(*present, run_import=..., refresh=...)`.
- **Factories**, in `tests/testkit.py`: the files, albums and galleries a
  test sets up (`write_file`, `write_files`, `make_album`, `make_gallery`,
  `make_gallery_album`, …). Add a parameter to one rather than copying it
  into a test module; a module keeps its own helper only for a setup no other
  test shares.
