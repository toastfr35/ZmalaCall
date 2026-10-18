"""Select the platform implementation without loading foreign native APIs."""
import sys
if sys.platform == 'win32':
    from zmala_terminal.windows.process_job import *
else:
    from zmala_terminal.linux.process_job import *
