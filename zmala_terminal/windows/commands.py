"""Windows shell command construction and Unicode output."""
import base64
import os
from pathlib import Path
import shutil

def command_arguments(command, shell, batch_directory=None):
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
