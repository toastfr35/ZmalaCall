"""Platform graphics backend, with common vector shapes and layout."""
import sys
if sys.platform == 'win32':
    from platforms.windows_icons import IconRenderer as IconRenderer
else:
    from platforms.linux_icons import IconRenderer as IconRenderer
