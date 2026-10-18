# ZmalaCall

A television video-call terminal with portrait contacts and simple physical
controls. A separate Raspberry Pi OS/Linux server manages accounts, settings,
SIP signalling and the media relay. Terminals run on Raspberry Pi 4 or Windows.

## Documentation

- [General](docs/general.md): supported deployments, networking, source layout,
  development checks and the Doorstop workflow.
- [Server](docs/server.md): installation/migration, administration, authentication,
  callbacks, console, persistence and recovery.
- [Terminal](docs/terminal.md): illustrated installation, enrollment, controls,
  TV/remote integration, media, services and troubleshooting.

Requirements are maintained only in [Doorstop records](requirements/), with
product (`ZMC`), server (`SERV`) and terminal (`TERM`) documents. The guides describe
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
`make lint` checks sources, `make test` runs server/terminal tests, and
`make clean CLEAN_FLAGS=--dry-run` previews disposable-file cleanup.
Use the root **Start ZmalaCall Terminal.cmd** and **Stop ZmalaCall Terminal.cmd**
for managed Windows terminal instances; server hosting is Linux-only.
