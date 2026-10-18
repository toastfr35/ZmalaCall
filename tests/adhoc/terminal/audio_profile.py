"""Profile an isolated SIP audio call; --real-audio explicitly uses room devices.

Use a private test bootstrap and peer. By default this uses file audio. The
real-audio option selects a named USB headset for capture/playback, and prints
its identifiers. It records filter timings and CPU usage, never audio content.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import os
import sys
import time

ROOT = (Path(__file__).resolve().parents[3] / 'zmala_terminal')
sys.path.insert(0, str(ROOT.parent))
from zmala_terminal.common.configuration import Configuration
from zmala_terminal.common.engine import Engine, P, I, S, SDK, encoded, ListNode
from zmala_terminal.common.native_runtime import library


class BoxPlot(C.Structure):
    _fields_ = [(key, C.c_uint64) for key in ('min', 'max', 'sum', 'deviation_sum', 'count')] + [('mean', C.c_double)]


class FilterStats(C.Structure):
    _fields_ = [('name', S), ('elapsed', BoxPlot)]


def ticks():
    fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return int(fields[11]) + int(fields[12])


def thread_ticks():
    result = {}
    for directory in Path('/proc/self/task').iterdir():
        try:
            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            result[directory.name] = (directory.joinpath('comm').read_text().strip(), int(fields[11]) + int(fields[12]))
        except FileNotFoundError:
            pass
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', type=Path, required=True)
    parser.add_argument('--dial', default='phone1')
    parser.add_argument('--profile', default='audio-probe')
    parser.add_argument('--duration', type=float, default=30)
    parser.add_argument('--real-audio', action='store_true')
    parser.add_argument('--device', default='Trust')
    parser.add_argument('--no-echo', action='store_true', help='Headset-only comparison, not a speakerphone setting')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config = Configuration(bootstrap=args.bootstrap, cache=ROOT / 'data' / (args.profile + '-cache.json')).fetch()
    config['terminal_settings'] = {'camera': 'StaticImage: Static picture', 'microphone': '', 'speaker': ''}
    states, received = [], False
    engine = None

    def on_call(call, state, user, domain):
        states.append(state)
        print('Call state:', state, flush=True)
        if state == 1:
            engine.hold_call(call)
            engine.answer()
        elif state in (14, 19):
            engine.hold_call(None)

    engine = Engine(config, on_call, lambda state: None, profile=args.profile)
    original = engine.call_params_enable_video
    engine.call_params_enable_video = lambda params, enabled: original(params, 0)
    if args.no_echo:
        engine.core_enable_echo_cancellation(engine.core, 0)
    if args.real_audio:
        devices = engine.devices()
        selected = {kind: next((device for device in devices[kind] if args.device in device), None)
                    for kind in ('microphone', 'speaker')}
        if not all(selected.values()):
            engine.close()
            raise RuntimeError('Requested headset not found: ' + str(devices))
        engine.apply_settings(selected)
        print('Audio devices:', selected, flush=True)
    else:
        for name, types, values in [('core_set_use_files', [P, I], [engine.core, 1]),
                ('core_set_play_file', [P, S], [engine.core, encoded(SDK / 'share/sounds/linphone/hello8000.wav')])]:
            function = getattr(engine.dll, 'linphone_' + name)
            function.argtypes, function.restype = types, None
            function(*values)
    media = library('mediastreamer2')
    factory_get = engine.dll.linphone_core_get_ms_factory
    factory_get.argtypes, factory_get.restype = [P], P
    factory = factory_get(engine.core)
    media.ms_factory_enable_statistics.argtypes = [P, I]
    media.ms_factory_enable_statistics(factory, 1)
    media.ms_factory_get_statistics.argtypes, media.ms_factory_get_statistics.restype = [P], C.POINTER(ListNode)
    start, connected, baseline = time.monotonic(), None, None
    dialed = False
    report = {'states': states, 'real_audio': args.real_audio, 'echo_enabled': not args.no_echo}
    try:
        while time.monotonic() - start < args.duration + 15:
            engine.iterate()
            if engine.registered and not dialed:
                engine.dial('sip:' + args.dial + '@' + config['sip']['domain'])
                dialed = True
            if engine.call and engine.call_get_state(engine.call) == 8:
                now = time.monotonic()
                received |= engine.media_stats()['audio']['download_kbps'] > 0
                if connected is None:
                    connected = now
                if baseline is None and now - connected > 3:
                    baseline = now, ticks(), thread_ticks()
                    payload = engine.dll.linphone_call_params_get_used_audio_payload_type
                    payload.argtypes, payload.restype = [P], P
                    value = payload(engine.call_get_current_params(engine.call))
                    report['codec'] = (engine.payload_type_get_mime_type(value) or b'').decode()
                if baseline and now - baseline[0] >= args.duration:
                    break
            time.sleep(.02)
        if baseline is None or not received:
            raise RuntimeError('No connected audio stream')
        elapsed = time.monotonic() - baseline[0]
        hz = os.sysconf('SC_CLK_TCK')
        report['sample_seconds'] = round(elapsed, 2)
        report['process_one_core_percent'] = round((ticks() - baseline[1]) / hz / elapsed * 100, 1)
        after = thread_ticks()
        report['threads'] = sorted([{'name': name, 'one_core_percent': round((count - baseline[2][tid][1]) / hz / elapsed * 100, 1)}
            for tid, (name, count) in after.items() if tid in baseline[2]], key=lambda row: row['one_core_percent'], reverse=True)
        # Snapshot before ending: the SDK resets accumulated filter statistics
        # while tearing down the call and rebuilding its idle/ring graph.
        rows, node = [], media.ms_factory_get_statistics(factory)
        while node:
            stat = C.cast(node.contents.data, C.POINTER(FilterStats)).contents
            rows.append({'filter': stat.name.decode(), 'calls': stat.elapsed.count,
                         'total_ms': round(stat.elapsed.sum / 1e6, 2), 'mean_ms': round(stat.elapsed.mean / 1e6, 3),
                         'max_ms': round(stat.elapsed.max / 1e6, 3)})
            node = node.contents.next
        report['filters'] = sorted(rows, key=lambda row: row['total_ms'], reverse=True)
        engine.end()
        stop = time.monotonic() + 2
        while time.monotonic() < stop:
            engine.iterate()
            time.sleep(.02)
    finally:
        engine.close()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'states'}), flush=True)


if __name__ == '__main__':
    main()
