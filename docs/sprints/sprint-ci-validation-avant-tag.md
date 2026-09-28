# CI Sprint — Validate the exe before tagging

Target location in the repository: `docs/sprints/sprint-ci-validation-avant-tag.md`.

## Goal

On `main`, build and control the Windows installer **before** creating
the tag, have the installer manually validated by the maintainer, then
publish **exactly the bytes tested**.

Current chain:

```
tests → tag → gh workflow run build.yml --ref v<version> → build → publish
```

Target chain, in **a single run** of `release.yml`:

```
tests → version → build (+ smoke test) → [manual approval] → tag + publish
```

## Sprint constraints

- Only `.github/workflows/` and the documentation change. No
  application code changes: `--controle-bundle` already exists in
  `app.py`.
- **`__version__` does not change.** Every PR of this sprint
  publishes nothing.
- No new dependency.
- YAML comments in **English**, explaining the *why*.
- The merge on `main` and the GitHub environment setup belong to the
  **maintainer**. Claude Code opens the PR in draft and stops there.
- Local verification with `actionlint` on `.github/workflows/`, if the
  tool is available on the workstation. This is not a project
  dependency.

## Decisions and their rationale

| Decision | Rationale |
|---|---|
| `build.yml` becomes reusable (`workflow_call`) and loses `push: tags` | The tag dispatch existed only because a tag pushed with `GITHUB_TOKEN` triggers no workflow. It is no longer necessary. |
| The `publish` job moves from `build.yml` to `release.yml` | The release receives the artifacts of the build that was tested, in the same run. |
| The tag is placed explicitly on `$GITHUB_SHA` | The tag names the commit that was built, never a more recent commit. |
| `publish` carries the `release` environment, with required reviewer | The run stops after the build: the maintainer downloads the installer, tests it, then approves or rejects. This is the approval planned in lot 9, put in place from now on. |
| A rejection creates neither tag nor release | The version number is not consumed: fix, push again with the same `__version__`, and the next run rebuilds. |
| Smoke test placed before signing | No point in signing a broken bundle. |

**Dead end not to take**: validate an exe in one job, then let
`build.yml` rebuild on the tag. We would then publish a binary
different from the one that was validated, with a different signature.

---

## US-CI-07 — Build, validate, then tag inside `release.yml`

### Change 1 — `.github/workflows/release.yml` (full replacement)

See the file shipped in this PR. Key points:

- `permissions: contents: read` at the top level; no more
  `actions: write` since there is no more `gh workflow run`.
- Concurrency `group: release`, `cancel-in-progress: false`: never cut
  a run waiting for approval or publication.
- `tests` job: calls `tests.yml` via `workflow_call`.
- `version` job: reads and validates `__version__`, decides whether a
  build is needed (`release=true` if the tag does not yet exist).
- `build` job: calls `build.yml` via `workflow_call` with
  `secrets: inherit` (necessary for `WINDOWS_PFX_*`).
- `publish` job: under `environment: release`, downloads the
  artifacts, places the tag on `$GITHUB_SHA`, publishes the release.
  `--clobber` is safe here: it is only used to rerun the same build
  (same bytes), which does not reintroduce the bug fixed by US-CI-01.
  The US-CI-02 pre-release logic is kept: it now reads `$TAG` instead
  of `GITHUB_REF_NAME`, which would be `main`.

The tag step is idempotent: the approval wait can last for days, so it
re-checks the existence of the tag at publication time and only
accepts an existing tag if it already points to `$GITHUB_SHA` (recovery
after a `Re-run failed jobs`).

### Change 2 — `.github/workflows/build.yml`

**a. Triggers**: `workflow_call` and `workflow_dispatch` only.
`push: tags` disappears. A standalone `workflow_dispatch` produces an
installer as an artifact, without publishing anything, from any
branch.

**b. Smoke test** in the `windows` job, right after the `pyinstaller`
step and before "Sign application when certificate is configured":

```yaml
      - name: Smoke test the bundle
        # Windowed exe: launched directly it returns at once and its exit
        # code is lost; Start-Process -Wait -PassThru exposes it.
        shell: pwsh
        run: |
          $p = Start-Process "dist\Glaneur\Glaneur.exe" `
                 -ArgumentList "--controle-bundle" -Wait -PassThru
          if ($p.ExitCode -ne 0) { throw "Bundle check failed: exit code $($p.ExitCode)" }
```

**c. Removal of the `publish` job**, moved to `release.yml`.

**d. Comments on the Linux and macOS blocks**: they now point to the
`publish` job of `release.yml`. A reminder is added: on
re-activation, read the version from `__version__`, because
`GITHUB_REF_NAME` will be `main`. The code of these blocks stays
commented and unchanged.

The `windows` job stays identical otherwise, including the artifact
name `Glaneur-setup`.

### Change 3 — documentation

- `docs/sprints/sprint-ci-workflows.md`, section "Recovery procedure",
  updated:
  - **Installer rejected at approval**: fix, then push again on
    `main` with the same `__version__`. No tag exists.
  - **Failure after approval** (tag or upload): launch *Re-run failed
    jobs* on `publish`. The tag step accepts a tag already placed on
    the same commit.
  - The *patch* bump is only a last resort now, if a tag exists on
    another commit.
- `README.md`: the passages that describe publication by `push` of a
  tag are corrected and mention the approval step. The passages about
  the `WINDOWS_PFX_*` signing stay as they are, because they belong
  to lot 9.

### Repository setup — done by the maintainer, not by Claude Code

Under *Settings → Environments → New environment*:

1. Create the `release` environment.
2. Tick *Required reviewers* and add the maintainer.
3. **Leave *Prevent self-review* unchecked.** Otherwise a lone
   maintainer can never approve.
4. Optional: restrict *Deployment branches* to `main`.

Without this setup, `environment: release` is created automatically
**with no protection**, and publication proceeds with no pause. The
PR must not be merged before the setup is done.

### Verified or assumed

- **Documented by GitHub**:
  - environments with required reviewers are available on public
    repositories, regardless of plan;
  - `secrets: inherit` is needed for `build.yml` to see
    `WINDOWS_PFX_*`.
- **Assumed, to be confirmed on first try**:
  - artifacts produced by a called workflow are downloadable by a
    job of the calling workflow;
  - they are visible on the run page during the approval wait
    (behaviour announced since `upload-artifact` v4).
- **Concurrency**: during the wait, the run occupies the `release`
  group. A second push waits. A third one replaces the second in the
  queue, because GitHub only keeps one pending. The last commit wins,
  which is acceptable.
- **Smoke test limits**: it covers `app.py`'s module-level imports,
  plus `engine`, `sources`, and `updater`. It covers neither the
  window opening, nor the `.qm` files, nor lazy Qt imports. The
  manual pre-approval trial covers those.

### Acceptance criteria

Observed after merge. Every ticked criterion points to the URL of the
run that proves it.

- [ ] `actionlint` reports nothing on `.github/workflows/`.
- [ ] Push on `main` without a version change: `build` and `publish`
      are *skipped*, and no approval is requested.
- [ ] `workflow_dispatch` of `builds` on a branch: the `Glaneur-setup`
      artifact is produced, without tag or release.
- [ ] On a fork, or on a branch with the guard temporarily lifted,
      never on `main`, with a `0.0.0-ci.1` version:
      - the run stops in *Waiting* and the installer is downloadable;
      - a rejection creates neither tag nor release;
      - an approval creates the tag on the built commit and a
        *Pre-release* release;
      - the SHA-256 of the published asset is identical to the tested
        artifact.
- [ ] *Re-run failed jobs* on `publish` after a simulated upload
      failure: the tag step resumes without error.
- [ ] Counter-check: a module imported by the application, added to
      `QT_INUTILES` on a throwaway branch, causes the smoke test to
      fail, and no approval is requested.
- [ ] Cleanup: delete the test tags and releases.

---

## US-CI-08 (optional, separate PR) — `build-check` reuses `build.yml`

**Problem.** `build-check.yml` does not compile the translations. It
therefore does not check the same bundle as the one that is
published.

**Change.**

- Add to `build.yml` a `workflow_call.inputs.sign` input (boolean,
  default `false`).
- Condition the two signing steps on `inputs.sign`. For the direct
  `workflow_dispatch`, an equivalent input defaults to `false`.
- In `release.yml`, call the build with `with: { sign: true }`.
- Reduce `build-check.yml` to a single job that calls `build.yml`
  with `sign: false`, keeping its `paths` filter and its concurrency.

**Rationale.** We get a single build definition, and every PR
provides its installer as an artifact. A PR build is never signed.

**Acceptance criteria**

- [ ] A PR that touches `Glaneur/` produces the `Glaneur-setup`
      artifact, unsigned, with `.qm` files present in the bundle.
- [ ] Publication on `main` stays signed when the certificate is
      configured.

---

## Definition of Done

- [ ] PR(s) opened in draft, with the US-CI-07 criteria listed.
- [ ] `__version__` unchanged.
- [ ] `release` environment configured by the maintainer before the
      merge.
- [ ] Recovery procedure and README up to date.
