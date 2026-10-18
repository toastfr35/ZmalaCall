"""Platform graphics backend, with common vector shapes and layout."""
import sys
if sys.platform == 'win32':
    from zmala_terminal.windows.icons import IconRenderer as IconRenderer
else:
    from zmala_terminal.linux.icons import IconRenderer as IconRenderer
