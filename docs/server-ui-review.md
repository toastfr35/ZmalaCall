# Server administration usability review

Reviewed the six live administration pages, sign-in and the group editor on
28 October 2026. Used an isolated service with sample accounts for editing and
save checks; the review did not modify live account or terminal settings.

## Findings and changes

- Supporting text was often 10–11 px and account actions had small targets.
  Raised supporting text to 12 px, primary field/row text to 14 px and icon
  buttons to 44 px. Preserved icon-only account actions with accessible names.
- Long terminal serials hid the account name in the selector. Show the name and
  account ID first; retain the full serial in Account association.
- Terminal connection, hardware and call-feature badges competed in one header.
  Split them into labelled groups and let the C20 explanation span both columns.
- Save changes was at the bottom of a long form. Keep it in a sticky bar with
  saved/unsaved feedback. Association remains a separate action; existing
  revision checks and retained drafts still apply.
- Old callback history obscured pending work. Default to Pending and provide a
  counted History view. Keep the selected view and keyboard focus after filtering.
  Completed records no longer show a future-action expiry label.

## Verification

- Visually inspected the live desktop pages and revised fixture layouts.
- Chromium component checks cover all six pages at 320, 390, 700 and 1920 px,
  overflow, touch targets, text size, terminal selector/status groups, sticky
  saving, modal scrolling and rejected edits.
- Real HTTP/browser checks verify saved terminal volume persists, account edits,
  conflicts and sign-out. Controller tests check pending/history separation and
  selection preservation without writes. Ringtone import/preview tests pass.
- Updated the technical server guide, Word guide and authoring source; rebuilt
  the server PDFs and inspected the revised guide pages.
- No physical phone touch test or real call is claimed for these presentation changes.

Normative behavior remains in the linked Doorstop requirements; this record
summarizes review evidence and is not a separate specification.
