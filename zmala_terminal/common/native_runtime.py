"""Choose native SDK operations without loading foreign platform libraries."""
import sys
from zmala_terminal.common.paths import ROOT as ROOT

WINDOWS = sys.platform == 'win32'
if WINDOWS:
    from zmala_terminal.windows.native_runtime import (
        SDK as SDK, library as library, load_linphone as load_linphone,
        resource as resource, process_options as process_options)
else:
    from zmala_terminal.linux.native_runtime import (
        SDK as SDK, library as library, load_linphone as load_linphone,
        resource as resource, process_options as process_options)
