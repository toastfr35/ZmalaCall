"""Live video checks must reject static fallbacks and low frame rates."""
import unittest
from pathlib import Path
import struct
import tempfile
import wave
from tests.terminal.HLT.camera_feed_live import decoded_audio_report, minimum_received_fps


class CameraFrameFloorTests(unittest.TestCase):
    def samples(self, rates):
        return [{'video': {'received_fps': rate}} for rate in rates]

    def test_startup_is_excluded(self):
        self.assertEqual(minimum_received_fps(self.samples([0]*5 + [12, 10, 15]), 10), (10, True))

    def test_static_placeholder_and_dips_fail(self):
        for rates in ([1]*12, [15]*8 + [9, 15], [15]*8 + [0, 15]):
            self.assertFalse(minimum_received_fps(self.samples(rates), 10)[1])

    def test_missing_or_invalid_measurements_fail(self):
        for samples in ([], [{}]*8, self.samples([15]*5 + [float('nan'), 15]),
                        self.samples([15]*5 + [None, 15]), self.samples([15]*5 + ['unknown', 15]),
                        self.samples([15]*5 + [100, 100])):
            self.assertFalse(minimum_received_fps(samples, 10)[1])

    def test_optional_frame_floor_preserves_short_call_checks(self):
        self.assertEqual(minimum_received_fps([], 0), (None, True))

    def test_moving_sender_cannot_pass_with_a_placeholder(self):
        samples = [{'video': {'received_fps': 15, 'sent_fps': 1}}]*12
        self.assertTrue(minimum_received_fps(samples, 10)[1])
        self.assertEqual(minimum_received_fps(samples, 10, 'sent'), (1, False))

    def test_audio_measurement_distinguishes_silence_from_decoded_signal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'received.wav'
            for samples, nonzero, peak in (([0]*80, 0, 0), ([0, 16384, -16384, 0]*20, 40, .5)):
                with wave.open(str(path), 'wb') as recording:
                    recording.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                    recording.writeframes(struct.pack('<80h', *samples))
                report = decoded_audio_report(path)
                self.assertEqual(report['seconds'], .01)
                self.assertEqual(report['nonzero_samples'], nonzero)
                self.assertEqual(report['peak'], peak)
