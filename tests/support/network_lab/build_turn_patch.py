"""Build the isolated lab's pinned upstream TURN packet-framing correction."""
import hashlib
import json
from pathlib import Path
import resource
import signal
import subprocess
import urllib.request

ROOT = Path('/opt/zmala-lab')
SOURCE = ROOT/'turn-sdk'
HASHES = {
    'turn_tcp.cpp': '95c98be983d7d547c88569438b8e7094309c989d4f4ea7b815a47036a425ac31',
    'turn_tcp.h': '77590e754ae896fee4414885d114d99b229333623cd180cfdc8d2438ab600ade',
}


def main():
    version = subprocess.check_output(['dpkg-query', '-W', '-f=${Version}',
                                       'libmediastreamer2-14'], text=True)
    if version.split('+')[0].split(':')[-1] != '5.3.105':
        raise RuntimeError('Requalify the TURN override for SDK version '+version)
    SOURCE.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        url = 'https://raw.githubusercontent.com/BelledonneCommunications/mediastreamer2/5.3.105/src/voip/'+name
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError('Unexpected upstream source hash: '+name)
        (SOURCE/name).write_bytes(data)
    (SOURCE/'original.cpp').write_bytes((SOURCE/'turn_tcp.cpp').read_bytes())
    subprocess.run(['patch', '--batch', '-p0', '-i', str(Path(__file__).with_name('turn-framing.patch'))], cwd=SOURCE, check=True)
    subprocess.run(['g++', '-shared', '-fPIC', '-std=c++17', str(SOURCE/'turn_tcp.cpp'),
                    '-o', str(ROOT/'turn-fix.so'), '-lmediastreamer2', '-lortp', '-lbctoolbox'], check=True)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    results = {}
    for name in ('original', 'turn_tcp'):
        executable = ROOT/('test-'+name)
        subprocess.run(['g++', '-std=c++17', '-I'+str(SOURCE), str(SOURCE/(name+'.cpp')),
                        str(Path(__file__).resolve().parents[2]/'adhoc/turn_parser.cpp'), '-o', str(executable),
                        '-lmediastreamer2', '-lortp', '-lbctoolbox'], check=True)
        # Four-byte reads isolate the original fragmented-padding defect without
        # depending on its separate incomplete-header out-of-bounds read.
        result = subprocess.run([str(executable), *(['4'] if name == 'original' else [])],
                                capture_output=True, text=True, timeout=30)
        results[name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
        original_failure = (result.returncode == -signal.SIGABRT and
                            'packet->length() == frames[count].size()' in result.stderr)
        if (name == 'original' and not original_failure) or (name == 'turn_tcp' and result.returncode != 0):
            raise RuntimeError('TURN framing regression failed: '+name+' '+result.stderr[-1000:])
    (ROOT/'parser-results.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results), flush=True)


if __name__ == '__main__':
    main()
