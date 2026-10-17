"""Isolated native QR capture; only decoded QR text travels to the terminal."""
import argparse
import json
import os
import sys
import threading
import time


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', type=int, required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--camera')
    parser.add_argument('--image')
    args = parser.parse_args()
    # Reserve stdout for JSON, including when the SDK writes directly to fd 1.
    output = os.fdopen(os.dup(1), 'w', encoding='utf-8', buffering=1)
    os.dup2(2, 1)
    from native_qr import NativeQRScanner
    stopped = threading.Event()
    def controls():
        for line in sys.stdin.buffer:
            if line.strip() == b'stop':
                break
        stopped.set()
    threading.Thread(target=controls, daemon=True).start()
    def qr(value):
        output.write(json.dumps({'type': 'qr', 'value': value}, ensure_ascii=True) + '\n')
    scanner = NativeQRScanner(qr, args.window, args.profile, args.camera)
    try:
        if args.image:
            if args.camera != 'StaticImage: Static picture':
                raise ValueError('A test image requires the static camera')
            scanner.set_static_picture(args.image)
        while not stopped.is_set():
            scanner.iterate()
            time.sleep(.02)
    finally:
        scanner.close()
        output.close()


if __name__ == '__main__':
    run()
