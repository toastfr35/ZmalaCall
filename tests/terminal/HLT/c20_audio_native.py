# @test T-HLT-034
# @requirements HLR-TERM-AUDIO-001, HLR-TERM-POWER-008
# @environment hardware
# @plan With the terminal idle and its service stopped, power on the C10 or C20 and run two isolated SDK cores over loopback. Route the receiver initially to HDMI, place an incoming audio call, bind the pending call to C10 or C20 and answer. Assert both effective native routes remain C10 or C20 after streams start. The sender uses file audio and no credentials, recording or external destination.
# @pass Both connected call routes identify Nuroum C10 or C20; every call/core is released. This verifies native routing, not acoustic quality, video or physical wake timing.

from pathlib import Path
import sys
import time
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.linphone_api import LinphoneAPI, P, S, I, CALL_CB
from zmala_terminal.common.native_runtime import library
from zmala_terminal.linux.media import bind_call_audio
from zmala_terminal.linux.nuroum import audio_card


def main():
    model = audio_card()
    cores = []
    temporary = tempfile.TemporaryDirectory(prefix="zmala-c20-audio-")
    callbacks = []
    try:
        for sender in (True, False):
            api = LinphoneAPI()
            api.load_api()
            api.bctbx = library('bctoolbox')
            api.bctbx.bctbx_list_free.argtypes = [P]
            api.bctbx.bctbx_list_free.restype = None
            data = Path(temporary.name) / str(len(cores))
            data.mkdir()
            for kind in ('config', 'data', 'download', 'cache'):
                function = getattr(api.dll, 'linphone_factory_set_'+kind+'_dir')
                function.argtypes, function.restype = [P, S], None
                function(api.factory_get(), str(data).encode())
            api.started = False
            api.core = api.factory_create_core_3(api.factory_get(), None, None, None)
            api.call = None
            cores.append(api)
            transports = api.transports_new()
            api.transports_set_udp_port(transports, -1)
            for kind in ('tcp', 'tls', 'dtls'):
                getattr(api, 'transports_set_'+kind+'_port')(transports, 0)
            assert api.core_set_transports(api.core, transports) == 0
            api.transports_unref(transports)
            api.core_enable_video_capture(api.core, 0)
            api.core_enable_video_display(api.core, 0)
            api.core_set_ring(api.core, None)
            api.core_set_ringback(api.core, None)
            if sender:
                use_files = api.dll.linphone_core_set_use_files
                use_files.argtypes, use_files.restype = [P, I], None
                use_files(api.core, 1)
            assert api.core_start(api.core) == 0
            api.started = True
            api.core_set_network_reachable(api.core, 1)
        sender, receiver = cores
        def incoming(core, call, state, message):
            if state == 1:
                receiver.call = receiver.call_ref(call)
        callback = CALL_CB(incoming)
        cbs = receiver.factory_create_core_cbs(receiver.factory_get())
        receiver.core_cbs_set_call_state_changed(cbs, callback)
        receiver.core_add_callbacks(receiver.core, cbs)
        callbacks.extend([callback, cbs])
        receiver.core_cbs_unref(cbs)
        # Deliberately reproduce a pending call with an obsolete HDMI output.
        devices = receiver.core_get_extended_audio_devices(receiver.core)
        node, hdmi = devices, None
        while node:
            device = node.contents.data
            name = receiver.audio_device_get_id(device) or b''
            if b'hdmi' in name.lower():
                hdmi = name
                receiver.core_set_default_output_audio_device(receiver.core, device)
            receiver.audio_device_unref(device)
            node = node.contents.next
        receiver.bctbx.bctbx_list_free(devices)
        assert hdmi, 'An HDMI device is required to reproduce this regression'
        port = receiver.dll.linphone_core_get_sip_port
        port.argtypes, port.restype = [P], I
        address = sender.address_new(('sip:probe@127.0.0.1:'+str(port(receiver.core))).encode())
        params = sender.core_create_call_params(sender.core, None)
        sender.call_params_enable_video(params, 0)
        call = sender.core_invite_address_with_params(sender.core, address, params)
        sender.call = sender.call_ref(call) if call else None
        sender.call_params_unref(params)
        sender.address_unref(address)
        assert sender.call
        def pump_until(predicate):
            deadline = time.monotonic() + 10
            while not predicate() and time.monotonic() < deadline:
                for api in cores: api.core_iterate(api.core)
                time.sleep(.02)
            assert predicate(), 'Native loopback call timed out'
        pump_until(lambda: receiver.call is not None)
        before = receiver.call_get_output_audio_device(receiver.call)
        assert before and b'hdmi' in receiver.audio_device_get_id(before).lower()
        bind_call_audio(receiver)
        params = receiver.core_create_call_params(receiver.core, receiver.call)
        receiver.call_params_enable_video(params, 0)
        result = receiver.call_accept_with_params(receiver.call, params)
        receiver.call_params_unref(params)
        assert result == 0
        pump_until(lambda: receiver.call_get_state(receiver.call) == 8)
        for direction in ('input', 'output'):
            device = getattr(receiver, 'call_get_'+direction+'_audio_device')(receiver.call)
            name = receiver.audio_device_get_id(device) or b''
            assert ('Nuroum '+model).encode() in name, (direction, name)
            print(direction + ': ' + name.decode())
        print('PASS: HDMI pending call rebound to '+model+' before connected streams')
    finally:
        for api in cores:
            if api.call:
                api.call_terminate(api.call)
                api.call_unref(api.call)
            if api.started: api.core_stop(api.core)
            api.core_unref(api.core)
        temporary.cleanup()


if __name__ == '__main__':
    main()
