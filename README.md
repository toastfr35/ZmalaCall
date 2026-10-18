# ZmalaCall

A television video-call terminal with portrait contacts and simple physical
controls. A separate Raspberry Pi OS/Linux server manages accounts, settings,
SIP signalling and the media relay. Terminals run on Raspberry Pi 4 or Windows.

## Documentation

Technical implementation guides:

- [General](docs/general.md): architecture, networking, builds and Doorstop.
- [Server](docs/server.md): deployment, APIs, SIP/media, persistence and recovery.
- [Terminal](docs/terminal.md): controllers, native media, TV/remote and Pi integration.

Word user guides:

- [Prepare a new terminal](docs/terminal_prep.docx)
- [Configure a terminal](docs/terminal_config.docx)
- [Use a terminal](docs/terminal_use.docx)
- [Prepare a server](docs/server_prep.docx)

Requirements are maintained only in [Doorstop records](requirements/), with
product (`PROD`), server HLR/LLR (`SHLR`/`SLLR`) and Pi-terminal HLR/LLR
(`THLR`/`TLLR`) documents. Run `make requirements` for the searchable offline report
at `requirements/output/index.html`; GitHub Verify also publishes it as the
`zmala-requirements` artifact. The guides describe
current operation and implementation; they do not duplicate requirement catalogues.
[astra.md](astra.md) tracks remaining engineering work.

## Install

Download the installers and guides from the
[latest public release](https://github.com/toastfr35/ZmalaCall/releases/latest).
For unreleased versions, use successful installer workflow artifacts under
[Actions](https://github.com/toastfr35/ZmalaCall/actions).
Follow the relevant guide before flashing or deploying. Installers require a
fresh supported Raspberry Pi OS image and wired SSH; runtime state and private
credentials are excluded from packages.

## Develop

See [development setup and checks](docs/general.md#development-tools-and-checks).
`make lint` checks sources, `make test` runs requirement-based server/terminal
LLT and HLT suites from `tests/`, `make requirements` publishes test traceability
and coverage gaps, and
`make clean CLEAN_FLAGS=--dry-run` previews disposable-file cleanup.
Use the root **Start ZmalaCall Terminal.cmd** and **Stop ZmalaCall Terminal.cmd**
for managed Windows terminal instances; server hosting is Linux-only.
