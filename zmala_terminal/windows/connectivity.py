"""Read Windows network link state through IP Helper without a shell/CIM query."""
import ctypes as C
from ctypes import wintypes as W


class Adapter(C.Structure):
    pass


Adapter._fields_ = [('alignment', C.c_uint64), ('next', C.POINTER(Adapter)), ('name', C.c_char_p),
                   ('unicast', C.c_void_p), ('anycast', C.c_void_p), ('multicast', C.c_void_p),
                   ('dns_servers', C.c_void_p), ('dns_suffix', W.LPWSTR), ('description', W.LPWSTR),
                   ('friendly_name', W.LPWSTR), ('physical_address', C.c_ubyte * 8),
                   ('physical_length', W.DWORD), ('flags', W.DWORD), ('mtu', W.DWORD),
                   ('interface_type', W.DWORD), ('operational_status', C.c_int)]


def network_link_available(wifi_only=False):
    try:
        function = C.WinDLL('iphlpapi').GetAdaptersAddresses
        function.argtypes = [W.ULONG, W.ULONG, C.c_void_p, C.c_void_p, C.POINTER(W.ULONG)]
        function.restype = W.ULONG
        size = W.ULONG(15000)
        for attempt in range(3):
            buffer = C.create_string_buffer(size.value)
            result = function(0, 14, None, buffer, C.byref(size))
            if result == 111:
                continue
            if result == 232:
                return False
            if result:
                return None
            pointer = C.cast(buffer, C.POINTER(Adapter))
            while pointer:
                adapter = pointer.contents
                if adapter.interface_type in ((71,) if wifi_only else (6, 71)) and adapter.operational_status == 1 and adapter.unicast:
                    return True
                pointer = adapter.next
            return False
    except (OSError, AttributeError):
        pass
    return None


def wifi_link_available():
    return network_link_available(wifi_only=True)
