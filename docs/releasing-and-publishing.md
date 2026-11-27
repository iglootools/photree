# Releasing and Publishing

The build uses the
[uv-dynamic-versioning](https://github.com/ninoseki/uv-dynamic-versioning)
hatchling plugin to automatically set the version based on git tags. It is
powered by the same [dunamai](https://github.com/mtkennerly/dunamai) library as
the `poetry-dynamic-versioning` plugin used before the move to uv, so version
strings are unchanged: a tagged commit builds as `0.6.1`, and an untagged one as
`0.6.1.post6.dev0+2a99beb`.

Because the version comes from git rather than from `pyproject.toml`, a build
that cannot see the repository history has no version to report.
`[tool.uv-dynamic-versioning] fallback-version` makes that case produce `0.0.0`
instead of failing — which is required, since Renovate builds the project
without git context — so a build from a shallow checkout or an exported archive
succeeds while producing a mis-versioned artifact. `mise run build-verify`
(wired into `ci-build`) inspects the built wheel's metadata and fails on
`0.0.0`, because PyPI does not allow a version to be re-uploaded once taken.
That is also why the publish workflows check out with `fetch-depth: 0` and
`fetch-tags: true`.

## Release a Version

1. When this is a major release, first add scenarios for what the release
   introduced to `demo/demo.sh`, so the demo keeps showing what the tool is
   for. Nothing else prompts this.
2. Trigger the `release` workflow: `gh workflow run release.yml`.
3. The workflows take care of the rest:
   - `release` bumps the version according to conventional commits, pushes the
     tag and creates the GitHub release, with the
     [github-tag](https://github.com/marketplace/actions/github-tag) action.
   - `publish` starts when `release` completes and publishes the new version to
     PyPI with the
     [pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish)
     action. Re-run it if needed with
     `gh workflow run publish.yml -f tag=<tag>`.
   - `demo` starts when `release` completes, records the demo and keeps it as
     the `demo-recording` artifact. Re-run it with
     `gh workflow run demo.yml -f tag=<tag>`.
4. When this is a major release, once its `demo` workflow has succeeded, run
   `mise run demo-upload-latest`. It uploads that recording to asciinema.org,
   repoints the asciicast embed at the top of `README.md` at it, and commits
   that change; open a pull request for it, since `main` is protected. CI
   cannot publish it: GitHub-hosted runners have no route to asciinema.org (see
   `.github/workflows/demo.yml`). Between major releases, do the same when a
   release visibly changes what the demo shows.

## PyPI Config

[PyPI](https://pypi.org/) and [Test PyPI](https://test.pypi.org/) have been
configured to allow the `photree` project to be published using OpenID Connect
(OIDC) authentication, with a trusted publisher on each index:

| Field | PyPI | Test PyPI |
|---|---|---|
| Owner | `iglootools` | `iglootools` |
| Repository name | `photree` | `photree` |
| Workflow name | `publish.yml` | `publish-test.yml` |
| Environment name | `pypi` | `testpypi` |

The workflow name is the filename of the workflow that uploads, so each index
trusts a different file. A mismatch in any field is only reported when an upload
is attempted, as an `invalid-publisher` error.

Rehearse on Test PyPI after changing anything on the publish path (the
workflows, the build backend, the build constraints, the trusted-publisher
settings) with `gh workflow run publish-test.yml --ref main`. It publishes under
a throwaway `<last release>.dev<timestamp>` version, so it can be repeated.

Check
[Publishing to PyPI with a Trusted Publisher](https://docs.pypi.org/trusted-publishers/)
for more details on OIDC authentication.
