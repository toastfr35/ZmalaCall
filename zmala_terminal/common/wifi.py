"""Select the platform implementation without loading foreign native APIs."""
import sys
if sys.platform == 'win32':
    from zmala_terminal.windows.wifi import *
else:
    from zmala_terminal.linux.wifi import *
