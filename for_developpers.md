# Developer information

[Back to the product overview](README.md)

Start with the [development setup and checks](docs/general.md#development-tools-and-checks).
The implementation guides cover the current code and its component boundaries:

- [System overview](docs/general.md): architecture, networking, builds and verification.
- [Server](docs/server.md): web administration, APIs, SIP/media, persistence and recovery.
- [Terminal](docs/terminal.md): user functions, controllers, native media and Pi hardware.
- [Android](docs/android.md): QR enrollment, calls, incoming alerts and release signing.

After installing the development dependencies, run these from the repository root:

```sh
make lint            # Static checks and generated-asset consistency
make test            # Portable requirement-based unit and integration tests
make requirements    # Validate traces and build the searchable requirements report
make coverage-llt    # Measure unit-test coverage separately from other tests
```

`make clean CLEAN_FLAGS=--dry-run` previews temporary-file cleanup.
Build and test the Android app with `make phone test-android` after configuring
the Android SDK and JDK as described in the Android guide.

## Requirements and verification

[Doorstop records](requirements/) are the source of product requirements.
Product items lead to themed server, Pi-terminal and Android high-level requirements,
then low-level requirements linked to code and tests. Tests live in
[`tests/server/`](tests/server/), [`tests/terminal/`](tests/terminal/) and
[`tests/android/`](tests/android/), with
separate `LLT` unit tests and `HLT` system/integration scenarios.

`make requirements` writes the report to `requirements/output/index.html`.
The [Verify workflow](https://github.com/toastfr35/ZmalaCall/actions/workflows/verify.yml)
also publishes it as the `zmala-requirements` artifact. See the
[requirement rewrite method](howto_rewrite_requirements.md) for the process and
[astra.md](astra.md) for remaining engineering work.

## Android builds

The Android companion lives in `zmala_phone/`. See [Android setup and development](docs/android.md). It uses App-only QR enrollment and the terminal visual identity, with LAN or encrypted server-relayed video calls and Firebase incoming-call alerts when the app is closed.

For a signed APK, use `python build_tools/android/release.py` with private release
signing and Firebase configuration as described in the Android guide. Signing keys,
deployment credentials and account QR codes are not included in this repository.

## Development installers and releases

Start work with a GitHub issue and a feature branch, then open a pull request
to `main` linking the issue with `Closes #number`. Push only the feature branch.
Verify runs once per pull request update; a newer update cancels superseded
checks. Its Linux, Windows and Android jobs remain separate platform checks.
Branch pushes and merges do not launch duplicate Verify runs.

Every pull request, including documentation changes, must increase both
`versionName` and `versionCode` in `zmala_phone/app/build.gradle` above current
`main`. Normally use the next patch version and code + 1. Verify checks the
increase and rejects an existing release tag. Update the branch if another
pull request merges first. Required checks must pass against the current base
before merging; direct pushes, force pushes and deletion of `main` are blocked.

The [Publish release workflow](https://github.com/toastfr35/ZmalaCall/actions/workflows/release.yml)
starts automatically on each merge into `main`, using the committed version
for its tag. It builds the two Pi installers, six PDFs and signed Android APK,
then publishes only after packaging, smoke tests and signature checks pass.
The separate installer workflows have been removed. The release workflow's
`release-windows` and `release-android` artifacts are retained for seven days;
GitHub sign-in is required to download them.

Use **Run workflow** on `main` to retry an unpublished release; the optional tag
input must match the committed version. Published releases are never replaced.
A failed upload leaves a draft: inspect it and remove only that unpublished
draft/tag before retrying the same commit. For an older failed merge, rerun its
original workflow so the intended source commit is retained. See the
[distribution guide](docs/general.md#distribution-and-third-party-components)
for build tooling and the Android guide for private signing inputs.

Editable user-guide sources are retained in `docs/`: `server_prep.docx`,
`terminal_prep.docx`, `terminal_config.docx`, `terminal_use.docx`,
`phone_installation.docx` and `phone_guide.docx`. Keep them and their authoring
sources synchronized with user-facing changes; regenerate the release PDFs
using `build_tools/release/guides.py`.
