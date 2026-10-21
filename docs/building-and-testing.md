# Building and Testing

Run automated tests and checks:
```bash
# mise tasks
mise run check              # Run all checks: format-check + lint + type-check + boundaries-check + lock-check + lock-check-uv + clidocs-check + depgraph-check
mise run check-all          # Run all checks: regular checks + all tests

mise run test-all           # All tests (unit + integration)
mise run test-unit          # Unit tests
mise run test-integration-fs # Filesystem integration tests (full workflow)

mise run format             # ruff format (rewrites files)
mise run format-check       # ruff format --check (verifies only; what check runs)
mise run lint               # ruff check
mise run type-check         # pyright
mise run boundaries-check   # import-linter (module boundary contracts in pyproject.toml — see architecture.md)

mise run clidocs            # Regenerate CLI reference in docs/cli-reference.md
mise run clidocs-check      # Check that CLI reference is up to date
mise run depgraph           # Regenerate Module Overview in docs/architecture.md
mise run depgraph-check     # Check that Module Overview is up to date

mise run install            # Sync .venv with uv.lock (rarely needed by hand — see below)
mise run reinstall          # Delete .venv and sync from scratch
mise run lock-check-uv      # Check uv.lock is consistent with pyproject.toml

# Running tools directly
uv run pytest tests/ -v                         # All tests
uv run ruff format .                            # formatting
uv run ruff check photree/ tests/               # linting
uv run pyright photree/                         # type-checking
uv run lint-imports                             # module boundaries
uv run pytest tests/test_cli.py::TestVersionCommand::test_version_flag -v   # run a single test
```

`uv run` is the prefix to use rather than a bare `pytest`/`ruff`. It resolves the
environment from the project root, so it is correct regardless of what is on `PATH` — a bare
command in a shell that has *another* project's `.venv` active silently runs that project's
copy of the tool. The mise tasks above use `uv run --no-sync` for the same reason.

Dependencies install themselves: `[deps.uv]` in `mise.toml` runs `uv sync` before any
`mise run` whenever `uv.lock` or `pyproject.toml` has changed, or `.venv` has gone missing.
So `mise run install` is seldom needed explicitly, and `mise run reinstall` is for the case
that automatic check cannot see — a `.venv` that is *dirty* rather than *stale*, e.g. after
a manual `uv pip install`. Add or remove dependencies with `uv add` / `uv remove`.

## Python version

photree runs on one Python version, everywhere: the `python` pin in `mise.toml` is the
local development version, the version CI tests (the `test` workflow has no version
matrix), and the only version `requires-python` in `pyproject.toml` accepts. There is no
older floor to stay compatible with, so code may use any feature of that version; ruff's
`target-version` and pyright's `pythonVersion` are set to match.

The [Python Version Policy](https://github.com/iglootools/common/blob/main/guidelines/coding/python.md#python-version-policy)
is to target the latest stable CPython that every dependency ships wheels for.
**Documented exception:** photree is on 3.14 rather than 3.15 because onnxruntime
(pulled in by the face-detection stack) publishes no cp315 wheels, so `uv lock` cannot
resolve on 3.15. Move to 3.15 when it does — check
[onnxruntime's files on PyPI](https://pypi.org/project/onnxruntime/#files) for `cp315`
wheels. Moving means changing, together: `[tools] python` in `mise.toml` (then
`mise lock`), `requires-python`, ruff `target-version` and pyright `pythonVersion` in
`pyproject.toml` (then `uv lock`).

The `check-links` workflow runs a link checker against the documentation to catch broken links.
It is scheduled to run weekly, but can also be triggered manually using `gh workflow run check-links.yml`.

## Release Process
- Trigger the `release` workflow: `gh workflow run release.yml`
- Let github workflows take care of the rest
    - `release` workflow: will bump version according to conventional commit conventions, push tag, and create a Github release
    - `publish` workflow: will publish the new version to PyPI
    - `demo` workflow: records the demo and keeps it as the `demo-recording` artifact
- When this is a major release, manually (nothing else prompts these):
    - before triggering the release, add scenarios for what the release introduced to
      `demo/demo.sh`, so the demo keeps showing what the tool is for
    - once the release's `demo` workflow has succeeded, run `mise run demo-upload-latest`: it
      uploads that recording to asciinema.org, repoints the asciicast embed at the top of
      `README.md` at it, and commits that change (open a pull request for it, since `main` is
      protected). CI cannot publish it: GitHub-hosted runners have no route to asciinema.org
      (see `.github/workflows/demo.yml`). Between major releases, do the same when a release
      visibly changes what the demo shows.

## GitHub Config
- **Protect `main` and the release tags with rulesets.** Configured as the shared
  [repository conventions](https://github.com/iglootools/common/blob/main/guidelines/project-setup/repository.md#protect-the-default-branch-and-release-tags)
  describe: `main` cannot be deleted or force-pushed, changes go through a pull request
  merged with a merge commit, and the `test` check must pass first; `v*` tags cannot be
  deleted or moved, so a published version keeps pointing at the commit it was built from.

  ```bash
  gh api --method POST repos/iglootools/photree/rulesets --input - <<'JSON'
  {
    "name": "main",
    "target": "branch",
    "enforcement": "active",
    "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
    "rules": [
      { "type": "deletion" },
      { "type": "non_fast_forward" },
      { "type": "pull_request", "parameters": {
          "required_approving_review_count": 0,
          "dismiss_stale_reviews_on_push": false,
          "require_code_owner_review": false,
          "require_last_push_approval": false,
          "required_review_thread_resolution": false,
          "allowed_merge_methods": ["merge"] } },
      { "type": "required_status_checks", "parameters": {
          "strict_required_status_checks_policy": false,
          "do_not_enforce_on_create": false,
          "required_status_checks": [{ "context": "test", "integration_id": 15368 }] } }
    ]
  }
  JSON

  gh api --method POST repos/iglootools/photree/rulesets --input - <<'JSON'
  {
    "name": "release tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": { "ref_name": { "include": ["refs/tags/v*"], "exclude": [] } },
    "rules": [{ "type": "deletion" }, { "type": "update" }]
  }
  JSON
  ```

  To change an existing ruleset, `PUT` the same payload to
  `repos/iglootools/photree/rulesets/<id>` (ids from `gh api repos/iglootools/photree/rulesets`).
  Verify what GitHub actually enforces — an `active` ruleset with an empty `include` list
  protects nothing and looks enabled all the same:

  ```bash
  gh api repos/iglootools/photree/rules/branches/main -q '[.[].type]'
  # expect: ["deletion","non_fast_forward","pull_request","required_status_checks"]
  ```

  `test` must keep running on every pull request (no `paths` filter on its workflow), or a
  pull request it skips can never be merged.
- Settings > Advanced Security > Enable Dependency graph
- Set up the following Github secrets:
    - `ASCIINEMA_INSTALL_ID`:
        1. Execute `asciinema auth` in your terminal
        2. Click the suggested link
        3. store the content of `~/.local/state/asciinema/install-id` in the `ASCIINEMA_INSTALL_ID` secret
- **Enable Dependabot security updates.** These are *repository settings*, and
  [.github/dependabot.yml](../.github/dependabot.yml) cannot switch them on — that file only
  shapes the resulting PRs and restricts Dependabot to the security half
  (`open-pull-requests-limit: 0`, because Renovate owns routine version updates and delays them
  14 days). A repo with the file committed and these settings off looks configured while
  watching nothing:

    ```bash
    gh api -X PUT repos/iglootools/photree/vulnerability-alerts
    gh api -X PUT repos/iglootools/photree/automated-security-fixes
    ```

    Both are required, and they are separate switches: `vulnerability-alerts` is what notices a
    vulnerable dependency, `automated-security-fixes` is what opens the fix PR. Alerts alone
    give a Security tab entry and no PR — the easy state to land in by accident, since alerts
    are the more discoverable of the two.

    Each `PUT` returns `204 No Content` and prints nothing, so verify rather than assume:

    ```bash
    gh api repos/iglootools/photree/vulnerability-alerts -i | head -1   # expect HTTP/2.0 204
    gh api repos/iglootools/photree/automated-security-fixes            # expect "enabled": true
    ```

    A `404` from the first is the disabled state, not a missing endpoint. Undo with the same two
    URLs and `-X DELETE`. Needs admin on the repository; the dependency graph is a prerequisite
    and is on by default for public repositories.

## Renovate
- Added the [iglootools](https://github.com/iglootools) org to [developer.mend.io](https://developer.mend.io/)
