"""One set of server video presets shared by Windows and the C20 terminal."""
from dataclasses import dataclass

FRAME_RATES = (10, 15, 20, 25, 30)


@dataclass(frozen=True)
class VideoSettings:
    resolution: str = '720p'
    fps: int = 15
    upload_kbps: int = 1500
    download_kbps: int = 2000

    @property
    def dimensions(self):
        return {'480p': (640, 480), '720p': (1280, 720), '1080p': (1920, 1080)}[self.resolution]

    @classmethod
    def for_config(cls, config):
        # A resolution change rebuilds the native graph only when idle. 720p
        # is the verified C20 default; Windows shares the server's three choices.
        resolution = config.get('video_resolution', '720p')
        # Old server snapshots used an unsupported 360p SDK preset.
        if resolution == '360p':
            resolution = '480p'
        presets = {'480p': (700, 1000), '720p': (1500, 2000), '1080p': (2500, 3000)}
        if not isinstance(resolution, str) or resolution not in presets:
            raise ValueError('Unsupported video resolution')
        fps = config.get('video_fps', 15)
        if type(fps) is not int or fps not in FRAME_RATES:
            raise ValueError('Unsupported video frame rate')
        upload, download = presets[resolution]
        # Preserve the 15 fps sending budgets, scaling with the selected rate.
        # Receive capacity is independent: a 15 fps sender may receive a 30 fps peer.
        return cls(resolution, fps, (upload * fps + 14) // 15, download * 2)
