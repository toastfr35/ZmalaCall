/* Liblinphone 5.4's automatic preview format callback uses the call graph
 * updater, which skips the QR filter and aborts on camera format changes.
 * Use its QR-aware preview updater on our accountless preview instead. */
#include <winsock2.h>
#include <windows.h>
#ifndef ORTP_PUBLIC
#define ORTP_PUBLIC
#endif
#include <mediastreamer2/mediastream.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/mswebcam.h>
#include <mediastreamer2/msqrcodereader.h>
#include <mediastreamer2/msinterfaces.h>

#define API(result, name, args) static result (*p_##name) args
API(VideoPreview *, video_preview_new, (MSFactory *));
API(void, video_preview_start, (VideoPreview *, MSWebCam *));
API(void, video_preview_stop, (VideoPreview *));
API(void, video_preview_update_video_params, (VideoPreview *));
API(void, video_stream_set_sent_video_size, (VideoStream *, MSVideoSize));
API(void, video_stream_set_display_filter_name, (VideoStream *, const char *));
API(void, video_stream_set_native_preview_window_id, (VideoStream *, void *));
API(void, video_stream_set_event_callback, (VideoStream *, VideoStreamEventCallback, void *));
API(void, ms_filter_clear_notify_callback, (MSFilter *));
API(void, ms_filter_add_notify_callback, (MSFilter *, MSFilterNotifyFunc, void *, bool_t));
API(int, ms_filter_call_method_noarg, (MSFilter *, unsigned int));
API(int, ms_filter_call_method, (MSFilter *, unsigned int, void *));

static void unmirror(VideoPreview *preview) {
    bool_t enabled = FALSE;
    if (preview->output2)
        p_ms_filter_call_method(preview->output2, MS_VIDEO_DISPLAY_ENABLE_MIRRORING, &enabled);
}

static void source_changed(void *user, MSFilter *source, unsigned int event, void *arg);
static void fix_source(VideoPreview *preview) {
    p_ms_filter_clear_notify_callback(preview->source);
    p_ms_filter_add_notify_callback(preview->source, source_changed, preview, FALSE);
}
static void source_changed(void *user, MSFilter *source, unsigned int event, void *arg) {
    VideoPreview *preview = (VideoPreview *)user;
    (void)source; (void)arg;
    if (event == MS_FILTER_OUTPUT_FMT_CHANGED) {
        p_video_preview_update_video_params(preview);
        /* The SDK restores selfie mirroring while rebuilding a camera graph.
         * QR setup should show the same orientation as the printed code. */
        unmirror(preview);
        /* The SDK updater adds its original callbacks again. Replace them
         * before another format notification is dispatched. */
        fix_source(preview);
    }
}

__declspec(dllexport) int zmala_qr_initialize(void) {
    HMODULE module = GetModuleHandleA("mediastreamer2.dll");
    if (!module) return 0;
#define LOAD(name) p_##name = (void *)GetProcAddress(module, #name); if (!p_##name) return 0
    LOAD(video_preview_new); LOAD(video_preview_start); LOAD(video_preview_stop);
    LOAD(video_preview_update_video_params); LOAD(video_stream_set_sent_video_size);
    LOAD(video_stream_set_display_filter_name); LOAD(video_stream_set_native_preview_window_id);
    LOAD(video_stream_set_event_callback); LOAD(ms_filter_clear_notify_callback);
    LOAD(ms_filter_add_notify_callback);
    LOAD(ms_filter_call_method_noarg);
    LOAD(ms_filter_call_method);
    return 1;
}
__declspec(dllexport) unsigned int zmala_qr_event_id(void) {
    return MS_QRCODE_READER_QRCODE_FOUND;
}
__declspec(dllexport) VideoPreview *zmala_qr_start(MSFactory *factory, MSWebCam *camera, void *window,
                                                  VideoStreamEventCallback callback) {
    MSVideoSize size = {640, 480};
    VideoPreview *preview = p_video_preview_new(factory);
    if (!preview) return NULL;
    p_video_stream_set_sent_video_size(preview, size);
    p_video_stream_set_display_filter_name(preview, "MSOGL");
    p_video_stream_set_native_preview_window_id(preview, window);
    preview->enable_qrcode_decoder = TRUE;
    p_video_stream_set_event_callback(preview, callback, NULL);
    p_video_preview_start(preview, camera);
    unmirror(preview);
    fix_source(preview);
    return preview;
}
__declspec(dllexport) void zmala_qr_refresh(VideoPreview *preview) {
    source_changed(preview, preview->source, MS_FILTER_OUTPUT_FMT_CHANGED, NULL);
}
__declspec(dllexport) void zmala_qr_reset_search(VideoPreview *preview) {
    p_ms_filter_call_method_noarg(preview->qrcode, MS_QRCODE_READER_RESET_SEARCH);
}
__declspec(dllexport) void zmala_qr_stop(VideoPreview *preview) {
    p_video_preview_stop(preview);
}
