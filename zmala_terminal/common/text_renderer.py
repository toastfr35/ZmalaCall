"""Select the platform implementation without loading foreign native APIs."""
import sys
if sys.platform == 'win32':
    from zmala_terminal.windows.text_renderer import *
else:
    from zmala_terminal.linux.text_renderer import *
