// @test T-LLT-045
// @requirements LLR-TERM-MEDIA-003, LLR-TERM-MEDIA-010
// @environment native-sdk
// @plan Request 1080p from a deliberately absent camera and inject repeated codec recovery requests; assert failure retains the requested size and keyframe work coalesces until the recovery interval passes.
// @pass Every named assertion must pass; record platform and native prerequisites with the result.

/* No camera capture or calls. Link codec.c, mjpeg-filter.c and mjpeg-stream.c
 * with the same SDK/FFmpeg flags as build-media.sh. */
#include "../../../zmala_terminal/linux/media/video/codec.h"
#include "../../../zmala_terminal/linux/media/video/mjpeg-stream.h"
#include <mediastreamer2/msfactory.h>
#include <stdio.h>

extern int zmala_mjpeg_register(MSFactory *factory);

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    if (zmala_mjpeg_register(factory)) return 1;
    MSFilter *source = ms_factory_create_filter_from_name(factory, "ZmalaMJPEGSource");
    MjpegCamera *camera = source->data;
    camera->device = ms_strdup("/dev/zmala-nonexistent-test-camera");
    MSVideoSize wanted = {1920, 1080}, actual = {320, 240};
    int failed = ms_filter_call_method(source, MS_FILTER_SET_VIDEO_SIZE, &wanted) != 0;
    failed |= ms_filter_call_method(source, MS_FILTER_GET_VIDEO_SIZE, &actual) == 0;
    failed |= actual.width != wanted.width || actual.height != wanted.height;
    ms_filter_destroy(source);
    ms_factory_destroy(factory);

    Codec codec = {0};
    pthread_mutex_init(&codec.mutex, NULL);
    zmala_codec_keyframe(&codec);
    failed |= codec.force_keyframe != 1;
    codec.force_keyframe = 0;
    for (int i = 0; i < 1000; ++i) zmala_codec_keyframe(&codec);
    failed |= codec.force_keyframe != 0;
    codec.last_keyframe_request -= 1001;
    zmala_codec_keyframe(&codec);
    failed |= codec.force_keyframe != 1;
    pthread_mutex_destroy(&codec.mutex);
    printf("Camera failure preserves 1080p; recovery requests coalesce: %s\n", failed ? "FAIL" : "PASS");
    return failed;
}
