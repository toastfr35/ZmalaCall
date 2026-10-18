/* Opt-in native camera probe. Run only while the terminal is idle: this opens
 * the physical webcam. It verifies real JPEG frames and negotiated dimensions,
 * rather than accepting a static no-camera placeholder as a passing result. */
#include <stdio.h>
#include <stdlib.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/mswebcam.h>
#include <bctoolbox/logging.h>
#include "../../zmala_terminal/linux/media/video/mjpeg-stream.h"

extern int zmala_mjpeg_register(MSFactory *factory);
static unsigned frames;
static unsigned packets;
static void consume(MSFilter *f) {
    mblk_t *frame;
    while ((frame = ms_queue_get(f->inputs[0]))) {
        ++packets;
        if (frame->b_cont && frame->b_cont->b_wptr - frame->b_cont->b_rptr > 30 &&
            frame->b_cont->b_rptr[0] == 0xff && frame->b_cont->b_rptr[1] == 0xd8) ++frames;
        freemsg(frame);
    }
}
static MSFilterDesc sink = {MS_FILTER_PLUGIN_ID, "ZmalaProbeSink", "Count JPEG frames",
    MS_FILTER_OTHER, NULL, 1, 0, NULL, NULL, consume, NULL, NULL, NULL, 0};

int main(int argc, char **argv) {
    if (argc != 3) { fprintf(stderr, "usage: probe-mjpeg-camera width height\n"); return 2; }
    bctbx_set_log_level_mask("mediastreamer", 63);
    MSFactory *factory = ms_factory_new_with_voip();
    if (!factory || zmala_mjpeg_register(factory)) return 1;
    MSWebCam *cam = ms_web_cam_manager_get_cam(ms_factory_get_web_cam_manager(factory), "ZmalaMJPEG: /dev/video0");
    if (!cam) { ms_factory_destroy(factory); return 1; }
    MSFilter *reader = ms_web_cam_create_reader(cam);
    MSFilter *output = ms_factory_create_filter_from_desc(factory, &sink);
    MSVideoSize wanted = {atoi(argv[1]), atoi(argv[2])}, actual = {0};
    float fps = 15;
    int failed = ms_filter_call_method(reader, MS_FILTER_SET_VIDEO_SIZE, &wanted) ||
        ms_filter_call_method(reader, MS_FILTER_SET_FPS, &fps) ||
        ms_filter_call_method(reader, MS_FILTER_GET_VIDEO_SIZE, &actual);
    if (failed) { ms_filter_destroy(reader); ms_filter_destroy(output); ms_factory_destroy(factory); return 1; }
    MSTicker *ticker = ms_ticker_new();
    ms_filter_link(reader, 0, output, 0);
    ms_ticker_attach(ticker, reader);
    ms_sleep(5);
    MjpegCamera *state = reader->data;
    printf("received=%u copied=%u rejected=%u\n", atomic_load(&state->received),
        atomic_load(&state->copied), atomic_load(&state->rejected));
    ms_ticker_detach(ticker, reader);
    ms_filter_unlink(reader, 0, output, 0);
    ms_ticker_destroy(ticker);
    ms_filter_destroy(reader);
    ms_filter_destroy(output);
    ms_factory_destroy(factory);
    printf("%dx%d requested, %dx%d configured, %u packets / %u real JPEG frames in 5 seconds\n",
        wanted.width, wanted.height, actual.width, actual.height, packets, frames);
    return actual.width != wanted.width || actual.height != wanted.height || frames < 50;
}
