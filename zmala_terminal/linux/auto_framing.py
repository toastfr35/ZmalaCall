"""Conservative group framing policy; coordinates are in the uncropped image.

The detector runs off the media/UI threads. The native adapter exports at most
one thumbnail every two seconds and applies the crop before the preview tee.
"""
import ctypes as C
import logging
import math
import os
from pathlib import Path
import sys
import threading
import time

WIDE = (.5, .5, 1.)


def group_frame(boxes):
    """Return (centre x, centre y, fractional size), preserving aspect ratio."""
    valid = [b for b in boxes if len(b) == 4 and all(math.isfinite(v) for v in b)
             and 0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1]
    if not valid:
        return None
    left, top = min(b[0] for b in valid), min(b[1] for b in valid)
    right, bottom = max(b[2] for b in valid), max(b[3] for b in valid)
    width, height = right - left, bottom - top
    # Twenty percent on each side, with a little extra space above heads.
    size = min(1., max(.5, width * 1.4, height * 1.5))
    cx, cy = (left + right) / 2, (top + bottom) / 2 - height * .05
    return (max(size / 2, min(1 - size / 2, cx)),
            max(size / 2, min(1 - size / 2, cy)), size)


class FramingPolicy:
    def __init__(self):
        self.target = WIDE
        self.candidate = None
        self.last_seen = None
        self.recent = []

    def update(self, boxes, now):
        candidate = group_frame(boxes)
        if candidate is None:
            self.candidate = None
            if self.last_seen is None or now - self.last_seen >= 6:
                self.target = WIDE
            return self.target
        self.last_seen = now
        # Keep a briefly occluded group member in frame rather than tightening
        # around the person the detector happened to find in this sample.
        self.recent = [(t, b) for t, b in self.recent if now - t < 6]
        self.recent.extend((now, b) for b in boxes)
        candidate = group_frame([b for _, b in self.recent])
        old = self.target
        # Widen/recentre immediately if the existing crop would exclude anyone.
        outside = any(b[0] < old[0] - old[2] / 2 or b[2] > old[0] + old[2] / 2
                      or b[1] < old[1] - old[2] / 2 or b[3] > old[1] + old[2] / 2
                      for b in boxes)
        stable = self.candidate is not None and max(abs(a - b) for a, b in zip(candidate, self.candidate)) < .08
        changed = max(abs(a - b) for a, b in zip(candidate, old)) > .06
        if outside or (stable and changed):
            # A newcomer must never trigger an immediate tighter crop.
            if outside and candidate[2] < old[2]:
                size = old[2]
                candidate = (max(size / 2, min(1 - size / 2, candidate[0])),
                             max(size / 2, min(1 - size / 2, candidate[1])), size)
            self.target = candidate
        self.candidate = candidate
        return self.target


class PersonDetector:
    """Pinned COCO SSD MobileNet V2 uint8 model with built-in postprocessing."""
    def __init__(self, model):
        runtime = Path(model).parent.parent / 'framing-runtime/lib'
        for packages in runtime.glob('python*/site-packages'):
            if str(packages) not in sys.path:
                sys.path.append(str(packages))
        import numpy as np
        from ai_edge_litert.interpreter import Interpreter
        self.np = np
        # Pi 4 measurements: two threads halve inference latency while leaving
        # two cores available to decoding/UI; no process-wide affinity changes.
        self.interpreter = Interpreter(model_path=str(model), num_threads=2)
        self.interpreter.allocate_tensors()
        self.input = self.interpreter.get_input_details()[0]
        self.outputs = self.interpreter.get_output_details()
        if tuple(self.input['shape']) != (1, 300, 300, 3) or self.input['dtype'] != np.uint8:
            raise ValueError('Unexpected automatic framing model input')
        if len(self.outputs) != 4:
            raise ValueError('Automatic framing model requires SSD postprocessing')

    def detect(self, rgb, width, height):
        from PIL import Image
        np = self.np
        image = Image.frombytes('RGB', (width, height), rgb)
        # This SSD model expects a resized square input. Letterboxing made
        # seated people too small and missed group members in the room test.
        # Normalized boxes map directly back to the original aspect ratio.
        canvas = image.resize((300, 300), Image.Resampling.BILINEAR)
        self.interpreter.set_tensor(self.input['index'], np.asarray(canvas, dtype=np.uint8)[None])
        self.interpreter.invoke()
        boxes, classes, scores, count = [self.interpreter.get_tensor(o['index']) for o in self.outputs]
        result = []
        for box, category, score in zip(boxes[0][:int(count[0])], classes[0], scores[0]):
            if int(category) != 0 or score < .45:
                continue
            top, left, bottom, right = map(float, box)
            left, right = max(0., left), min(1., right)
            top, bottom = max(0., top), min(1., bottom)
            if right > left and bottom > top:
                result.append((left, top, right, bottom))
        return result


class AutoFraming:
    def __init__(self, plugin, root):
        self.plugin = plugin
        self.model = Path(root) / 'linux/media/models/person.tflite'
        self.enabled = False
        self.closed = threading.Event()
        self.changed = threading.Event()
        self.thread = None
        self.revision = 0
        self.status = 'disabled'
        plugin.zmala_framing_enable.argtypes = [C.c_int]
        plugin.zmala_framing_enable.restype = None
        plugin.zmala_framing_take.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
        plugin.zmala_framing_take.restype = C.c_uint64
        plugin.zmala_framing_target.argtypes = [C.c_uint64, C.c_float, C.c_float, C.c_float]
        plugin.zmala_framing_target.restype = None

    def configure(self, enabled):
        enabled = enabled is True
        if enabled == self.enabled:
            return
        self.enabled = enabled
        self.status = 'waiting' if enabled else 'disabled'
        self.revision += 1
        self.plugin.zmala_framing_enable(int(enabled))
        self.changed.set()
        if enabled and self.thread is None:
            self.thread = threading.Thread(target=self._run, name='person-framing', daemon=True)
            self.thread.start()

    def _run(self):
        # Linux nice applies to this detector thread and its inference workers,
        # never to the UI or real-time media threads in the same process.
        if hasattr(os, 'setpriority'):
            try:
                os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 5)
            except OSError:
                pass
        detector, revision, session = None, -1, 0
        policy = FramingPolicy()
        buffer = (C.c_uint8 * (256 * 256 * 3))()
        width, height = C.c_int(), C.c_int()
        retry_at = 0
        while not self.closed.is_set():
            self.changed.wait(.1)
            self.changed.clear()
            if revision != self.revision:
                revision = self.revision
                policy, session, retry_at = FramingPolicy(), 0, 0
            if not self.enabled or time.monotonic() < retry_at:
                continue
            token = self.plugin.zmala_framing_take(buffer, C.byref(width), C.byref(height))
            if not token:
                continue
            if token >> 32 != session:
                session, policy = token >> 32, FramingPolicy()
            try:
                detector = detector or PersonDetector(self.model)
                start = time.monotonic()
                boxes = detector.detect(bytes(buffer[:width.value * height.value * 3]), width.value, height.value)
                elapsed = time.monotonic() - start
                if self.enabled and revision == self.revision and not self.closed.is_set() and elapsed < 3:
                    target = policy.update(boxes, time.monotonic())
                    self.plugin.zmala_framing_target(token, *target)
                    self.status = 'active'
                    logging.debug('Automatic framing: people=%d inference=%.0fms zoom=%.2fx',
                                 len(boxes), elapsed * 1000, 1 / target[2])
            except Exception:
                logging.exception('Automatic framing unavailable; keeping the full camera view')
                if self.enabled:
                    self.status = 'unavailable'
                self.plugin.zmala_framing_target(token, *WIDE)
                retry_at = time.monotonic() + 30

    def close(self):
        self.configure(False)
        self.closed.set()
        self.changed.set()
        if self.thread:
            # Inference holds no SDK objects. Native library stays strongly
            # referenced by this worker if an unusually slow invocation exits later.
            self.thread.join(timeout=4)
