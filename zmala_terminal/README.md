# Zmala Terminal

Python terminal with platform adapters. Shared controllers start in `common/main.py`.

| Responsibility | Source |
| --- | --- |
| Application | `common/` owns state, configuration, calls, setup and Tk views |
| Pi hardware | `linux/` owns native media, Bluetooth, HDMI-CEC and Pi services |
| Windows compatibility | `windows/` supplies development adapters outside the Pi baseline |

`common/` means shared by terminal platforms. Shared Pi host identity/storage policy belongs in `../zmala_system/`. Native/display/hardware tests use the explicit commands in the implementation guide.

Read the [implementation guide](../docs/terminal.md) and
[development setup](../docs/development.md). Product requirements are in
[`requirements/terminal/`](../requirements/terminal/); unit and system plans are in
[`tests/terminal/`](../tests/terminal/).

Run from the repository root after installing the development dependencies:

```sh
make test
make requirements
```
