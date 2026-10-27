"""Read-only peripheral report snapshots, kept separate from polling and UI dispatch."""


# @llr LLR-TERM-MAINT-018
def collect_peripheral_status(remote=None, power=None, detector=None):
    """Preserve unknown observations; never wake USB or open the camera here."""
    status = getattr(remote, 'status', None)
    if status not in ('connected', 'disconnected', 'unpaired', 'blocked',
                      'bluetooth_unavailable', 'input_unavailable'):
        status = 'unknown'
    battery = getattr(remote, 'battery', None)
    battery = battery if type(battery) is int and 0 <= battery <= 100 else None
    charger = getattr(remote, 'charger_connected', None)
    charger = charger if type(charger) is bool else None
    enabled = power is not None and power.enabled is True
    powered = power.power_state if enabled else None
    powered = powered if type(powered) is bool else None
    try:
        connected = detector.read() if detector else None
    except OSError:
        connected = None
    connected = connected if type(connected) is bool else None
    camera = 'connected' if connected is True else 'disconnected' if connected is False else 'unknown'
    if enabled:
        if power.state == 'error':
            camera = 'error'
        elif power.state in ('starting', 'switching'):
            camera = 'switching'
        elif powered is False:
            camera = 'off'
        elif power.ready is False:
            camera = 'waking'
        elif camera == 'unknown' and powered is True:
            camera = 'on'
    return {'remote_status': status, 'remote_battery': battery,
            'remote_charger_connected': charger, 'camera_powered': powered,
            'camera_connected': connected, 'camera_status': camera}

