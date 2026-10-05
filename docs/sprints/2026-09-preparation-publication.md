# Sprint - Preparing the project for publication

> **Archived on 2026-09-25.** Sprint finished, apart from two
> maintainer checkboxes deliberately left unchecked (US-07 "full Qt
> GUI startup", US-08 "final review + publication commit").

Target version: **1.0.2**

## Goal

Prepare the project for a public release by removing third-party
assets, clarifying the license, and decoupling the engine from the
WordPress site currently in use.

## US-01 - Remove the distributed graphic identity

- [x] Identify and verify `build/Glaneur.ico`.
- [x] Remove the asset from the repo.
- [x] Add the asset to `.gitignore`.
- [x] Verify that no other third-party image is present in the repo.
- [x] Keep the graphic fallback generated dynamically by
  `icone_application()`.

## US-02 - Clarify the absence of affiliation

- [x] Add the disclaimer at the top of `README.md`.
- [x] Mention the personal and independent nature of the project.
- [x] Mention the absence of affiliation, endorsement, and
  sponsoring.
- [x] Clarify the descriptive use of the trademarks mentioned.

## US-03 - Add an explicit license

- [x] Choose GNU GPL version 3 or later for the code.
- [x] Add the `LICENSE` file.
- [x] Reference the license in `README.md`.
- [x] Distinguish the license of the code from the rights applicable
  to the downloaded content.

## US-04 - Externalise the target site

- [x] Add `site` to `Config`, with `https://example.com` as the
  historic default value.
- [x] Add `site` to `Options`.
- [x] Build `self.base` with `options.site.rstrip("/")`.
- [x] Build `self.api` with `self.base`.
- [x] Use `self.api` inside `_api()` instead of a global constant.
- [x] Remove the global constants `BASE` and `API` from the engine.

## US-05 - Propagate the configuration

- [x] Pass `Config.site` from `app.py` to `Options.site`.
- [x] Pass `Config.site` from `cli.py` to `Options.site`.
- [x] Keep a single source of truth for the target site.
- [x] Do not modify the download logic outside this configuration.

Expected flow:

```text
Config.site
  -> app.py / cli.py
  -> Options.site
  -> Engine
  -> self.base
  -> self.api
```

## US-06 - Make the tests independent of the real site

- [x] Replace the test catalogue URLs with a fictional origin.
- [x] Provide a `site` URL specific to the test.
- [x] Verify the simulated WordPress endpoints used by the engine.
- [x] Verify that the tests download no real content.
- [x] Do not add a real image to the fixtures.
- [x] Cover the trailing slash of the URL with
  `https://fake-wordpress.test/`.

## US-07 - Functional verification

- [x] Verify the default value of `Config.site`.
- [x] Verify that another origin can be provided to `Options`.
- [x] Verify the normalisation of the trailing slash.
- [x] Verify that the mocked API works.
- [x] Add a persistent URL field in the interface for the WordPress
      site.
- [x] Run `python tests/test_moteur.py`.
- [x] Compile the Python modules with `python -m compileall`.
- [x] Verify that `python cli.py --help` starts.
- [ ] Start the full graphical interface in a Qt environment.

## US-08 - Documentation and audit before publication

- [x] Document the site configuration in `README.md`.
- [x] Describe the project as a configurable WordPress downloader.
- [x] Document the distinction between code and downloaded content.
- [x] Verify the absence of image files in the repo.
- [x] Verify the absence of a site constant in `Glaneur/engine.py`.
- [x] Verify whitespace and line endings with `git diff --check`.
- [ ] Review historical files and URLs before final publication.
- [ ] Publication commit to be made by the maintainer.

## US-09 - Linux packaging

- [x] Add the Debian package (`.deb`).
- [x] Add the Flatpak manifest and its launcher.
- [x] Add the desktop metadata and the Linux icon.
- [x] Build the Linux packages in GitHub Actions on tags.
- [x] Add a macOS application (`.app`, `.zip`, and `.dmg`).

## US-10 - Windows auto-update

- [x] Compare SemVer versions against stable GitHub Releases.
- [x] Select the Windows installer and verify its SHA-256.
- [x] Prepare a separate Windows updater.
- [x] Publish installers and checksums in a GitHub Release.

## Definition of Done

The sprint is ready when:

- the engine builds the API exclusively from `Options.site`;
- the callers pass `Config.site`;
- the tests work without access to the real site;
- no third-party asset is distributed;
- `LICENSE` and the disclaimer are in place;
- the tests and publication controls pass;
- the remaining manual checks are validated by the maintainer.
