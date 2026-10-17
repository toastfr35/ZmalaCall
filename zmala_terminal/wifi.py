"""Select the platform implementation without loading foreign native APIs."""
import sys
if sys.platform == 'win32':
    from platforms.windows_wifi import *
else:
    from platforms.linux_wifi import *
