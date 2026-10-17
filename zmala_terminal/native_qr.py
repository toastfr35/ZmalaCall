"""Select the isolated camera preview implementation for this OS."""
import sys
if sys.platform == 'win32':
    from platforms.windows_qr import NativeQRScanner as NativeQRScanner
else:
    from platforms.linux_qr import NativeQRScanner as NativeQRScanner
