# Repository working instructions

Keep code, documentation and requirements synchronized in every change.

- Before editing, identify the affected behavior, Doorstop items, code trace
  comments and documentation. Update affected artifacts in the same change set;
  a change is not complete while they disagree.
- Keep normative product, server and Raspberry Pi terminal requirements only in
  `requirements/`. Maintain the PROD → SHLR → SLLR and PROD → THLR → TLLR
  hierarchy, stable IDs, implementation references and verification guidance.
- Maintain standalone `@llr` comments beside the owning implementation. When
  moving, adding or removing code, update both the comments and the corresponding
  Doorstop references. Follow the format documented in `docs/general.md`.
- Keep `docs/general.md`, `docs/server.md` and `docs/terminal.md` accurate as
  technical implementation guides. Update affected Word user guides and their
  authoring sources when installation, configuration or user workflows change;
  distribute those guides beside the installers.
- Regenerate affected derived artifacts using their build tools. Do not hand-edit
  generated admin bundles or commit `requirements/output/`.
- Run checks appropriate to the change. When requirements, references, trace
  comments or their tooling change, run `make requirements` to validate and rebuild
  the report. Review suspect links before clearing them; never mark a requirement
  reviewed or a verification passed without the corresponding review or evidence.

Review impact even for refactoring and documentation-only changes. Artifacts that
remain accurate need no gratuitous edits. Report any unresolved inconsistency.

Tests belong in the top-level `tests/` tree. Product verification is requirement
based: `tests/server/LLT/` and `tests/terminal/LLT/` contain unit tests linked to
SLLRs/TLLRs; `HLT/` contains system/integration scenarios linked to SHLRs/THLRs.
Every LLT/HLT scenario starts with the stable `@test`, `@requirements`,
`@environment`, `@plan` and `@pass` comments documented in `docs/general.md`.
Keep reciprocal Doorstop references synchronized. Plans explain the inputs,
procedure and expected behavior actually checked; do not claim whole-requirement
coverage from a partial assertion or count skipped/manual checks as passed.
Shared fixtures belong in `tests/support/`. Non-RBT experiments, development-tool
regressions and Windows-terminal compatibility checks belong in `tests/adhoc/`.
New regression tests for product behavior must use LLT/HLT, not the ad-hoc escape
hatch. Run `make requirements` after changing test plans or links.
