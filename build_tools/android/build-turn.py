"""Build the Android TURN correction against checksum-pinned SDK ABI headers."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request
import zipfile

SOURCES = {
    'bctoolbox/include/bctoolbox/crypto.h': ('bctoolbox/crypto.h', '84f05b2bdc4e35f3cfeda159b3a3551debc181c57b1f0f68610691184bcd3582'),
    'bctoolbox/include/bctoolbox/list.h': ('bctoolbox/list.h', '9b641156fa7346fb2a7c223d338ff123988187d579ad3f25fb8f5bb7cb78e4c1'),
    'mediastreamer2/src/voip/turn_tcp.h': ('turn_tcp.h', '71651a42d069393b68185bf1b73edc95f519a088aecbc60be93a7a8c93166f44'),
    'ortp/include/ortp/str_utils.h': ('ortp/str_utils.h', '6e396a53cc1d67b633ac01caf3f894ef3263a23cdb8342f3e847f8f510abb569'),
    'ortp/include/ortp/port.h': ('ortp/port.h', 'a8a3bccd2515df4691f238aaa713ae8c05b46d9db7902c640bb4b210c3a67d0a'),
    'bctoolbox/include/bctoolbox/port.h': ('bctoolbox/port.h', '9b103d1e060c136e11b1e503a3e3a0a473a4d3a348cbfe1389286ecf4df810ef'),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--aar', required=True, type=Path)
    parser.add_argument('--ndk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if args.aar.name != 'linphone-sdk-android-5.5.32.aar':
        raise RuntimeError('Requalify the native correction before changing SDK version')
    if hashlib.sha256(args.aar.read_bytes()).hexdigest() != 'ff5756cf7061cae88e251a7be32cd1b5a2069fd01ad594e229b4ed0cacfb48d8':
        raise RuntimeError('SDK binary changed; requalify the native correction')
    include = args.output / 'include'
    for source, (name, digest) in SOURCES.items():
        target = include / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            url = 'https://raw.githubusercontent.com/BelledonneCommunications/linphone-sdk/5.5.32/' + source
            with urllib.request.urlopen(url, timeout=60) as response:
                target.write_bytes(response.read())
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Unexpected SDK source: ' + source)
    header = (include / 'turn_tcp.h').read_text()
    # Preserve the original license and exact packet and socket class layouts.
    trimmed = (header[:header.index('#ifndef MS_TURN_TCP_H')] +
               '#pragma once\n#include <condition_variable>\n#include <list>\n#include <memory>\n#include <string>\n#include <mutex>\n#include <thread>\n#include <queue>\n#include <stdexcept>\n#include "ortp/str_utils.h"\n#include "bctoolbox/crypto.h"\n#define INVALID_SOCKET static_cast<ortp_socket_t>(-1)\n'
               'struct MSTurnContext;\nnamespace ms2 { namespace turn {\n' +
               header[header.index('class Packet {'):header.index('class TurnClient {')] +
               '\n}}\n')
    (include / 'turn-packet.h').write_text(trimmed)
    platform = 'windows-x86_64' if os.name == 'nt' else 'linux-x86_64'
    compiler = args.ndk / 'toolchains/llvm/prebuilt' / platform / 'bin' / ('clang++.exe' if os.name == 'nt' else 'clang++')
    with zipfile.ZipFile(args.aar) as archive:
        for abi, target in [('arm64-v8a', 'aarch64-linux-android28'), ('x86_64', 'x86_64-linux-android28')]:
            libs = args.output / 'sdk' / abi
            libs.mkdir(parents=True, exist_ok=True)
            for name in ('libmediastreamer2.so', 'libortp.so', 'libbctoolbox.so', 'libc++_shared.so'):
                (libs / name).write_bytes(archive.read('jni/' + abi + '/' + name))
            output = args.output / 'jniLibs' / abi
            output.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(compiler), '--target=' + target, '-shared', '-fPIC', '-std=c++17',
                            '-O2', '-Wl,-z,global', '-Wl,-z,max-page-size=16384',
                            '-Wl,-soname,libzmala_turn.so', '-Wl,--no-undefined', '-nostdlib++',
                            '-I' + str(include), '-I' + str(root), str(root / 'zmala_phone/app/src/main/cpp/turn-framing.cpp'),
                            '-L' + str(libs), '-lmediastreamer2', '-lortp', '-lbctoolbox', '-lc++_shared',
                            '-o', str(output / 'libzmala_turn.so')], check=True)
            test_output = args.output / 'testJniLibs' / abi
            test_output.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(compiler), '--target=' + target, '-shared', '-fPIC', '-std=c++17',
                            '-O2', '-Wl,-z,max-page-size=16384', '-nostdlib++',
                            '-I' + str(include), str(root / 'tests/support/android/turn-parser.cpp'),
                            '-L' + str(output), '-lzmala_turn', '-L' + str(libs),
                            '-lmediastreamer2', '-lortp', '-lc++_shared', '-ldl',
                            '-o', str(test_output / 'libturn_test.so')], check=True)


if __name__ == '__main__':
    main()
