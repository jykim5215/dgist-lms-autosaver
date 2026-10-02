# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).

## What is signed

Only binaries built from this repository's source code by GitHub Actions
([`.github/workflows/release.yml`](.github/workflows/release.yml)) are signed:

- `붕어빵.exe` (the application)
- `bungeoppang-<version>-win-x64-setup.exe` (the installer)

Third-party components bundled unchanged (Python runtime and packages, Playwright driver, the Microsoft WebView2
bootstrapper) are not re-signed by this project.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [tutleblue](https://github.com/tutleblue) |
| Approvers | [tutleblue](https://github.com/tutleblue) |

Every signing request is approved manually by an approver in SignPath. All members use multi-factor authentication
on GitHub and SignPath.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user
or the person installing or operating it. See [PRIVACY.md](PRIVACY.md) for the services it connects to.
