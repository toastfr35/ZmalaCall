#!/bin/sh
# Build the C20 codecs locally; never install into another application's SDK.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
source_dir="$task_root/zmala_terminal/linux/media/video"
cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -fPIC -shared -pthread \
  "$source_dir/codec.c" "$source_dir/filters.c" \
  "$source_dir/mjpeg-stream.c" "$source_dir/mjpeg-filter.c" "$source_dir/preview-display.c" \
  "$source_dir/auto-framing.c" \
  -o "$source_dir/libzmala_video.so" \
  $(pkg-config --cflags --libs libavcodec libavutil) \
  -lmediastreamer2 -lortp -lbctoolbox -lm
printf 'Built %s\n' "$source_dir/libzmala_video.so"
audio_dir="$task_root/zmala_terminal/linux/media/audio"
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  "$audio_dir/echo-rate.c" -o "$audio_dir/libzmala_speech_audio.so" \
  -lmediastreamer2 -lortp -lbctoolbox
printf 'Built %s\n' "$audio_dir/libzmala_speech_audio.so"
