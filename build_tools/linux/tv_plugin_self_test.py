"""Brand-neutral TV driver experiment runner and offline evidence report.

This is a development tool, not automatic TV qualification. Command acceptance,
reported state and photographed display remain separate pieces of evidence.
"""
import base64
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import time
import zipfile


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_sequence(invoke, snapshot, inputs, delay=5, sleep=time.sleep, clock=time.monotonic, observation_count=3):
    """Inject bounded driver/camera operations so the sequence is independently testable."""
    if observation_count not in (1, 3):
        raise ValueError('observation_count must be 1 or 3')
    report = {'schema_version': 1, 'sequence': 'power-and-directed-input-transitions-v3', 'started_at': utc_now(), 'steps': [], 'visual_verdict': 'Not assessed',
              'restoration': 'Not attempted', 'observation_count': observation_count}
    capabilities = set()
    initial = {}
    photo_number = 0

    def call(method, *args):
        if method not in ('get_model', 'get_capabilities') and method not in capabilities:
            return {'status': 'unsupported', 'value': None}
        return invoke(method, list(args))

    def step(label, method=None, args=(), restoring=False):
        nonlocal photo_number
        started = clock()
        previous = report['steps'][-1] if report['steps'] else None
        result = call(method, *args) if method else {'status': 'observation', 'value': None}
        completed = clock()
        command_seconds = completed - started
        record = {'label': label, 'timestamp': utc_now(), 'method': method,
                  'arguments': list(args), 'result': result,
                  'power': {'status': 'not observed', 'value': None},
                  'input': {'status': 'not observed', 'value': None},
                  'command_started_monotonic': started, 'command_completed_monotonic': completed,
                  'gap_since_previous_command_seconds': round(started - previous['command_completed_monotonic'], 3) if previous else None,
                  'command_seconds': round(command_seconds, 3), 'delay_seconds': delay if method else 0,
                  'restoring': restoring}
        report['steps'].append(record)
        record['observations'] = []
        offsets = tuple(delay * n for n in range(1, observation_count + 1)) if method and result['status'] != 'unsupported' else (0,)
        for offset in offsets:
            # Absolute deadlines avoid accumulating the duration of previous
            # camera/status operations into subsequent observation times.
            sleep(max(0, completed + offset - clock()))
            observation = {'target_seconds': offset, 'started_seconds': round(clock() - completed, 3)}
            record['observations'].append(observation)
            photo_number += 1
            try:
                observation['photo'] = snapshot(photo_number)
                observation['photo_at'] = utc_now()
                observation['photo_completed_seconds'] = round(clock() - completed, 3)
            except Exception as error:
                observation['photo_error'] = type(error).__name__
            observation['power_query_started_seconds'] = round(clock() - completed, 3)
            observation['power'] = call('get_power_status')
            observation['input_query_started_seconds'] = round(clock() - completed, 3)
            observation['input'] = call('get_current_input')
            observation['observed_at'] = utc_now()
            observation['completed_seconds'] = round(clock() - completed, 3)
            record.update(observation)  # Overview uses the last observation only.
        expected = None
        actual = None
        if method in ('set_power_on', 'set_power_off'):
            expected, actual = method == 'set_power_on', record['power'].get('value')
        elif method == 'set_current_input':
            expected, actual = args[0], record['input'].get('value')
        record['expected_state'] = expected
        record['reported_state_comparison'] = ('not applicable' if method is None else
            'unsupported' if result['status'] == 'unsupported' else
            'unknown' if actual is None else 'matches' if actual == expected else 'differs')
        return record

    try:
        report['model'] = call('get_model')
        cap_result = call('get_capabilities')
        report['capabilities_result'] = cap_result
        capabilities = set(cap_result.get('value') or [])
        report['capabilities'] = sorted(capabilities)
        baseline = step('Initial TV state')
        initial = {'power': baseline['power'].get('value'), 'input': baseline['input'].get('value')}
        report['initial_state'] = initial
        if 'photo_error' in baseline:
            initial = {}  # Nothing has changed; do not issue restoration commands.
            raise RuntimeError('Initial camera observation failed')
        # Without a known power baseline we cannot restore a power cycle safely.
        if not isinstance(initial['power'], bool):
            report['sequence_status'] = 'Observation only: initial power unknown'
            return report
        step('Initial power off', 'set_power_off')
        step('Power on', 'set_power_on')
        step('Repeat power on (must remain on)', 'set_power_on')
        for source in inputs:
            step('Select input ' + source, 'set_current_input', (source,))
            step('Repeat selection of ' + source, 'set_current_input', (source,))
            step('Standby from input ' + source, 'set_power_off')
            step('Repeat standby from ' + source, 'set_power_off')
            step('Wake after standby from ' + source, 'set_power_on')
            step('Re-select ' + source + ' after wake', 'set_current_input', (source,))
        # Every directed pair is exercised, without assuming wake preserves input.
        for origin in inputs:
            for destination in inputs:
                if origin != destination:
                    step('Prepare transition from ' + origin, 'set_current_input', (origin,))
                    step('Switch ' + origin + ' → ' + destination, 'set_current_input', (destination,))
        if not inputs:
            step('Power off', 'set_power_off')
            step('Repeat power off (must remain off)', 'set_power_off')
            step('Wake after standby', 'set_power_on')
        report['sequence_status'] = 'Sequence finished; inspect photos and reported states'
    except (Exception, KeyboardInterrupt) as error:
        report['sequence_status'] = 'Interrupted: ' + type(error).__name__
    finally:
        if isinstance(initial.get('power'), bool):
            try:
                # Wake before restoring a source: many TVs cannot select it in standby.
                if initial.get('input') is not None:
                    step('Restore: wake for original input', 'set_power_on', restoring=True)
                    step('Restore original input', 'set_current_input', (initial['input'],), restoring=True)
                step('Restore original power', 'set_power_on' if initial['power'] else 'set_power_off', restoring=True)
                report['restoration'] = 'Attempted; inspect final state and photo'
                if initial.get('input') is None:
                    report['restoration'] += '; original input unknown, source not restored'
            except (Exception, KeyboardInterrupt) as error:
                report['restoration'] = 'Incomplete: ' + type(error).__name__
        report['finished_at'] = utc_now()
    return report


def render_html(report, folder):
    """Embed photos so the HTML remains useful after extraction or sharing alone."""
    def escaped(value):
        return html.escape(str(value))

    notes = ''.join('<li>' + escaped(note) + '</li>' for note in report.get('review_notes', []))
    cards = []
    overview = []
    for index, step in enumerate(report['steps'], 1):
        photos = []
        for observation in step.get('observations', [step]):
            photo = ''
            if observation.get('photo'):
                path = folder / observation['photo']
                if path.is_file():
                    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
                    photo = f'<img alt="TV photograph after step {index}" src="data:image/jpeg;base64,{encoded}">'
            title = f'Observation at +{observation.get("target_seconds", 0)} seconds'
            timing = f'Capture started +{observation.get("started_seconds", 0):.2f}s; completed +{observation.get("photo_completed_seconds", 0):.2f}s'
            if 'frame_read_seconds' in observation:
                timing += f'; frame read +{observation["frame_read_seconds"]:.2f}s'
            values = json.dumps({'power': observation.get('power'), 'input': observation.get('input'),
                                 'power_query_started_seconds': observation.get('power_query_started_seconds'),
                                 'input_query_started_seconds': observation.get('input_query_started_seconds'),
                                 'queries_completed_seconds': observation.get('completed_seconds')}, indent=2)
            photos.append(f'<h3>{escaped(title)}</h3><p>{escaped(timing)}</p>' +
                          (photo or '<p class="warning">Photo unavailable</p>') + f'<pre>{escaped(values)}</pre>')
        photo = ''.join(photos)
        result = step['result']
        overview.append(f'<tr><td><a href="#step-{index}">{index}</a></td><td>{escaped(step["label"])}</td>'
                        f'<td>{escaped(result.get("value"))} ({escaped(result["status"])})</td>'
                        f'<td>{escaped(step["power"].get("value"))}</td><td>{escaped(step["input"].get("value"))}</td>'
                        f'<td>{escaped(step.get("reported_state_comparison", "not assessed"))}</td></tr>')
        details = json.dumps({'action': step['method'], 'arguments': step['arguments'],
                              'result': result, 'reported_power': step['power'],
                              'reported_input': step['input']}, indent=2)
        cards.append(f'''<section id="step-{index}"><h2>{index}. {escaped(step['label'])}</h2>
<p>{escaped(step['timestamp'])} · Command: {step['command_seconds']:.3f}s · Observation interval: {step['delay_seconds']}s ({len(step.get("observations", []))} samples)</p>
<p>Gap since preceding command completed: {escaped(step.get("gap_since_previous_command_seconds"))}s</p>
{photo or '<p class="warning">No photo: '+escaped(step.get('photo_error', 'unavailable'))+'</p>'}
<details open><summary>Plugin observations</summary><pre>{escaped(details)}</pre></details>
<p class="review">Visual review: compare the picture with the requested action. No automatic pass is claimed.</p></section>''')
    return f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TV plugin self-test</title><style>
body{{font:16px system-ui,sans-serif;background:#10151e;color:#e6edf5;margin:0 auto;max-width:1000px;padding:24px}}
h1,h2{{line-height:1.3}}section{{background:#1c2532;border:1px solid #354456;border-radius:12px;padding:20px;margin:24px 0}}
img{{width:100%;height:auto;border-radius:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#111923;padding:14px}}
p{{line-height:1.6}}.warning{{color:#ffd38a}}.review{{color:#afc8e7}}summary{{cursor:pointer}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{border:1px solid #354456;padding:8px;text-align:left}}a{{color:#8bc7ff}}.table{{overflow-x:auto}}code{{overflow-wrap:anywhere}}
</style><h1>TV plugin self-test</h1>
<p><strong>Model:</strong> {escaped(report.get('model', {}).get('value'))}<br>
<strong>Started:</strong> {escaped(report['started_at'])}<br>
<strong>Sequence:</strong> {escaped(report.get('sequence_status', 'Not completed'))}<br>
<strong>Restoration:</strong> {escaped(report['restoration'])}</p>
<p class="warning">This is an evidence record, not automatic qualification. A successful command does not prove that the TV changed. Times measure the API call, not time to visible completion. Photos may show private household content.</p>
<p><strong>Visual review:</strong> {escaped(report.get("visual_verdict", "Not assessed"))}</p><ul>{notes}</ul>
<p>Capabilities: {escaped(', '.join(report.get('capabilities', [])))}</p>
<div class="table"><table><thead><tr><th>Step</th><th>Action</th><th>Command result</th><th>Power</th><th>Input</th><th>Reported state vs request</th></tr></thead><tbody>{''.join(overview)}</tbody></table></div>
{''.join(cards)}</html>'''


def package_report(report, folder, output):
    """Create exclusively, with private permissions and no configuration or raw logs."""
    folder = Path(folder)
    (folder / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (folder / 'index.html').write_text(render_html(report, folder), encoding='utf-8')
    output = Path(output)
    with output.open('xb') as target:
        output.chmod(0o600)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.iterdir()):
                if path.name in ('index.html', 'report.json') or (path.name.startswith('photo-') and path.suffix == '.jpg'):
                    archive.write(path, path.name)
    return output
