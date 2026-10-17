# Automatic framing (experimental)

Enable **Terminals → Video & audio → Automatic framing** for a Pi C20 terminal.
The setting is per terminal, defaults off, and takes effect during a call when
the terminal receives its next configuration update (normally within two seconds).
Windows currently reports this feature as unsupported and sends its normal view.

## Behaviour

The terminal detects people in the uncropped camera image every two seconds.
It frames the whole group, preserves the image's aspect ratio and leaves about
20% margin (slightly more above heads). Digital zoom is limited to 1–2×.
Small changes are ignored; zooming in requires two consistent observations.
An additional person outside the crop immediately requests a wider frame.
Pan and zoom ease toward the requested frame over about two seconds.

Brief missed detections hold the previous framing. A briefly occluded group
member remains in the framing calculation for six seconds. Six seconds without people
returns to the full view. A stalled or failed detector also returns to the full
view, with an independent eight-second native watchdog. Switching off stops new
detections and smoothly restores the full view. A new call starts wide and cannot
use a previous call's detection results.

At 2×, a 1080p camera supplies a 960×540 crop enlarged to 1080p. This improves
framing, not optical detail. People shown on a television or photograph may also
be detected; this version does not distinguish real people from pictures.

## Detector installation

The Pi terminal installer installs the detector runtime and model automatically; framing remains disabled until enabled in settings. For a manual installation or runtime repair on a 64-bit Pi with Python 3.13, from the installed project directory:

```sh
sudo apt-get install python3-venv
sudo sh build_tools/linux/setup-auto-framing.sh
sudo systemctl restart zmalacall-terminal
```

The script creates a private runtime under `zmala_terminal/media/framing-runtime`
and downloads a SHA-256-checked model to `media/models/person.tflite`. Calls never
download models. The detector uses the CPU version of Google's
[SSD MobileNet V2 COCO quantized model](https://github.com/google-coral/test_data/blob/master/ssd_mobilenet_v2_coco_quant_postprocess.tflite)
(Apache-2.0, 300×300 uint8 input, built-in SSD postprocessing) and LiteRT 2.3.0.
No Coral accelerator is required. Source packages exclude installed runtimes and
model weights; the installer prepares them while deploying a release. Manual source installations must run this setup themselves.

## Processing and multicore use

The MJPEG decoder adapter sits before the SDK's preview/encoder tee. JPEG decode, crop and preview reduction run on its worker, with only the newest camera frame waiting for processing. It samples
an uncropped RGB thumbnail and crops decoded YUV420 frames once for both outputs.
Encoded resolution, frame rate and SIP negotiation are unchanged. No additional
camera handle is opened. With framing disabled and the view wide, the adapter
forwards decoded frames without copying their pixels.

A separate, lower-priority Python worker owns LiteRT with two inference threads.
Only one thumbnail can wait; old work is replaced rather than queued. Session and
sample tokens reject stale results after a toggle, resolution change or new call.
The media thread never waits for inference. Existing hardware encoding and
software decoding keep their independent workers; CPU affinity is not restricted.

Initial Pi 4 isolated measurements: 146 ms inference with one thread, 78 ms with
two, and 55 ms with three. Two leaves more CPU capacity for decoding and UI.
A fixed 2× 1080p crop/resize measured about 6.3 ms per frame. These are isolated
measurements; use a real two-way call to assess total load and frame pacing.

## Verification

Portable tests cover group geometry, edge clamping, stable detections, temporary
misses, the 2× limit and server configuration validation. On the Pi:

```sh
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
  build_tools/linux/test-auto-framing.c -o /tmp/test-auto-framing \
  -lmediastreamer2 -lortp -lbctoolbox -lm
/tmp/test-auto-framing
```

This checks the actual SDK adapter, thumbnail colour order, immutable source data,
output resolution/timestamps, crop cost, stale tokens and smooth disable.
The terminal logs person count, inference time and requested zoom. Normal operation
does not save camera images or send detector images to the server.

### Pi 4 room test — 11 October 2026

The first SSD trial used letterboxing, which missed a seated group member. The
final implementation uses the model's square resize input, a 0.45 confidence
threshold and conservative group history. Received call snapshots confirmed both
seated people in the frame at up to 2×. Native thumbnail RGB order was verified
independently with a synthetic colour sample.

Two detector threads ran at Linux nice level 5 while media/UI threads kept their
normal priority. During a two-way call, inference took approximately 100–155 ms
every two seconds. The Pi reported 15 fps sent and about 15 fps received at 1080p,
56°C and no throttling. A configuration update disabled framing during the call;
inference stopped and media continued. Controlled resolution measurements disabled
SDK bitrate adaptation; ordinary calls keep adaptation enabled.

Early trials were interrupted by the existing C20 USB control timeouts before
the detector received any frames. A reconnect/software reset and camera-only
isolation restored capture. Subsequent calls worked with both normal and speech
audio profiles; the evidence does not isolate an audio-profile cause. This feature
does not resolve the intermittent USB problem.
