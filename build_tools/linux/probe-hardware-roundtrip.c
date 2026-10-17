/* Opt-in, idle-only probe: real MJPEG capture through the same H.264 codec
 * and RTP packetization used by calls, without a network in between. This
 * separates capture/codec failures from transport or remote decoder failures. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mediastreamer2/allfilters.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/mswebcam.h>
#include <bctoolbox/logging.h>
#include "../../zmala_terminal/media/video/codec.h"

extern int zmala_mjpeg_register(MSFactory *factory);
extern int zmala_video_register(MSFactory *factory);
static unsigned frames, wrong_size;
static MSVideoSize wanted;
static void consume(MSFilter *filter) {
    mblk_t *frame;
    while ((frame = ms_queue_get(filter->inputs[0]))) {
        MSPicture picture;
        if (ms_yuv_buf_init_from_mblk(&picture, frame) >= 0) {
            if (picture.w == wanted.width && picture.h == wanted.height) ++frames;
            else ++wrong_size;
        }
        freemsg(frame);
    }
}
static MSFilterDesc sink = {MS_FILTER_PLUGIN_ID, "ZmalaRoundtripSink", "Count decoded pictures",
    MS_FILTER_OTHER, NULL, 1, 0, NULL, NULL, consume, NULL, NULL, NULL, 0};

int main(int argc, char **argv) {
    if (argc != 3 && (argc != 4 || strcmp(argv[3], "openh264"))) {
        fprintf(stderr, "usage: probe-hardware-roundtrip width height [openh264]\n"); return 2;
    }
    wanted = (MSVideoSize){atoi(argv[1]), atoi(argv[2])};
    /* Include queue counters at teardown without per-frame debug logging. */
    bctbx_set_log_level_mask("mediastreamer", BCTBX_LOG_MESSAGE | BCTBX_LOG_WARNING | BCTBX_LOG_ERROR | BCTBX_LOG_FATAL);
    MSFactory *factory = ms_factory_new_with_voip();
    if (!factory || zmala_mjpeg_register(factory) || zmala_video_register(factory)) return 1;
    /* The Windows SDK uses OpenH264. Selecting it here checks interoperability
     * independently of packet loss, while FFmpeg checks our native decoder. */
    if (argc == 4) ms_factory_enable_filter_from_name(factory, "MSOpenH264Dec", TRUE);
    MSWebCam *cam = ms_web_cam_manager_get_cam(ms_factory_get_web_cam_manager(factory), "ZmalaMJPEG: /dev/video0");
    if (!cam) { ms_factory_destroy(factory); return 1; }
    MSFilter *chain[] = {
        ms_web_cam_create_reader(cam),
        ms_factory_create_filter(factory, MS_MJPEG_DEC_ID),
        ms_factory_create_filter_from_name(factory, "ZmalaV4L2H264Enc"),
        ms_factory_create_filter_from_name(factory, argc == 4 ? "MSOpenH264Dec" : "ZmalaFFmpegH264Dec"),
        ms_factory_create_filter_from_desc(factory, &sink)
    };
    int failed = 0;
    for (unsigned i = 0; i < 5; ++i) if (!chain[i]) failed = 1;
    float fps = 15;
    MSVideoConfiguration config = {1800000, 2500000, wanted, 15, 1, NULL};
    if (!failed) failed = ms_filter_call_method(chain[0], MS_FILTER_SET_VIDEO_SIZE, &wanted) ||
        ms_filter_call_method(chain[0], MS_FILTER_SET_FPS, &fps) ||
        ms_filter_call_method(chain[2], MS_VIDEO_ENCODER_SET_CONFIGURATION, &config);
    if (!failed) {
        MSTicker *ticker = ms_ticker_new();
        for (unsigned i = 0; i < 4; ++i) ms_filter_link(chain[i], 0, chain[i + 1], 0);
        ms_ticker_attach(ticker, chain[0]);
        ms_sleep(10);
        ms_ticker_detach(ticker, chain[0]);
        /* Detach joins workers before reading their final queue counters. */
        for (unsigned i = 2; i <= (argc == 4 ? 2u : 3u); ++i) {
            Codec *codec = chain[i]->data;
            printf("%s: peak_input=%d peak_output=%d max_queue_ms=%llu dropped=%d display_dropped=%d\n",
                i == 2 ? "encoder" : "decoder", codec->peak_input, codec->peak_output,
                (unsigned long long)codec->max_queue_ms, codec->dropped, codec->display_dropped);
        }
        for (unsigned i = 0; i < 4; ++i) ms_filter_unlink(chain[i], 0, chain[i + 1], 0);
        ms_ticker_destroy(ticker);
    }
    for (unsigned i = 0; i < 5; ++i) if (chain[i]) ms_filter_destroy(chain[i]);
    ms_factory_destroy(factory);
    printf("%dx%d: %u decoded frames, %u wrong-size frames in 10 seconds\n",
        wanted.width, wanted.height, frames, wrong_size);
    return failed || frames < 100 || wrong_size;
}
