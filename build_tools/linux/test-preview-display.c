/* Synthetic aliasing regression and Pi timing; no camera, display or call. */
#include "../../zmala_terminal/media/video/preview-display.c"
#include <stdio.h>
#include <time.h>

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    if (zmala_preview_register(factory)) return 1;
    MSFilter *display = ms_factory_create_filter_from_name(factory, "ZmalaPreviewOGL");
    if (!display) return 1;
    bool_t mirrored = TRUE;
    /* This also validates the inherited MSOGL method namespace. */
    if (ms_filter_call_method(display, MS_VIDEO_DISPLAY_ENABLE_MIRRORING, &mirrored)) return 1;
    ms_filter_destroy(display);
    ms_factory_destroy(factory);
    PreviewDisplay s = {.width = 240, .height = 135};
    s.allocator = ms_yuv_buf_allocator_new();
    MSPicture src, out;
    mblk_t *frame = ms_yuv_buf_allocator_get(s.allocator, &src, 1920, 1080);
    if (!frame) return 1;
    /* Alternating thin stripes must average to gray, including chroma.
     * Taking just two pixels per display pixel can miss these stripes. */
    for (int p = 0; p < 3; ++p) {
        int w = p ? src.w / 2 : src.w, h = p ? src.h / 2 : src.h;
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) src.planes[p][y * src.strides[p] + x] = x % 4 < 2 ? 0 : 254;
    }
    mblk_set_timestamp_info(frame, 123456);
    mblk_t *small = reduce_frame(&s, frame);
    if (!small || ms_yuv_buf_init_from_mblk(&out, small)) return 1;
    int failed = out.w != 480 || out.h != 270 || mblk_get_timestamp_info(small) != 123456;
    for (int p = 0; p < 3; ++p) {
        int w = p ? out.w / 2 : out.w, h = p ? out.h / 2 : out.h;
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) failed |= out.planes[p][y * out.strides[p] + x] != 127;
    }
    failed |= src.w != 1920 || src.h != 1080 || src.planes[0][0] != 0 || src.planes[0][2] != 254;
    failed |= reduction(&src, 960, 540) != 1 || reduction(&src, 0, 0) != 1;
    freemsg(small);
    clock_t start = clock();
    for (int i = 0; i < 150; ++i) {
        small = reduce_frame(&s, frame);
        if (!small) return 1;
        freemsg(small);
    }
    printf("Preview averages luma/chroma, preserves 1080p source: %s; %.2f ms/frame\n",
           failed ? "FAIL" : "PASS", 1000.0 * (clock() - start) / CLOCKS_PER_SEC / 150);
    freemsg(frame);
    ms_yuv_buf_allocator_free(s.allocator);
    return failed;
}
