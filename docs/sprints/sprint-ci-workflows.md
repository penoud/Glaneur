> **Archived on 2026-09-25.** Sprint moved to `docs/sprints/` by
> US-05 of the sprint "Sphinx documentation and `docs/` cleanup".
> The progress status of stories US-CI-01 through US-CI-06 was not
> verified at the move; consult the `.github/workflows/` history to
> know what was actually delivered.

# CI Sprint — Harden the GitHub Actions chain

Historical location in the repository: `docs/sprint-ci-workflows.md`.

## Goal

Make the `tests → tag → build → release` chain safe **before** the
extraction of `sources/wordpress.py`. Fix two publication bugs, remove
redundant runs, and detect packaging problems **before** a tag is
created.

This sprint only modifies `.github/workflows/`. The only exception is
a control option added to the application (US-CI-06). **`__version__`
does not change**: this sprint's PRs publish nothing.

## Starting state (verified in the files)

| Workflow | Triggers | Role |
|---|---|---|
| `tests.yml` | `push` on `main`, `pull_request` | pytest under Ubuntu |
| `release.yml` | `push` on `main`, `workflow_dispatch` | pytest (duplicate), reading of `__version__`, tag, `gh workflow run build.yml --ref v<version>` |
| `build.yml` | `push` of `v*` tags, `workflow_dispatch` | PyInstaller, signing, Inno Setup, `.sha256`, Release (`publish` job limited to `refs/tags/v*` refs) |

The explicit trigger of `build.yml` is deliberate: a tag pushed with
`GITHUB_TOKEN` triggers no other workflow. It has to be kept.

## PR split

| PR | Stories | Risk |
|---|---|---|
| 1 | US-CI-01, US-CI-02 | Low, fixes publication |
| 2 | US-CI-03, US-CI-04 | Low, restructures `release.yml` |
| 3 | US-CI-05 | Medium, may reveal tests failing under Windows |
| 4 | US-CI-06 | Medium, touches `app.py` and adds a workflow |

Each PR is opened as a draft on the first commit, so tests run on
every push.

---

## US-CI-01 — Stop rebuilding the current release

**Problem.** In `release.yml`, the `exit 0` of "Create and push version
tag" ends only that step. "Trigger installer builds" has no condition:
every push on `main` without a version change reruns `build.yml` on
the existing tag, and `--clobber` replaces the assets. We get new
binaries and a new signature for the same version. Between the two
uploads, the installer and its `.sha256` no longer match, and the
updater rejects the update.

**Change** (`release.yml`):

```yaml
      - name: Create and push version tag
        id: tag
        # … env and shell unchanged
        run: |
          tag="v$VERSION"
          if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
            echo "Tag $tag already exists; nothing to tag."
            echo "created=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi
          # … git config, tag and push unchanged
          echo "created=true" >> "$GITHUB_OUTPUT"
      - name: Trigger installer builds
        if: steps.tag.outputs.created == 'true'
        # … unchanged
```

**Accepted trade-off.** If the tag is created but the trigger fails,
rerunning `release.yml` will no longer rerun the build. Recovery is
done by hand (see §Recovery procedure).

**Acceptance criteria**

- [ ] A push on `main` without a version change: `release.yml` goes
      green and no `builds` execution appears.
- [ ] The assets of the last release keep their date and SHA-256.

## US-CI-02 — Publish pre-releases as such

**Problem.** The `[0-9]*.[0-9]*.[0-9]*` validation accepts `1.0.5-rc.1`,
but `gh release create` is not given `--prerelease`. Yet
`GitHubReleaseProvider._is_stable` relies on the GitHub flag, not the
tag name. An rc would therefore be offered as a stable update.

**Choice.** Mark the release as pre-release rather than reject the
suffix. This keeps the ability to publish test rcs during the
multi-source work without affecting users, and the updater already
ignores pre-releases (covered by
`test_github_provider_ignores_prerelease_and_draft`).

**Change** (`build.yml`, `publish` job):

```bash
          prerelease=()
          [[ "$GITHUB_REF_NAME" == *-* ]] && prerelease=(--prerelease)
          if ! gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
            gh release create "$GITHUB_REF_NAME" \
              --repo "$GITHUB_REPOSITORY" \
              --verify-tag "${prerelease[@]}" \
              --title "Glaneur $GITHUB_REF_NAME" \
              --notes "Automated release $GITHUB_REF_NAME"
          fi
```

**Acceptance criteria**

- [ ] Verification outside `main`: manually push a `v0.0.0-ci.1` tag
      on a commit of the PR branch. `builds` is triggered by
      `push: tags`, and the release is created with the *Pre-release*
      badge.
- [ ] Then delete the test release and tag.

> Assumed, to be confirmed on first try: an empty `"${prerelease[@]}"`
> produces no argument under the Ubuntu runners' bash (bash ≥ 4.4).

## US-CI-03 — Branch guard and concurrency

**Problems.**

- `workflow_dispatch` on `release.yml` launched from another branch
  would tag and publish that branch's commit.
- Two close pushes on `main` launch two `release.yml` runs that may
  attempt the same tag.

**Change** (`release.yml`, at the top and on the tag job):

```yaml
concurrency:
  group: release
  cancel-in-progress: false   # never cut a tag or dispatch in progress

jobs:
  tag:
    if: github.ref == 'refs/heads/main'
```

**Acceptance criteria**

- [ ] `workflow_dispatch` of `release.yml` from a branch: job *skipped*.
- [ ] Two successive pushes on `main`: the second run waits for the
      first.

## US-CI-04 — A single tests definition

**Problem.** Tests run twice on every push to `main`, and their
definition is duplicated (apt packages, dependencies, command).

**Choice.** A reusable workflow (`workflow_call`) rather than a
composite action. It is the native mechanism to chain jobs between
workflows, and it requires no extra file.

**Change** (`tests.yml`):

```yaml
on:
  pull_request:
  workflow_call:

concurrency:
  # On a PR, a new push makes the previous run pointless.
  group: tests-${{ github.workflow }}-${{ github.head_ref || github.run_id }}
  cancel-in-progress: true
```

`tests.yml`'s `push: main` disappears: on `main`, it is `release.yml`
that calls it.

**Change** (`release.yml`): the `test-and-tag` job is split in two.

```yaml
jobs:
  tests:
    if: github.ref == 'refs/heads/main'
    uses: ./.github/workflows/tests.yml

  tag:
    needs: tests
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      # checkout, setup-python, version read, tag, dispatch
      # (the apt, pip pytest, and "Run tests before tagging" steps are removed)
```

`fetch-depth: 0` can be removed: the existence of the tag is tested by
`git ls-remote`, not through local history.

> Point of attention: in `tests.yml`, `github.head_ref` is empty when
> called by `workflow_call` from a push. Falling back to `run_id` then
> isolates each run so that a release test is never cancelled.

**Acceptance criteria**

- [ ] Push on `main`: a single pytest run, visible as job
      `tests / tests` in `tag-release`.
- [ ] A deliberately broken test on a verification branch prevents the
      `tag` job from starting (to be checked on a fork or on a dispatch
      branch with the guard temporarily lifted, never on `main`).
- [ ] Two rapid pushes on a PR: the first run is cancelled.

## US-CI-05 — Tests under Windows

**Why.** Several invariants are more fragile under Windows: the
atomic `replace` on an open file, `.part` file locking, and
`systeme.py`. Today, nothing tests them on the main platform. For a
public repo, the minute cost is zero.

**Change** (`tests.yml`):

```yaml
jobs:
  tests:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      # … checkout, setup-python unchanged
      - name: Install Qt runtime libs (offscreen)
        if: runner.os == 'Linux'
        # … unchanged
      # … dependency installation and pytest unchanged
```

> Assumed: the `offscreen` plugin is shipped in the
> `PySide6-Essentials` wheels for Windows, and `QT_QPA_PLATFORM=offscreen`
> works there. To be confirmed on first run.

**Risk.** Some tests may fail under Windows (path separators, files
left open in fixtures). We limit the time spent fixing them in this
sprint. A test that reveals a real engine bug leaves the sprint and
becomes an issue; it is then marked `xfail` under Windows, with the
issue number as the reason.

**Acceptance criteria**

- [ ] The matrix passes on both OSes, or each Windows `xfail` links to
      an open issue.

## US-CI-06 — Control packaging before the tag

**Problem.** PyInstaller only runs after the tag is created. A broken
exe — for example a module missing from the bundle — leaves a tag
with no release, and that tag can no longer be recreated. The
`sources/` extraction is exactly that kind of change.

**Part 1 — control option in the application** (`app.py`, at the very
top of the entry point, before `QApplication` is created):

```python
if "--controle-bundle" in sys.argv:
    # Imports what PyInstaller might have forgotten, without opening a window.
    # The result is signalled by the exit code: in windowed mode,
    # sys.stdout can be None and a print would raise.
    import Glaneur.engine  # noqa: F401
    # Once sources/ exists: import Glaneur.sources
    sys.exit(0)
```

> Assumed: the `.spec` builds the exe in windowed mode
> (`console=False`), hence the choice of an exit code rather than text
> output. If the exe is in console mode, nothing changes.

**Part 2 — new workflow** `.github/workflows/build-check.yml`:

```yaml
name: build-check

on:
  pull_request:
    paths:
      - "Glaneur/**"
      - "app.py"
      - "cli.py"
      - "build/**"
      - "requirements.txt"
      - ".github/workflows/build-check.yml"

concurrency:
  group: build-check-${{ github.head_ref }}
  cancel-in-progress: true

jobs:
  windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt pyinstaller
      - run: pyinstaller build\Glaneur.spec --noconfirm --clean
      - name: Bundle smoke test
        shell: pwsh
        run: |
          $p = Start-Process "dist\Glaneur\Glaneur.exe" `
                 -ArgumentList "--controle-bundle" -Wait -PassThru
          if ($p.ExitCode -ne 0) { throw "Bundle KO: code $($p.ExitCode)" }
```

There is neither signing nor Inno Setup here: we check the bundle's
content, not the publication chain. `Start-Process -Wait` is
necessary, because a windowed exe launched directly returns
immediately and its exit code would be lost.

**Do not do this**: declare `build-check` as a *required status check*
in branch protection. Because of the `paths` filter, a PR that does
not touch these paths never launches it, and the required check would
stay pending forever.

**Acceptance criteria**

- [ ] A PR that touches `Glaneur/` launches `build-check`, which
      passes.
- [ ] Counter-check on a throwaway branch: add to `QT_INUTILES` a Qt
      module actually imported by the application. The smoke test must
      fail.
- [ ] A PR that only touches `docs/` does not launch `build-check`.

---

## Out of scope

- **Reactivating Linux / macOS.** The macOS block targets `macos-13`,
  an image that GitHub has removed based on what I know (not verified
  as of today). We will have to move to `macos-14` or newer, so Apple
  Silicon, which changes the `.app` architecture. To be handled after
  the multi-source work.
- **Factoring the signing.** The `signtool` block is duplicated in
  `build.yml`. It is annoying but not risky, so we leave it alone.
- **Branch protection on `main`.** That is a repository setting, not a
  file. To be decided separately: enforcing it would require every
  change to go through a PR.

## Recovery procedure

> Updated by the sprint "CI — Validate the exe before tagging"
> (US-CI-07). Since that sprint, the tag is no longer placed before the
> build: the run stops after the build on the `release` environment
> waiting for a maintainer's approval. The vast majority of recoveries
> is therefore handled without ever consuming a version number.

1. **Installer rejected at approval.** Fix the code or the packaging,
   then push again on `main` with the **same** `__version__`. No tag
   exists and no release has been published: the new `release.yml`
   run rebuilds from scratch.
2. **Failure after approval** (tag or upload). From the run page,
   launch *Re-run failed jobs* on `publish`. The tag step accepts a
   tag already placed on the same commit; the upload uses `--clobber`
   and re-uploads the same bytes. Then verify that no asset has been
   mixed with those from another run.
3. **External cause during the build** (Windows runner, Chocolatey,
   timestamping). Launch *Re-run failed jobs* on `build`. If the
   incident persists after several attempts, a `workflow_dispatch` of
   `builds` on `main` produces an offline artifact for investigation.
4. **Last resort: tag already exists on another commit.** Bump the
   *patch* of `__version__` and push again on `main`. Do not delete
   the existing tag. Since no public release was produced for the
   rejected version, no user received it.

## Verification

The workflows are not tested against the fake server. So we verify:

- before each push, locally and optionally: `actionlint` on
  `.github/workflows/`. It is a workstation tool, not a project
  dependency;
- after merge, through the observable scenarios of the acceptance
  criteria. Every checked criterion points to the URL of the run that
  proves it.

## Definition of Done

- [ ] The four PRs are merged, each with its criteria checked and
      links to the corresponding runs.
- [ ] A push on `main` without a version change triggers no build.
- [ ] On `main`, pytest runs only once, on Ubuntu and Windows.
- [ ] Any PR touching the code or the packaging produces a controlled
      Windows bundle.
- [ ] `__version__` is unchanged over the whole sprint.
- [ ] The recovery procedure is documented.
