# ZmalaCall documentation

[Design](design.md) describes terminal and server behavior and its operating behavior. See the [platform and recovery notes](reliability.md) for Windows/Linux scope and remaining hardware acceptance. Requirements are maintained in Doorstop YAML records; the Markdown catalogues are generated views:

[Implementation guide](implementation.md) maps the source modules, explains their state and lifetime rules, and lists development checks.

[Pi server installation](pi-server-installation.md) covers the Windows server
installer, migration, wired SSH control and microSD wear reduction.

- [Product requirements](product_requirements.md) (`ZMC`): shared product expectations.
- [Terminal requirements](terminal_requirements.md) (`TERM`): terminal behavior, controls, provisioning and maintenance.
- [Server requirements](server_requirements.md) (`SERV`): accounts, groups, signaling, administration and persistence.

The requirements tree is `ZMC → TERM / SERV`. Each terminal/server requirement links to a product requirement and references an implementation or verification file. YAML records under `requirements/` are the editable source; regenerate the catalogues after changing them.

## Install and run Doorstop

Doorstop 3.2 uses its own Python 3.13 environment under `build_tools/runtime/doorstop/`. This installation does not change the terminal's Python runtime. The install script requires `uv` and keeps downloaded Python and package caches under `build_tools/runtime/`.

From the project root in PowerShell:

```powershell
& '.\build_tools\install-doorstop.ps1'
& '.\build_tools\doorstop.cmd' --version
& '.\build_tools\doorstop.cmd' --no-reformat --error-all --no-review-check
& '.\build_tools\publish-requirements.ps1'
```

The validation command checks levels, parent links, stale parent stamps and referenced files. The imported baseline is left unreviewed for maintainer review; `--no-review-check` permits structural validation before that review. After review, omit that option for normal validation. The wrapper supplies an absolute project path so references resolve correctly on Windows.

This checkout is a Git repository. Keep source YAML records and generated catalogues together in version control; run Doorstop from the project root so it can locate the working copy.

## Edit, link and review requirements

Add an item, then edit its new YAML file and link it to the appropriate product requirement:

```powershell
& '.\build_tools\doorstop.cmd' add TERM
& '.\build_tools\doorstop.cmd' edit TERM028
& '.\build_tools\doorstop.cmd' link TERM028 ZMC003
```

Use an existing item's ID to edit it instead. Every record contains its requirement text, human-readable header and parent links. `references` uses project-relative paths to the code or tests that implement/check it. A reference is a traceability link, not a test-pass result. Run the referenced tests separately when changing the behavior.

After reviewing an item's text, record the review. If a parent changes, inspect its children before clearing their suspect links and reviewing the affected records:

```powershell
& '.\build_tools\doorstop.cmd' clear TERM028
& '.\build_tools\doorstop.cmd' review TERM028
& '.\build_tools\publish-requirements.ps1'
```

`clear` accepts the current parent text as the child's baseline; it should follow the impact review. `review` stamps the reviewed item content. Regeneration preserves these links in the readable catalogues.

To publish an HTML report with traceability navigation:

```powershell
& '.\build_tools\doorstop.cmd' publish all '.\build_tools\tmp\requirements-html' --html
```

See the [official Doorstop documentation](https://doorstop.readthedocs.io/en/latest/) for additional commands and formats.
