"""Outbound polling agent. A command runs once in a bounded background process."""
import base64
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from configuration import ROOT
from process_job import ProcessJob
from platforms.native_runtime import WINDOWS, process_options


def command_arguments(command, shell, batch_directory=None):
    """Use explicit shell arguments. PowerShell text is encoded; cmd uses a private batch file."""
    if not WINDOWS:
        if shell not in ('sh', 'bash'):
            raise ValueError('Choose sh or bash in the Linux terminal account settings')
        executable = shutil.which(shell)
        if not executable:
            raise FileNotFoundError(f'{shell} is not installed on this terminal')
        return [executable, '-c', command]
    script = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); $OutputEncoding = [Console]::OutputEncoding; $ProgressPreference = 'SilentlyContinue'; $LASTEXITCODE = 0; $script:familyCallSuccess = $true; & {\n" + command + "\n$script:familyCallSuccess = $?\n}; $ok = $?; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not $ok -or -not $familyCallSuccess) { exit 1 }"
    encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    if shell == 'cmd':
        batch = Path(batch_directory) / 'command.cmd'
        batch.write_bytes(('@echo off\r\nchcp 65001 >nul\r\n' + command + '\r\n').encode('utf-8'))
        arguments = ['cmd.exe', '/d', '/c', str(batch)]
    elif shell in ('powershell', 'pwsh'):
        executable = 'powershell.exe'
        if shell == 'pwsh':
            executable = shutil.which('pwsh.exe') or str(Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'PowerShell/7/pwsh.exe')
            if not Path(executable).is_file():
                raise FileNotFoundError('PowerShell 7 is not installed on this terminal')
        arguments = [executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-EncodedCommand', encoded]
    else:
        raise ValueError('Unsupported command shell')
    return arguments


def bounded_output(stdout, stderr, truncated=False):
    """Limit decoded UTF-8 bytes, including replacement characters and errors."""
    remaining, output = 65536, {}
    for name, value in [('stdout', stdout), ('stderr', stderr)]:
        data = value.decode('utf-8', errors='replace').encode('utf-8')
        text = data[:remaining].decode('utf-8', errors='ignore')
        size = len(text.encode('utf-8'))
        output[name] = text
        truncated |= len(data) > size
        remaining -= size
    return output | {'truncated': truncated}


def run_command(command, timeout_seconds, cancelled, shell='powershell'):
    """Drain both pipes concurrently, cap retained output, and kill descendants on completion or cancellation."""
    chunks = {'stdout': bytearray(), 'stderr': bytearray()}
    lock, truncated = threading.Lock(), [False]
    process, job, batch_directory = None, ProcessJob(), None
    status, exit_code = 'failed', None
    try:
        if shell == 'cmd':
            batch_directory = tempfile.TemporaryDirectory(prefix='zmalacall-command-')
        arguments = command_arguments(command, shell, batch_directory.name if batch_directory else None)
        process = subprocess.Popen(arguments,
                                   cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   **process_options())
        job.assign(process)
        def reader(name, stream):
            while data := stream.read(4096):
                with lock:
                    remaining = max(0, 65536 - sum(len(value) for value in chunks.values()))
                    chunks[name].extend(data[:remaining])
                    if len(data) > remaining:
                        truncated[0] = True
            stream.close()
        readers = [threading.Thread(target=reader, args=(name, getattr(process, name)), daemon=True) for name in chunks]
        for thread in readers:
            thread.start()
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None and not cancelled.is_set() and time.monotonic() < deadline:
            cancelled.wait(.1)
        if process.poll() is None:
            status = 'cancelled' if cancelled.is_set() else 'timed_out'
            job.close()
        else:
            exit_code = process.returncode
            status = 'completed' if exit_code == 0 else 'failed'
            job.close()  # A returned command may have left a background child.
        process.wait(timeout=5)
        for thread in readers:
            thread.join(timeout=5)
    except Exception as error:
        job.close()
        if process and process.poll() is None:
            process.kill()
        chunks['stderr'].extend(('Command execution failed (' + type(error).__name__ + '): ' + str(error)).encode('utf-8', errors='replace'))
    finally:
        job.close()
        if batch_directory:
            batch_directory.cleanup()
    return {'status': status, 'exit_code': exit_code} | bounded_output(chunks['stdout'], chunks['stderr'], truncated[0])


class MaintenanceAgent:
    def __init__(self, configuration, interval=3):
        self.configuration, self.interval = configuration, interval
        self.cancelled = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.cancelled.set()

    def submit(self, job_id, result):
        route = '/api/console/result/' + job_id
        try:
            self.configuration.request(route, result)
        except HTTPError as error:
            if error.code not in (400, 404, 409, 413):
                raise
            diagnostic = dict(result, stdout='', stderr='Command ran, but its result was rejected by the server.',
                              status='failed', truncated=True)
            try:
                self.configuration.request(route, diagnostic)
            except HTTPError as retry:
                if retry.code not in (400, 404, 409, 413):
                    raise
                logging.warning('Command result permanently rejected; command will not be rerun')

    def loop(self):
        """Retry an unacknowledged result with its lease; never rerun the command after an HTTP failure."""
        pending = None
        while not self.cancelled.is_set():
            try:
                if pending:
                    job_id, result = pending
                    self.submit(job_id, result)
                    pending = None
                reply = json.loads(self.configuration.request('/api/console/next', {}))
                if reply.get('job') and not self.cancelled.is_set():
                    job = reply['job']
                    if not isinstance(job.get('command'), str) or not 5 <= job.get('timeout_seconds', 0) <= 120:
                        raise ValueError('Invalid maintenance job')
                    result = run_command(job['command'], job['timeout_seconds'], self.cancelled, job.get('shell', 'powershell'))
                    result['lease'] = job['lease']
                    pending = job['id'], result
                    # Submit immediately; do not wait another polling interval.
                    self.submit(job['id'], result)
                    pending = None
            except Exception as error:
                logging.debug('Maintenance polling failed (%s)', type(error).__name__)
            self.cancelled.wait(self.interval)
