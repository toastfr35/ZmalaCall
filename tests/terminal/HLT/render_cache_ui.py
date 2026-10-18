# @test T-HLT-011
# @requirements HLR-TERM-UI-012, HLR-TERM-UI-013
# @environment display
# @plan Render actual platform text, portraits and icons under deliberately tiny cache budgets; assert retained pixels survive eviction, oversized images are rejected and cache bytes remain bounded.
# @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

"""Real platform rendering under eviction; no camera, SIP, TV or input control.

Run explicitly with a graphical Python environment (or xvfb-run on Linux).
The hidden Tk root tests retained image lifetime without disturbing the UI.
"""
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from zmala_terminal.common.text_renderer import TextRenderer
from zmala_terminal.common.icons import IconRenderer
from tests.terminal.LLT.test_image_bounds import png, jpeg


def benchmark():
    """Synthetic cache pressure, not a carousel FPS or whole-terminal benchmark."""
    import json
    root = tk.Tk()
    root.withdraw()
    renderer = TextRenderer(root)
    timings = []
    try:
        with tempfile.TemporaryDirectory() as directory:
            for index in range(40):
                path = Path(directory) / f'{index}.png'
                image = tk.PhotoImage(master=root, width=480, height=480)
                image.put('#3465a4', to=(0, 0, 480, 480))
                image.write(str(path), format='png')
                for size in (200, 300, 400, 500, 600):
                    for fast in (False, True):
                        start = time.perf_counter()
                        renderer.portrait(path, size, '#112233', fast=fast)
                        timings.append((time.perf_counter() - start) * 1000)
            caches = [renderer.cache, renderer.portraits, renderer.sources]
            if hasattr(renderer, 'backgrounds'):
                caches.append(renderer.backgrounds)
            result = {'renders': len(timings),
                      'retained_pixel_MiB': round(sum(cache.bytes_used for cache in caches) / 1048576, 2),
                      'p95_render_ms': round(sorted(timings)[int(len(timings) * .95)], 2)}
            if sys.platform == 'linux':
                import resource
                result['peak_RSS_MiB'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
            print(json.dumps(result))
    finally:
        renderer.close()
        root.destroy()


def exercise():
    root = tk.Tk()
    root.withdraw()
    renderer = TextRenderer(root)
    icons = IconRenderer(renderer)
    try:
        # Force frequent eviction using tiny budgets rather than a huge heap.
        renderer.cache.max_bytes = 32000
        renderer.portraits.max_bytes = 100000
        renderer.sources.max_bytes = 100000
        icons.cache.max_bytes = 2000
        usb_icons = [icons.usb_power(powered, '#0e141d') for powered in (True, False, None)]
        assert all((icon.width(), icon.height()) == (30, 22) for icon in usb_icons)
        assert len({str(icon) for icon in usb_icons}) == 3
        if hasattr(renderer, 'backgrounds'):
            renderer.backgrounds.max_bytes = 100000
        visible = []
        with tempfile.TemporaryDirectory() as directory:
            for extension, data in (('png', png(4096, 4096)), ('jpg', jpeg(16000, 16000))):
                oversized = Path(directory) / ('oversized.' + extension)
                oversized.write_bytes(data)
                try:
                    renderer.portrait(oversized, 80, '#112233')
                except OSError:
                    pass
                else:
                    raise AssertionError('Oversized image reached the decoder')
            assert not renderer.sources
            for i in range(45):
                path = Path(directory) / f'{i}.png'
                image = tk.PhotoImage(master=root, width=80, height=100)
                image.put('#3465a4', to=(0, 0, 80, 100))
                image.write(str(path), format='png')
                for fast in (False, True):
                    for size in (48, 160, 200):
                        photo = renderer.portrait(path, size, '#112233', fast=fast)
                        assert (photo.width(), photo.height()) == (round(size * .8), size)
                        if i == 0:
                            visible.append(photo)
                label = renderer.photo(f'Contact {i}: العربية Français', 'Arial', 16,
                                       '#112233', '#ffffff', 220)
                assert label.width() == 220 and label.height() > 0
                if i == 0:
                    visible.append(label)
                icons.callback(18 + i, '#ffffff', '#112233')
                for cache in (renderer.cache, renderer.portraits, renderer.sources, icons.cache):
                    assert cache.bytes_used <= cache.max_bytes
                    assert len(cache) <= cache.limit
            # A single source larger than the entire cache must render uncached.
            renderer.sources.max_bytes = 1
            renderer.sources.clear()
            photo = renderer.portrait(path, 204, '#445566')
            assert photo.height() == 204 and not renderer.sources
            if sys.platform == 'win32':
                # A partially loaded native source must be freed if inspection fails.
                with patch.object(renderer.dll, 'GdipGetImageWidth', return_value=1), \
                        patch.object(renderer.dll, 'GdipDisposeImage', wraps=renderer.dll.GdipDisposeImage) as dispose:
                    try:
                        renderer.portrait(path, 208, '#445566')
                    except RuntimeError:
                        pass
                    else:
                        raise AssertionError('Failed dimension query was accepted')
                    dispose.assert_called_once()
                    assert not renderer.sources
        # Eviction must not blank an image still owned by a widget/frame.
        for photo in visible:
            assert int(root.tk.call('image', 'width', str(photo))) > 0
        renderer.close()
        renderer.close()
        assert not renderer.sources and renderer.sources.bytes_used == 0
        print('Real render cache checks passed: 45 sources, fast/quality resizes, text, icons, oversized bypass, active references and repeated close.')
    finally:
        renderer.close()
        root.destroy()


if __name__ == '__main__':
    benchmark() if '--benchmark' in sys.argv else exercise()
