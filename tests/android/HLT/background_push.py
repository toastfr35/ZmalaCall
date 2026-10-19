# @test A-HLT-004
# @requirements HLR-AND-CALL-003
# @environment hardware
# @plan On an explicitly selected enrolled phone and idle Pi, background and reclaim the app process, send an authorized real SIP call through the Pi and Firebase, and inspect the package's native alert before caller cancellation. Use trusted SIP TLS and encrypted ICE SDP when the Pi's secure policy is present, otherwise the LAN UDP fixture. Repeat with the screen off or forced Doze; restore Doze and charging overrides afterward. Credentials remain on the Pi. User answering and media quality are separate checks.
# @pass The app process starts through FCM, a notification or incoming activity appears within 15 seconds, and the alert disappears after acknowledged CANCEL or after a user answer followed by acknowledged BYE. Output distinguishes these paths; neither establishes media quality. A skipped, unavailable or timed-out run is not a pass.
"""Opt-in physical push check; does not clear enrollment or use Android Force stop."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from build_tools.server_installer.backend import Deployment  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--fingerprint', required=True)
    parser.add_argument('--serial', required=True)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--caller', required=True)
    parser.add_argument('--recipient', required=True)
    parser.add_argument('--mode', choices=('background', 'screen-off', 'doze'), default='background')
    parser.add_argument('--https-origin', help='Trusted public HTTPS origin for a secure deployment')
    args = parser.parse_args()

    def adb(*command):
        return subprocess.check_output([args.adb, '-s', args.serial, *command], text=True, encoding="utf-8", errors="replace", timeout=15).strip()

    target = Deployment(args.host, emit=lambda message: None)
    target.key = args.fingerprint
    remote = '/home/zmalaserver/.zmala-push-check.cjs'
    channel = None
    try:
        target.check()
        # Read the operator password from stdin; never retain it in a test artifact.
        password = sys.stdin.readline().strip()
        assert password, 'Supply the administrator password through stdin.'
        check = """(async()=>{const s=require('./data/server.json');const base='http://127.0.0.1:'+s.http_port;const password=require('node:fs').readFileSync(0,'utf8').trim();const r=await fetch(base+'/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password,session_token:true})});const {session_token}=await r.json();if(!session_token)throw Error('Admin login failed');try{const live=await fetch(base+'/api/admin/live',{headers:{Authorization:'Bearer '+session_token}}).then(r=>r.json());if(live.sip_status.active_calls)throw Error('A call is active');console.log('Server idle');}finally{await fetch(base+'/api/auth/logout',{method:'POST',headers:{Authorization:'Bearer '+session_token,'Content-Type':'application/json'},body:'{}'});}})().catch(e=>{console.error(e.message);process.exitCode=1;})"""
        if args.https_origin:
            from urllib.parse import urlsplit
            import json
            parsed = urlsplit(args.https_origin)
            assert parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and parsed.path in ('', '/') and not parsed.query and not parsed.fragment
            check = check.replace("'http://127.0.0.1:'+s.http_port", json.dumps(args.https_origin.rstrip('/')))
        print(target.command('cd /opt/zmalacall-server/current/zmala_server && node -e '+shlex.quote(check), password), flush=True)
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        time.sleep(1)
        adb('shell', 'am', 'kill', 'org.zmala.phone')
        # pidof returns 1 when no process exists, which is the expected precondition.
        before = subprocess.run([args.adb, '-s', args.serial, 'shell', 'pidof', 'org.zmala.phone'], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        assert not before.stdout.strip(), 'App process still alive; no reclaimed-process claim.'
        if args.mode != 'background':
            adb('shell', 'input', 'keyevent', 'KEYCODE_SLEEP')
        if args.mode == 'doze':
            adb('shell', 'dumpsys', 'battery', 'unplug')
            print(adb('shell', 'dumpsys', 'deviceidle', 'force-idle'), flush=True)
        with target.client.open_sftp() as ftp:
            ftp.put(str(ROOT/'tests/support/android/push-caller.cjs'), remote)
        channel = target.client.get_transport().open_session()
        channel.settimeout(40)
        channel.exec_command('cd /opt/zmalacall-server/current/zmala_server && node '+shlex.quote(remote)+' '+shlex.quote(args.caller)+' '+shlex.quote(args.recipient))
        deadline = time.monotonic()+15
        found = False
        while time.monotonic() < deadline:
            notifications = adb('shell', 'dumpsys', 'notification')
            activity = adb('shell', 'dumpsys', 'activity', 'activities')
            found = any('NotificationRecord(' in line and 'pkg=org.zmala.phone ' in line for line in notifications.splitlines()) or any('topResumedActivity=' in line and 'org.zmala.phone/.MainActivity' in line for line in activity.splitlines())
            if found:
                print('Incoming alert observed with previously absent app process:', args.mode, flush=True)
                break
            time.sleep(0.5)
        output = channel.makefile().read().decode()
        errors = channel.makefile_stderr().read().decode()
        code = channel.recv_exit_status()
        print(output, flush=True)
        if errors:
            print(errors, flush=True)
        assert found, 'No incoming notification/activity within 15 seconds.'
        assert code == 0, 'SIP cancellation did not complete.'
        time.sleep(2)
        notifications = adb('shell', 'dumpsys', 'notification')
        assert not any('NotificationRecord(' in line and 'pkg=org.zmala.phone ' in line for line in notifications.splitlines()), 'Alert remained after cancellation.'
        print('PASS: real Firebase wake and signaling cleanup; see RESULT for cancel versus answer. Media not tested.', flush=True)
    finally:
        if args.mode == 'doze':
            adb('shell', 'dumpsys', 'deviceidle', 'unforce')
            adb('shell', 'dumpsys', 'battery', 'reset')
        if channel:
            if not channel.exit_status_ready():
                channel.makefile().read()
                channel.recv_exit_status()
            channel.close()
        if target.client:
            target.command('rm -f '+shlex.quote(remote))
        target.close()


if __name__ == '__main__':
    main()
