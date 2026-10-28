"""Linux portrait conversion; invoked as a bounded server subprocess."""
import argparse
from pathlib import Path
from PIL import Image, ImageOps


# @llr LLR-SRV-DIR-033, LLR-SRV-DIR-035
def convert(source, destination):
    Image.MAX_IMAGE_PIXELS = 16000000
    with Image.open(source) as image:
        if image.width * image.height > 16000000 or max(image.size) > 8192:
            raise ValueError('Photo dimensions exceed the supported limit')
        if image.format == 'GIF':
            convert_gif(image, destination)
            return
        image = ImageOps.exif_transpose(image)
        image.thumbnail((480, 480), Image.Resampling.LANCZOS)
        image.convert('RGBA').save(destination, format='PNG')


# @llr LLR-SRV-DIR-033, LLR-SRV-DIR-035
def convert_gif(image, destination):
    """Composite disposal/partial frames before resizing; omit repeat metadata."""
    if image.width != image.height or not 480 <= image.width <= 720:
        raise ValueError('GIF must be square, 480–720 pixels per side')
    frames, durations = [], []
    for index in range(73):
        try:
            image.seek(index)
        except EOFError:
            break
        delay = image.info.get('duration', 100) or 100
        if index == 72 or not 20 <= delay <= 2000 or sum(durations) + delay > 5000:
            raise ValueError('GIF must have 2–72 frames and last at most 5 seconds')
        # Pillow composites each GIF frame, including its disposal method.
        frame = image.convert('RGBA')
        background = Image.new('RGB', frame.size, '#111827')
        background.paste(frame, mask=frame.getchannel('A'))
        frames.append(background.resize((480, 480), Image.Resampling.LANCZOS))
        durations.append(delay)
    if len(frames) < 2:
        raise ValueError('Choose an animated GIF with at least two frames')
    # Standardize every accepted source to 40 timeline frames over two seconds.
    # GIF may combine identical adjacent frames; their 50 ms slots remain intact.
    total = sum(durations)
    timeline, source_index, boundary = [], 0, durations[0]
    for index in range(40):
        position = min(total - 1, index * total / 40)
        while position >= boundary and source_index < len(frames) - 1:
            source_index += 1
            boundary += durations[source_index]
        timeline.append(frames[source_index])
    timeline[-1] = frames[-1]  # Always finish on the supplied resting pose.
    timeline[0].save(destination, format='GIF', save_all=True, append_images=timeline[1:],
                     duration=50, disposal=2, optimize=False)
    if Path(destination).stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Converted GIF exceeds 16 MiB')
    with Image.open(destination) as output:
        if not 2 <= output.n_frames <= 40:
            raise ValueError('GIF must contain at least two distinct frames')
        for index in range(output.n_frames):
            output.seek(index)
            if not 20 <= output.info.get('duration', 100) <= 2000:
                raise ValueError('Combined identical GIF frames exceed the timing limit')



# @llr LLR-SRV-DIR-035
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-Source', required=True)
    parser.add_argument('-Destination', required=True)
    args = parser.parse_args()
    convert(args.Source, args.Destination)
