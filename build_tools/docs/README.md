# Installation guide sources

The installation guides are committed under `output/docx` and `output/pdf`.
Both use `zmala_terminal_setup.exe` without exposing its build-machine path.

To regenerate on Windows, install `reportlab`, `Pillow` and `python-docx` into
your document-building Python environment. Put Poppler's `pdftoppm` on PATH;
the PDF builder uses the Windows Segoe UI fonts.

Run from any working directory:

```powershell
python build_tools/docs/build_installation_pdf.py
python build_tools/docs/build_installation_docx.py
```

The Word builder extracts the connection diagram from the PDF. Its other
content, including the settings table and web links, remains editable.
The pairing illustration comes from the terminal's approved asset.

Render and visually check all pages after changing either builder. The guide
uses the Argon ONE Pi 4 V2 rear-panel layout and deliberately omits the local
installer location. The installer binary is built separately with
`build_tools/windows_installer/build.py` and remains excluded from Git.
