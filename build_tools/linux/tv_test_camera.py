"""Continuous camera capture for the opt-in TV evidence tool, never normal calls."""
import json
from pathlib import Path
import time


def capture_stream(args):
    """Drain frames continuously in an isolated child; save a fresh requested frame.

    The parent bounds startup and each request, so a blocked USB read cannot
    hang the test. Keeping the stream warm removes per-photo camera startup.
    """
    import cv2
    folder = Path(args.capture_stream)
    camera = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
    try:
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        warmed = 0
        pending = None
        while True:
            # Read the request before acquiring the next frame, not afterwards.
            request = folder / 'camera-request.json'
            if request.exists():
                pending = json.loads(request.read_text())
                request.unlink()
            ok, frame = camera.read()
            captured = time.monotonic()
            if not ok:
                raise RuntimeError('Camera read failed')
            warmed += 1
            if warmed == 30:
                (folder / 'camera-ready').touch()
            if pending is not None:
                index = int(pending)
                name = f'photo-{index:02d}.jpg'
                if not cv2.imwrite(str(folder / name), frame):
                    raise RuntimeError('Camera write failed')
                receipt = folder / f'capture-{index}.json'
                temporary = receipt.with_suffix('.tmp')
                temporary.write_text(json.dumps({'frame_read_monotonic': captured,
                                                  'saved_monotonic': time.monotonic()}))
                temporary.replace(receipt)
                pending = None
    finally:
        camera.release()
