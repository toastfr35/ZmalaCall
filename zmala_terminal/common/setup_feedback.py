"""Bounded setup messages: raw QR values and network diagnostics never reach the UI."""

# @llr LLR-TERM-SETUP-028, LLR-TERM-SETUP-029
MESSAGES = {
    'invalid_wifi_qr': 'Invalid Wi-Fi QR code. Scan a Wi-Fi sharing code or the printed Wi-Fi code.',
    'invalid_server_qr': 'Invalid server QR code. Scan the setup code made for this terminal.',
    'connecting': 'QR code read. Connecting to Wi-Fi…',
    'server_connecting': 'QR code read. Connecting to the server…',
    'network_not_found': 'Wi-Fi network not found. Check the network name and move closer to the router.',
    'authentication_failed': 'Wi-Fi authentication failed. Check the password and the router security settings.',
    'permission_denied': 'Wi-Fi setup is not permitted on this terminal. Ask your helper to check its configuration.',
    'wifi_unavailable': 'Wi-Fi is off or unavailable. Ask your helper to enable the wireless adapter.',
    'address_failed': 'The router did not provide a network address. Check the router and try again.',
    'timed_out': 'Wi-Fi connection timed out. Check the signal and router, then try again.',
    'connection_failed': 'Could not connect to Wi-Fi. Check the network details and try again.',
    'camera_failed': 'The camera could not scan the code. Check its connection; scanning will retry.',
}


# @llr LLR-TERM-SETUP-029, LLR-TERM-NET-004
class WifiSetupError(OSError):
    """Expose only an allowlisted reason, including in exception strings."""
    def __init__(self, reason):
        self.reason = reason if reason in MESSAGES else 'connection_failed'
        super().__init__('Wi-Fi setup failed (' + self.reason + ')')
