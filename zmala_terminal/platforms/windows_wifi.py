"""Windows WLAN join; the shared-PC test mode only verifies its existing link."""
import ctypes as C
from ctypes import wintypes as W
import time
import uuid
import xml.etree.ElementTree as ET
from connectivity import network_link_available


class GUID(C.Structure):
    _fields_ = [('a', W.DWORD), ('b', W.WORD), ('c', W.WORD), ('d', C.c_ubyte * 8)]


class Interface(C.Structure):
    _fields_ = [('id', GUID), ('description', W.WCHAR * 256), ('state', C.c_int)]


class SSID(C.Structure):
    _fields_ = [('length', W.DWORD), ('bytes', C.c_ubyte * 32)]


class Connection(C.Structure):
    _fields_ = [('mode', C.c_int), ('profile', W.LPCWSTR), ('ssid', C.c_void_p),
                ('bssids', C.c_void_p), ('bss_type', C.c_int), ('flags', W.DWORD)]


class Attributes(C.Structure):
    _fields_ = [('state', C.c_int), ('mode', C.c_int), ('profile', W.WCHAR * 256), ('ssid', SSID)]


def profile_xml(wifi, name):
    """Encode the SSID as UTF-8 bytes and escape XML fields with ElementTree, not string templates."""
    root = ET.Element('WLANProfile', xmlns='http://www.microsoft.com/networking/WLAN/profile/v1')
    def add(parent, tag, text):
        node = ET.SubElement(parent, tag)
        node.text = text
        return node
    add(root, 'name', name)
    ssid_config = ET.SubElement(root, 'SSIDConfig')
    ssid = ET.SubElement(ssid_config, 'SSID')
    add(ssid, 'hex', wifi['ssid'].encode('utf-8').hex())
    add(ssid, 'name', wifi['ssid'])
    add(ssid_config, 'nonBroadcast', str(wifi['hidden']).lower())
    add(root, 'connectionType', 'ESS')
    add(root, 'connectionMode', 'auto')
    security = ET.SubElement(ET.SubElement(root, 'MSM'), 'security')
    auth = ET.SubElement(security, 'authEncryption')
    protected = wifi['security'] == 'WPA'
    add(auth, 'authentication', 'WPA2PSK' if protected else 'open')
    add(auth, 'encryption', 'AES' if protected else 'none')
    add(auth, 'useOneX', 'false')
    if protected:
        shared = ET.SubElement(security, 'sharedKey')
        add(shared, 'keyType', 'networkKey' if len(wifi['password']) == 64 else 'passPhrase')
        add(shared, 'protected', 'false')
        add(shared, 'keyMaterial', wifi['password'])
    return ET.tostring(root, encoding='unicode')


class WLAN:
    def __init__(self):
        self.dll = C.WinDLL('wlanapi')
        signatures = {
            'WlanOpenHandle': [W.DWORD, C.c_void_p, C.POINTER(W.DWORD), C.POINTER(W.HANDLE)],
            'WlanCloseHandle': [W.HANDLE, C.c_void_p],
            'WlanEnumInterfaces': [W.HANDLE, C.c_void_p, C.POINTER(C.c_void_p)],
            'WlanSetProfile': [W.HANDLE, C.POINTER(GUID), W.DWORD, W.LPCWSTR, W.LPCWSTR, W.BOOL, C.c_void_p, C.POINTER(W.DWORD)],
            'WlanDeleteProfile': [W.HANDLE, C.POINTER(GUID), W.LPCWSTR, C.c_void_p],
            'WlanConnect': [W.HANDLE, C.POINTER(GUID), C.POINTER(Connection), C.c_void_p],
            'WlanQueryInterface': [W.HANDLE, C.POINTER(GUID), C.c_int, C.c_void_p, C.POINTER(W.DWORD), C.POINTER(C.c_void_p), C.c_void_p],
        }
        for name, args in signatures.items():
            function = getattr(self.dll, name)
            function.argtypes, function.restype = args, W.DWORD
        self.dll.WlanFreeMemory.argtypes, self.dll.WlanFreeMemory.restype = [C.c_void_p], None
        self.handle, version = W.HANDLE(), W.DWORD()
        self.check(self.dll.WlanOpenHandle(2, None, C.byref(version), C.byref(self.handle)))

    @staticmethod
    def check(code):
        if code:
            raise OSError(code, 'Windows Wi-Fi operation failed')

    def interfaces(self):
        """Return copies: WLAN owns the original array, which must be freed before returning."""
        pointer = C.c_void_p()
        self.check(self.dll.WlanEnumInterfaces(self.handle, None, C.byref(pointer)))
        try:
            count = W.DWORD.from_address(pointer.value).value
            return [Interface.from_buffer_copy(C.string_at(pointer.value + 8 + index * C.sizeof(Interface), C.sizeof(Interface))) for index in range(count)]
        finally:
            self.dll.WlanFreeMemory(pointer)

    def current_ssid(self, interface):
        pointer, size = C.c_void_p(), W.DWORD()
        code = self.dll.WlanQueryInterface(self.handle, C.byref(interface.id), 7, None, C.byref(size), C.byref(pointer), None)
        if code:
            return None
        try:
            current = Attributes.from_address(pointer.value)
            return bytes(current.ssid.bytes[:current.ssid.length]) if current.state == 1 else None
        finally:
            self.dll.WlanFreeMemory(pointer)

    def close(self):
        self.dll.WlanCloseHandle(self.handle, None)


def forget_wifi(wifi, profile):
    """Delete only this application/profile's connections, including the legacy FamilyCall prefix."""
    name = wifi.get('windows_profile', '')
    if not name.startswith(('ZmalaCall-' + profile + '-', 'FamilyCall-' + profile + '-')):
        return
    wlan = WLAN()
    try:
        for interface in wlan.interfaces():
            code = wlan.dll.WlanDeleteProfile(wlan.handle, C.byref(interface.id), name, None)
            if code not in (0, 1168):
                wlan.check(code)
    finally:
        wlan.close()


def connect_wifi(wifi, profile, mode='existing-link', cancelled=None):
    """Test mode keeps the PC network unchanged; real enrollment rolls back its new profile on failure."""
    if mode == 'existing-link':
        if not network_link_available():
            raise OSError('Connect this PC to a network before testing QR setup')
        return dict(wifi, connection_mode=mode)
    wlan = WLAN()
    name = 'ZmalaCall-' + profile + '-' + uuid.uuid4().hex[:12]
    enrolled = dict(wifi, windows_profile=name, connection_mode=mode)
    try:
        interfaces = wlan.interfaces()
        if not interfaces:
            raise OSError('No Windows Wi-Fi interface is available')
        interface = interfaces[0]
        reason = W.DWORD()
        wlan.check(wlan.dll.WlanSetProfile(wlan.handle, C.byref(interface.id), 2, profile_xml(wifi, name), None, False, None, C.byref(reason)))
        parameters = Connection(0, name, None, None, 1, 0)
        wlan.check(wlan.dll.WlanConnect(wlan.handle, C.byref(interface.id), C.byref(parameters), None))
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if cancelled and cancelled.is_set():
                raise OSError('Wi-Fi setup cancelled')
            if wlan.current_ssid(interface) == wifi['ssid'].encode('utf-8'):
                return enrolled
            time.sleep(.25)
        raise TimeoutError('Wi-Fi did not connect; check the QR code and network')
    except Exception:
        for interface in wlan.interfaces():
            wlan.dll.WlanDeleteProfile(wlan.handle, C.byref(interface.id), name, None)
        raise
    finally:
        wlan.close()
