# C20 Raspberry Pi media

## Supported configuration

Linux uses one media path: Nuroum C20 MJPEG capture, Pi `bcm2835-codec` H.264
encoding, FFmpeg software H.264 decoding and C20 microphone/speaker/ringer.
The shared Python UI, SIP/RTP, provisioning, server communication and call
control remain shared with Windows. Windows retains its SDK device selection
and VP8/H.264 support for PC tests. Phone peers must enable H.264 for Pi calls.

The current target is Pi 3 Model B with Debian 13 ARM64, Liblinphone 5.3.105,
a C20 (`0525:a4ad`) and a Samsung TV on HDMI 2. This does not establish support
for a Pi without that hardware encoder or a different camera. The C20's
capture audio is stereo S16_LE at 16 kHz; playback is stereo S16_LE at 48 kHz.
It offers MJPEG at 640×360, 640×480, 1280×720 and 1920×1080 at 30 camera fps;
raw YUYV stops at VGA and no H.264 camera format is advertised.

Pi 4 Model B Rev 1.5 was additionally checked on 11 October 2026 using the
migrated Debian 13 ARM64 card and Liblinphone 5.3.105. Its
`bcm2835-codec-encode` device supports the existing backend: the synthetic
resize regression decoded 29/29/30/29 pictures across all four phases. Direct
concurrent C20 camera, microphone and silent playback checks also completed
(450 VGA MJPEG pictures and 15 seconds of audio). These short checks do not
establish sustained call quality or physical CEC operation. A later boot-time
display override restored a 720p TV picture, confirmed by the user; see the
[Pi migration notes](linux-terminal.md#moving-a-pi-3-card-to-a-pi-4). The Pi 3
performance figures below must not be interpreted as Pi 4 measurements.

The default is **720p at 15 encoded fps**, with 1500/2000 kbit/s upload/download
budgets. The server retains 480p, 720p and 1080p presets and normal/speech audio
processing. Change these while idle; active calls finish before the native
graph is recreated. 1080p is retained for explicit comparisons but has not met
the user's 10 fps minimum in a reliable C20 call. Use 720p for this Pi.

## Pi 4 call measurements — 11 October 2026

On Pi 4 Model B Rev 1.5, the best verified **bidirectional call setting is
720p at 15 fps**. A 90-second call and a three-minute repeat maintained decoded
video after startup. In the longer run, the PC measured approximately
14.1–17.0 fps from the Pi camera (median 15.0); the Pi decoded the PC's moving
1280×720 test pattern at approximately 13.7–15.8 fps (median 15.0). The Pi's
reported send/receive sizes stayed at 1280×720; the PC occasionally omitted a
received size but reported no smaller size. All 169 samples after the first
ten seconds indicated active video on each end.

Average system CPU use was about 26% of the four-core machine, peaking around
37%; temperature peaked at approximately 56.5°C. The 720p repeat had no
reported RTCP packet loss, undervoltage, throttling or USB disconnect. Audio
traffic continued in both directions. Tests used the actual C20 camera,
microphone and speaker, the normal UI/local preview, 720p HDMI with VSync
compositing, and 5 GHz Wi-Fi. Speaker volume was reduced to 10% during the
later tests. These are short hardware checks, not an unattended endurance or
subjective audio-quality certification.

The 1080p call failed outgoing-video acceptance: the Pi decoded incoming
1920×1080 at approximately 15 fps, but Windows decoded no Pi video during
the 90-second call and logged OpenH264 errors. System CPU averaged about
42%, peaking at 52%, with maximum temperature about 58°C and no throttling.
Reported transmission at 15 fps is not proof of usable video. An isolated
C20 capture → hardware encode → packetize/decode test subsequently decoded
146 full-HD frames with FFmpeg and 147 with OpenH264 over ten seconds, with
no wrong-size frames or codec queue drops. This separates basic full-HD
hardware capability from the unresolved live-call failure; it does not
identify the failing component. Investigate the live H.264 negotiation,
transport and Windows decoder before attributing this to insufficient CPU.

The low-bandwidth 480p preset automatically reduced the Pi's transmitted
size to 320×240 in both comparison calls. Its roughly 15 fps result therefore
does not qualify sustained VGA transmission. Prefer the verified 720p setting
for image quality; the adaptive low-preset behavior remains a tuning issue.
Test resolution overrides were confined to temporary terminal processes;
saved server settings were not changed.

## One installation package

Build `ZmalaCall-Terminal-rpi.tar.gz` on the development PC:

```powershell
python build_tools/linux/package-terminal.py
```

Extract it on the Pi and run `sudo ./install.sh` as described in the
[Linux guide](linux-terminal.md). The installer builds the native codecs on
the target and configures automatic startup. No hardware-experiment package,
codec switch or external camera-capture checkout is needed. Updating an old
installation removes its legacy media systemd drop-ins and command links;
enrollment, TV pairing and state remain in `/var/lib/zmalacall`.

Native source lives under `zmala_terminal/media/video/` and `media/audio/`.
`build_tools/linux/build-media.sh` builds the private libraries, which are
registered explicitly instead of modifying another application's SDK plugin
directory. `platforms/linux_media.py` owns the Linux device policy and plugin
loader. Camera entries are registered only for kernel devices named Nuroum
C20. The terminal selects the current MJPEG entry and C20 audio IDs, even if
ALSA/V4L2 indices or saved server device strings changed. Only C20 choices are
reported to the server on Linux. Missing C20 components cause a clear media
startup error rather than selecting HDMI or a different webcam.

The C930e subprocess/IPC bridge, hardware-decoder branch, opt-in media mode
scripts and legacy local video JSON/environment switches have been removed.
Their historical measurements remain in Git history. Resolution, bandwidth
and frame rate come from one shared server-preset implementation.

## Processing and ownership

The standard SDK V4L2 camera prefers YUYV and can silently clamp HD to VGA.
Our explicit MJPEG source checks the negotiated format and exact dimensions.
Camera I/O runs off the SDK ticker with a single latest-frame slot; raw camera
frames can be dropped safely without accumulating latency. MJPEG decoding,
scaling and OpenGL display still use SDK filters.

The encoder also handles input pictures whose dimensions differ from its
configured target. This occurs in real calls when the SDK supplies 640×480
pictures to a 320×240 encoder. A cached SDK scaler on the codec worker resizes
only mismatched pictures; matching sizes retain the direct copy. Both the
scaler and raw frame allocation are released when the encoder is reopened.
Without this fallback, every mismatched picture was rejected and triggered
another encoder reopen, stopping outgoing video indefinitely.

The opt-in Pi regression `build_tools/linux/test-video-resize.c` uses synthetic
pictures and decodes the hardware output to verify target dimensions through
target and source size changes. Stop the terminal before running it, and
restart it afterwards. From the repository root:

```sh
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread \
  -Izmala_terminal/media/video build_tools/linux/test-video-resize.c \
  zmala_terminal/media/video/codec.c -o /tmp/test-video-resize \
  $(pkg-config --cflags --libs libavcodec libavutil) \
  -lmediastreamer2 -lortp -lbctoolbox
timeout 30 /tmp/test-video-resize
```

The codec worker owns FFmpeg objects and exchanges bounded queues with the
ticker. The encoder reuses its raw AVFrame buffer; FFmpeg's `make_writable`
allocates only when an in-flight reference still owns that buffer. Resolution
changes reopen the context and release the old allocation. The ticker keeps
only the newest raw picture in delayed batches and supplies a unique RTP
timestamp. Encoded reference frames are retained; overflow reopens the encoder
to recover with fresh headers. RFC3984 packetization repeats SPS/PPS on IDRs.

The software decoder keeps two FFmpeg threads and allocates output through the
SDK's reusable YUV allocator. It sends bounded PLI requests after corrupted
access units. Hardware decoding was removed because it reproduced stalls in
the earlier experiments. There is no silent codec change during a call.

The server's speech profile caps echo processing at the C20 microphone's
native 16 kHz. Its Opus RTP clock remains 48 kHz, and the SDK handles playback
resampling to the C20's native rate. Normal processing remains a server option.
The 500 ms echo window and automatic delay are retained pending acoustic
measurements; the C20's presence alone does not prove that a shorter window
or disabled software cancellation is safe. Windows uses its normal SDK audio.

## Verified frame floor and limits

Before this simplification, a 60-second call received a real 1280×720 C20 feed
at a minimum 14.26 fps after five startup samples while sending a moving
1280×720 SDK test pattern at 15 fps. The snapshot showed that pattern on the
physical TV. Final received rate was 14.84 fps, with approximately 189 ms video
jitter buffer. A five-second in-call terminal CPU sample measured 197.2% of one
core, about half of the Pi's four cores in aggregate. A subsequent 30-second
call after restart passed above 14.39 fps. These are short continuity checks,
not long-term reliability, end-to-end latency or subjective audio measurements.

After installing the single C20 package, another 60-second moving-pattern call
passed at a minimum 14.30 received fps and 15 sent fps, with a real 1280×720
snapshot showing the TV's incoming picture. A repeat call then lost camera
capture and fell back to the placeholder. An independent MJPEG camera probe
also received zero frames, so this was not accepted as a passing performance
measurement. Rebooting recovered capture; a 45-second call passed at a minimum
14.12 received fps and 15 sent fps. A five-second CPU sample during that passing
call measured 168.9% of one core. This is a short sample, not a controlled
before/after benchmark. The capture stall can also affect repeated 720p calls;
reliable camera recovery remains unresolved. Testing was paused at the user's
request after this call, with the Pi registered and idle.

1080p capture/hardware encoding worked in a local ten-second roundtrip (144
correctly sized decoded frames). An OpenH264 decoder comparison produced 94
frames with increasing ticker delay. Actual 1080p calls produced decoder
errors or a one-fps placeholder and failed the 10 fps floor. The C20 stopped
delivering USB camera frames after a trial and required a Pi reboot; changing
the resolution alone did not recover it. Requesting 15 camera fps was clamped
to 30 by this device. That USB recovery issue remains unresolved.

Live tests deliberately support a moving synthetic source because the PC
webcam may be occupied. A one-fps placeholder must not count as a passing
moving-video workload:

```powershell
python zmala_terminal/tests/camera_feed_live.py --synthetic --seconds 60 --min-fps 10 --output build_tools/tmp/c20-call.json --snapshot build_tools/tmp/c20-call.jpg
```

Run with both terminals idle. This calls the auto-answering Pi as term1 and
leaves the PC webcam free. `--camera` instead uses its real webcam. The test
requires every received FPS sample after five startup samples to meet the
floor; moving-source tests also check sent FPS. Missing/zero/invalid values
fail. `--snapshot` explicitly saves one received frame for dimension/pixel
verification; without it no webcam images are recorded. `--check-audio` measures
decoded PCM duration, nonzero samples, RMS and peak amplitude, then deletes the
temporary WAV. Neither audio traffic nor nonzero PCM verifies audibility or echo
quality. Implausible FPS values above the C20's 30 fps limit fail the frame floor.

On October 9, with HDMI disconnected, the C20 disconnected from USB during a
phone call at 20:43:42 (UVC error -71, followed by missing-device audio errors).
Camera capture subsequently stalled even in a standalone probe. A Pi reboot
recovered it. Two successive 25-second Windows-to-Pi calls then received nonzero
decoded microphone audio; the second saved a genuine 1280×720 C20 image. HDMI
remained disconnected throughout. This verifies audio/video reception, but does
not establish the 10 fps floor: the SDK reported an unreliable 100 fps value.
The cause of the unexpected USB disconnect and intermittent capture stall is
still unresolved.

## October 9 optimization checks

Camera acquisition drains all USB buffers but copies JPEGs only at the requested
rate. There is one rate gate in capture; adding another on the SDK ticker caused
unnecessary losses between independently paced clocks and was removed. Compressed
NALs share their original allocation with RTP packing, and FFmpeg retains padded
access-unit buffers instead of copying them again. Decoding still processes every
reference frame; after a delayed tick, only the newest decoded picture is displayed.
Queues remain bounded and record their peak lengths, drops and maximum wait.

At 720p, an idle camera probe delivered 75 genuine JPEGs in five seconds from
127 captured frames, copying only the 75 required. The hardware encode/software
decode/RTP roundtrip delivered 146 correctly sized frames in ten seconds. Encoder
and decoder queues peaked at one input/output frame, with a maximum 1 ms queue
wait and no dropped frames in that local test. This is not end-to-end latency.

A 60-second network call initially passed at a minimum 10.70 received fps; repeat
calls failed with decoding gaps and then a one-fps placeholder. A standalone
camera roundtrip also received no frames. Rebooting recovered the C20, and a
subsequent 60-second call passed at a minimum 12.21 received fps and 15 sent fps,
with a genuine 1280×720 TV snapshot. A five-second CPU sample during that passing
call was 218.4% of one core. These short samples are not controlled before/after
comparisons, so a CPU improvement has not been established. Intermittent C20
capture recovery remains unresolved; failed placeholder calls do not count as
passing performance measurements.

A subsequent 45-second call passed without another reboot, at a minimum 11.43
received fps and 15 sent fps, again with a genuine 1280×720 TV snapshot. This
short repeat check does not establish long-term camera reliability.

Versioned polling reduced the live terminal configuration response from 2,022
to 249 bytes (88%) for the current contacts. A six-second check confirmed that
presence polling no longer rewrites its offline configuration cache. Admin live
polling also omits stable account/profile data; private hash-named photos reuse
cached bytes. Ringing updates canvas items, countdowns update once per second,
and both platform renderers use bounded LRU text/portrait caches with four-pixel
portrait size buckets. Durable console/callback writes run asynchronously and
are flushed before acknowledging a lease/result or starting notification delivery.

## Native checks

### Windows 1080p decoder correction — 11 October 2026

The earlier Windows receive failure was reproduced with synthetic Pi-encoded
1080p H.264: direct OpenH264 decoding succeeded, while the bundled SDK adapter
corrupted emulation-prevention sequences and decoded zero frames. The terminal
now registers `ZmalaOpenH264Dec`, a byte-preserving receiver using the same pinned
OpenH264 DLL. It also accepts SDP parameter sets and coalesces recovery requests.
The Pi encoder similarly limits requested keyframes to one per second.

A 180-second real-camera call then sustained 1920×1080 in both directions:
Windows received 15.14 fps on average and Pi received 15.00 fps, with approximately
2.5 Mbit/s sent by the Pi. Every post-startup sample had live received video.
The screenshot was visibly sharper than the original 320×240 transmission.
Intermittent C20 USB disconnects remain separate from decoder compatibility;
the C20 was still directly connected to the Pi during these tests.
The following call reproduced C20 USB startup timeouts, requiring a USB reset.
Repeated-call device reliability therefore remains unresolved.

On Windows, `build_tools/setup-runtime.py` and `start-terminal.ps1` build the
receive adapter using the existing x64 GCC toolchain. A camera-free regression
with three synthetic gray frames exercises fragmented RTP and both in-band/SDP
parameter sets:

```powershell
python build_tools/build-h264-decoder.py
python build_tools/tests/h264_decoder_native.py
```

On Linux, `build_tools/linux/test-video-recovery.c` verifies that camera setup
errors do not silently select 320×240 and that repeated keyframe requests are
coalesced. It does not capture pictures or place calls. Compile it with `codec.c`,
`mjpeg-filter.c` and `mjpeg-stream.c`, using the flags from `build-media.sh`.

### Camera probes

The opt-in camera probes open the physical C20; run them only when idle.
From an installed checkout, compile and run:

```sh
video=zmala_terminal/media/video
cc -std=c11 -O2 -Wall -Wextra -Werror build_tools/linux/probe-mjpeg-camera.c \
  -o /tmp/probe-mjpeg-camera -lmediastreamer2 -lortp -lbctoolbox \
  -L"$video" -lzmala_video
LD_LIBRARY_PATH="$PWD/$video" /tmp/probe-mjpeg-camera 1280 720
cc -std=c11 -O2 -Wall -Wextra -Werror build_tools/linux/probe-hardware-roundtrip.c \
  -o /tmp/probe-hardware-roundtrip -lmediastreamer2 -lortp -lbctoolbox \
  -L"$video" -lzmala_video
LD_LIBRARY_PATH="$PWD/$video" /tmp/probe-hardware-roundtrip 1280 720
```

The camera probe requires 50 genuine JPEG frames in five seconds; the codec
roundtrip requires 100 correctly sized decoded pictures in ten seconds. Its
optional third argument `openh264` checks the Windows decoder family locally.
Neither probe records camera video. `probe-hardware-presets.c` checks the
three SDK encoder presets without a camera or call. The FFmpeg benchmark and
echo-processing probe are standalone diagnostic tools, not runtime branches.

## Local preview downsampling

Linux uses `ZmalaPreviewOGL`, a wrapper around the SDK's MSOGL renderer. For
the small self-view context (240×135 nominal size), it averages source pixels
before the final GPU resize. A 1080p camera image becomes 480×270 for this
display branch, reducing jagged edges and shimmering caused by shrinking
1080p directly with bilinear filtering. The full-size incoming display and
the camera frames sent to the encoder are unchanged. Windows keeps MSOGL.

The synthetic regression checks luma/chroma averaging, source preservation,
timestamps and the inherited renderer interface, without opening a camera:

```sh
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror \
  build_tools/linux/test-preview-display.c -o /tmp/test-preview-display \
  -lmediastreamer2 -lortp -lbctoolbox
/tmp/test-preview-display
```

Measured on the Pi 4: approximately 8–9 ms per 1080p frame for averaging.

## Primary source references

- [Raspberry Pi camera software and V4L2 hardware codecs](https://www.raspberrypi.com/documentation/computers/camera_software.html)
- [MediaStreamer V4L2 camera](https://github.com/BelledonneCommunications/mediastreamer2/blob/5.3.105/src/videofilters/msv4l2.c)
- [FFmpeg V4L2 M2M encoder](https://github.com/FFmpeg/FFmpeg/blob/n7.1/libavcodec/v4l2_m2m_enc.c)


## Configurable frame rate and 1080p30 trial (2026-10-17)

The server now stores an independent outgoing `video_fps` target for each
terminal: 10, 15 (default), 20, 25 or 30. Terminals apply changes only when idle.
Sending bandwidth and the Pi encoder ladder scale from the existing 15 fps
presets; receiving bandwidth allows a faster peer independently of the local
sending rate. Resolution remains a separate setting. The server relays packets
and does not impose a frame-rate conversion.

A 100-second trial requested 1080p30 with a 5 Mbit/s sending allowance on both
terminals. It did not establish stable 30 fps in both directions: the Windows
webcam path generally sent around 19 fps, and the Pi decoder reported around
15 fps on average. The C20-to-Windows path was faster, but receiver statistics
had discontinuities and packet-reassembly warnings near the end of the trial.
Do not treat its negotiated 30 fps as proof of 30 decoded/displayed frames.
The terminal Pi averaged 67% total CPU (80% peak), while the server Pi averaged
about 4%; neither reported throttling. Existing terminals remain at the stable
15 fps default, with higher targets available for further tuning.

A subsequent 45-second call verified independent settings (Windows 20 fps,
Pi 25 fps), with 1920×1080 video continuously decoded in both directions.
Windows sent about 16 fps; the receiver's sampled rate varied around the Pi's
25 fps target. The strict frame-rate probe failed because some SDK receive
measurements exceeded the camera's 30 fps maximum, so this is configuration
and continuity verification, not a passed sustained-frame-rate benchmark.
Both terminals were restored to 1080p15 and confirmed to apply that setting.

## 1080p20 bottleneck investigation (2026-10-17)

Both terminals are now configured for 1080p20 at the user's request (3334 kbit/s
sending allowance each), with speaker volume still zero. Temporary profiling
was removed after testing; both terminals returned home and registered.

- A 70-second real-camera call sustained video. Windows sent about 15–16 fps;
  its media process used about 0.41 CPU cores. Filter elapsed time was about
  70 ms/second for encoding and 115 ms/second for received H.264 decoding.
  Replacing only the Windows camera with the SDK moving test pattern produced
  an exact 20 fps sending rate at 1920×1080 in the following 45-second call.
  The Pi reported approximately 19.9 fps over the settled synthetic interval.
- The C930e's exposure control reported automatic exposure at -4. This means
  1/16 second (62.5 ms), longer than the 50 ms frame period needed for 20 fps.
  The capture SDK selected a 1920×1080 NV12 mode labelled 24 fps, but measured
  only 439 camera samples in the approximately 30-second capture test. Mode
  metadata therefore did not establish the actual camera throughput.
- A temporary manual exposure of -5 (1/32 second) set **after capture began**
  raised Windows sending to 20 fps throughout the final 12 seconds of the
  confirmation call, with zero reported RTP loss during that interval.
  Setting exposure before opening capture was insufficient: opening the
  camera changed the reported value back to -4. Automatic exposure was
  restored afterward; actual fps can fall again in low light. The exposure
  units are documented by
  [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/strmif/ne-strmif-cameracontrolproperty).
- The terminal Pi averaged approximately 59% total CPU, at 38.5°C with no
  throttling. Its busiest video thread used about 67% of one core. Profiled
  filter elapsed time was approximately 337 ms/second for video display
  (including the self-view) and 225 ms/second for the MJPEG/framing wrapper.
  These are wall-time measurements, not CPU percentages. H.264 decoding
  already ran on two worker threads, using about 19% of one core each.
  During the real-camera short-exposure interval, Pi receive/display samples
  still varied around 14–20 fps despite Windows sending 20. This does not
  establish sustained 20 displayed fps for complex live video.
- The server averaged approximately 4% total CPU. Pi Wi-Fi reported a strong
  -46 dBm signal and a 72.2 Mbit/s link on 2.4 GHz. Real-camera steady-state
  samples reported zero RTP loss, but receive jitter and bursty frame delivery
  remained visible. Link rate alone does not exclude wireless latency.

The first improvement for term1 is sufficient lighting or an explicit
frame-rate-priority exposure option, with the brightness/noise tradeoff made
visible. For the Pi, prioritize moving MJPEG decoding/framing off the shared
video ticker and reducing preview/display work; compare Ethernet with Wi-Fi
before attributing all display gaps to processing. A faster server would not
address the measured limits. The 20 fps setting remains a target, not a promise
that every camera or display delivers every frame.
