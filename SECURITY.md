# Security Policy

## Supported Versions

Glaneur is actively maintained on the latest stable release.

Security fixes are generally applied to the latest stable version. Older versions may not receive security updates.

| Version                            | Supported          |
| ---------------------------------- | ------------------ |
| Latest stable release              | :white_check_mark: |
| Older releases                     | :x:                |
| Development / pre-release versions | :x:                |

If you are using an older version, please update to the latest stable release before reporting an issue whenever possible.

## Reporting a Vulnerability

If you discover a security vulnerability in Glaneur, please **do not open a public GitHub issue**.

Security vulnerabilities should be reported privately to the project maintainer.

Please use one of the following methods:

* **GitHub Security Advisories**: use the private vulnerability reporting feature available from the repository's Security tab, when available.
* If private vulnerability reporting is not available, contact the repository owner privately through GitHub.

When reporting a vulnerability, please provide as much information as possible, including:

* A description of the vulnerability.
* The affected version or commit.
* Steps to reproduce the issue.
* The expected and observed behaviour.
* The potential security impact.
* A minimal proof of concept, if available.
* Any relevant logs or screenshots, while removing passwords, tokens, personal information, or other sensitive data.

Please do not include credentials, API keys, authentication tokens, cookies, or other secrets in a vulnerability report.

## What to Expect

The maintainer will acknowledge a security report as soon as reasonably possible and will investigate the issue.

If the vulnerability is confirmed:

1. The issue will be assessed for severity and affected versions.
2. A fix or mitigation will be developed when appropriate.
3. A new release may be published containing the security fix.
4. A GitHub Security Advisory may be published when appropriate.
5. The reporter may be credited in the security advisory or release notes, unless they prefer to remain anonymous.

There is currently no guaranteed response or remediation time.

## Scope

Security reports are particularly relevant to issues involving:

* Arbitrary code execution.
* Command or argument injection.
* Path traversal or unsafe file handling.
* Unintended access to local files.
* Unsafe handling of downloaded files.
* Malicious or manipulated update packages.
* Vulnerabilities in the automatic update mechanism.
* Improper validation of remote URLs or downloaded content.
* Sensitive information being exposed through configuration files or logs.
* Vulnerabilities in HTTP communication with remote sources.
* Security issues introduced through application dependencies.

Glaneur communicates with external websites to retrieve image inventories and download files. The supported source implementations currently include WordPress and Djangoplicity-based sites.

## Out of Scope

The following are generally outside the scope of Glaneur security reports:

* Security vulnerabilities in third-party websites targeted by Glaneur.
* Vulnerabilities in WordPress, Djangoplicity, GitHub, PySide6, Python, Windows, or other third-party software themselves.
* Copyright or licensing issues concerning content downloaded from third-party websites.
* Website-specific restrictions or terms of service.
* Issues that require physical access to the user's computer.
* Denial-of-service attacks against third-party websites.
* Bugs that have no meaningful security impact.

Third-party vulnerabilities should be reported to the corresponding project or vendor.

## Downloaded Content

Glaneur downloads content from websites specified by the user. Downloaded images and other remote content are not part of the Glaneur source code and are not implicitly trusted or endorsed by the project.

Users are responsible for ensuring that they have the necessary rights and permissions to download and use content from the websites they configure.

## Automatic Updates

Glaneur includes an automatic update mechanism that checks GitHub Releases and verifies the SHA-256 checksum of the downloaded installer before proceeding with the update.

Security issues affecting the update mechanism should be reported privately because exploitation could potentially affect the integrity of the installed application.

## Responsible Disclosure

Please allow reasonable time for the maintainer to investigate and address a reported vulnerability before publicly disclosing technical details.

Coordinated disclosure helps protect users while a fix is being prepared.

## Security Advisories

Confirmed security vulnerabilities may be documented through GitHub Security Advisories and/or the project's release notes.

The project does not currently operate a bug bounty program or provide financial rewards for vulnerability reports.
