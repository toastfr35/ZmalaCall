"""Select the platform implementation without loading foreign native APIs."""
import sys
if sys.platform == 'win32':
    from platforms.windows_text_renderer import *
else:
    from platforms.linux_text_renderer import *
