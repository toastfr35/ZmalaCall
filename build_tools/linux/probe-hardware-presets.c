/* Check the SDK's actual encoder capability negotiation without a camera/SIP.
 * Build alongside the C20 plugin:
 * cc probe-hardware-presets.c -o probe-hardware-presets -lmediastreamer2 \
 *    -lortp -lbctoolbox -L../../zmala_terminal/media/video -lzmala_video
 * Run with that plugin directory in LD_LIBRARY_PATH.
 */
#include <stdio.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msvideo.h>

extern int zmala_video_register(MSFactory *factory);

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    if (!factory) return 1;
    if (zmala_video_register(factory)) { ms_factory_destroy(factory); return 1; }
    MSFilter *encoder = ms_factory_create_encoder(factory, "H264");
    const MSVideoConfiguration *list = NULL;
    int failed = !encoder;
    if (encoder && ms_filter_call_method(encoder, MS_VIDEO_ENCODER_GET_CONFIGURATION_LIST, &list)) failed = 1;
    if (!list) failed = 1;
    const struct { int width, height, bitrate; } presets[] = {
        {640, 360, 700000}, {1280, 720, 1500000}, {1920, 1080, 2500000}
    };
    for (unsigned i = 0; list && i < sizeof(presets) / sizeof(presets[0]); ++i) {
        MSVideoSize requested = {presets[i].width, presets[i].height};
        MSVideoConfiguration selected = ms_video_find_best_configuration_for_size_and_bitrate(
            list, requested, 4, presets[i].bitrate - 64000); /* Leave room for call audio. */
        MSVideoConfiguration applied;
        if (selected.vsize.width != requested.width || selected.vsize.height != requested.height ||
            ms_filter_call_method(encoder, MS_VIDEO_ENCODER_SET_CONFIGURATION, &selected) ||
            ms_filter_call_method(encoder, MS_VIDEO_ENCODER_GET_CONFIGURATION, &applied) ||
            applied.vsize.width != requested.width || applied.vsize.height != requested.height) failed = 1;
        printf("%dx%d preset selected %dx%d at %.0f fps\n", requested.width, requested.height,
               selected.vsize.width, selected.vsize.height, selected.fps);
    }
    if (encoder) ms_filter_destroy(encoder);
    ms_factory_destroy(factory);
    return failed;
}
