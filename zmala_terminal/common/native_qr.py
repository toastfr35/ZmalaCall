"""Select the isolated camera preview implementation for this OS."""
import sys
if sys.platform == 'win32':
    from zmala_terminal.windows.qr import NativeQRScanner as NativeQRScanner
else:
    from zmala_terminal.linux.qr import NativeQRScanner as NativeQRScanner
