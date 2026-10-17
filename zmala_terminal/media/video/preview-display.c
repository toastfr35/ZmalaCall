/* Anti-alias the small self-view before MSOGL's final bilinear resize.
 * Only display frames are copied: the encoder keeps the original camera image. */
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msogl_functions.h>
#include <mediastreamer2/msogl.h>
#include <mediastreamer2/msvideo.h>

typedef struct {
    MSFilter *display;
    MSQueue frame, unused;
    MSYuvBufAllocator *allocator;
    unsigned width, height;
} PreviewDisplay;

/* Leave at least two samples per display pixel for the final GPU resize.
 * Divisibility keeps every source pixel and the YUV420 aspect ratio intact. */
static int reduction(const MSPicture *src, unsigned width, unsigned height) {
    if (!width || !height || width > 480 || height > 270) return 1;
    int factor = 1;
    while (factor < 16 && src->w % (factor * 4) == 0 && src->h % (factor * 4) == 0 &&
           src->w / (factor * 2) >= (int)width * 2 && src->h / (factor * 2) >= (int)height * 2)
        factor *= 2;
    return factor;
}

static mblk_t *reduce_frame(PreviewDisplay *s, mblk_t *frame) {
    MSPicture src, dst;
    if (ms_yuv_buf_init_from_mblk(&src, frame)) return NULL;
    int factor = reduction(&src, s->width, s->height);
    if (factor == 1) return NULL;
    mblk_t *small = ms_yuv_buf_allocator_get(s->allocator, &dst, src.w / factor, src.h / factor);
    if (!small) return NULL;
    const unsigned count = (unsigned)(factor * factor);
    for (int p = 0; p < 3; ++p) {
        int width = p ? dst.w / 2 : dst.w, height = p ? dst.h / 2 : dst.h;
        for (int y = 0; y < height; ++y) {
            uint8_t *out = dst.planes[p] + y * dst.strides[p];
            for (int x = 0; x < width; ++x) {
                unsigned sum = 0;
                const uint8_t *in = src.planes[p] + y * factor * src.strides[p] + x * factor;
                for (int dy = 0; dy < factor; ++dy)
                    for (int dx = 0; dx < factor; ++dx) sum += in[dy * src.strides[p] + dx];
                out[x] = (uint8_t)((sum + count / 2) / count);
            }
        }
    }
    mblk_meta_copy(frame, small);
    return small;
}

static void notify(void *context, MSFilter *child, unsigned event, void *arg) {
    (void)child;
    ms_filter_notify(context, event, arg);
}
static void initialize(MSFilter *f) {
    PreviewDisplay *s = ms_new0(PreviewDisplay, 1);
    f->data = s;
    ms_queue_init(&s->frame);
    ms_queue_init(&s->unused);
    s->allocator = ms_yuv_buf_allocator_new();
    s->display = ms_factory_create_filter_from_name(f->factory, "MSOGL");
    if (s->display) {
        s->display->inputs[0] = &s->frame;
        s->display->inputs[1] = &s->unused;
        ms_filter_add_notify_callback(s->display, notify, f, TRUE);
    }
}
static void start(MSFilter *f) {
    PreviewDisplay *s = f->data;
    if (s->display) ms_filter_preprocess(s->display, f->ticker);
}
static void process(MSFilter *f) {
    PreviewDisplay *s = f->data;
    mblk_t *last = ms_queue_peek_last(f->inputs[0]);
    if (last && s->display) {
        mblk_t *small = reduce_frame(s, last);
        ms_queue_put(&s->frame, small ? small : dupmsg(last));
    }
    if (s->display) s->display->desc->process(s->display);
    ms_queue_flush(f->inputs[0]);
    if (f->inputs[1]) ms_queue_flush(f->inputs[1]);
}
static void stop(MSFilter *f) {
    PreviewDisplay *s = f->data;
    if (s->display) ms_filter_postprocess(s->display);
}
static void destroy(MSFilter *f) {
    PreviewDisplay *s = f->data;
    if (s->display) {
        s->display->inputs[0] = s->display->inputs[1] = NULL;
        ms_filter_destroy(s->display);
    }
    ms_queue_flush(&s->frame);
    ms_queue_flush(&s->unused);
    ms_yuv_buf_allocator_free(s->allocator);
    ms_free(s);
}
static int forward(MSFilter *f, unsigned method, void *arg) {
    PreviewDisplay *s = f->data;
    return s->display ? ms_filter_call_method(s->display, method, arg) : -1;
}
static int set_window(MSFilter *f, void *arg) {
    PreviewDisplay *s = f->data;
    const MSOglContextInfo *context = *(const MSOglContextInfo **)arg;
    s->width = context ? context->width : 0;
    s->height = context ? context->height : 0;
    return forward(f, MS_VIDEO_DISPLAY_SET_NATIVE_WINDOW_ID, arg);
}
#define FORWARD(name, method) static int name(MSFilter *f, void *arg) { return forward(f, method, arg); }
FORWARD(set_size, MS_FILTER_SET_VIDEO_SIZE)
FORWARD(get_window, MS_VIDEO_DISPLAY_GET_NATIVE_WINDOW_ID)
FORWARD(show, MS_VIDEO_DISPLAY_SHOW_VIDEO)
FORWARD(zoom, MS_VIDEO_DISPLAY_ZOOM)
FORWARD(mirror, MS_VIDEO_DISPLAY_ENABLE_MIRRORING)
FORWARD(mode, MS_VIDEO_DISPLAY_SET_MODE)
FORWARD(render, MS_OGL_RENDER)
FORWARD(egl_context, MS_OGL_DISPLAY_SET_EGL_TARGET_CONTEXT)
static MSFilterMethod methods[] = {
    {MS_FILTER_SET_VIDEO_SIZE, set_size},
    {MS_VIDEO_DISPLAY_SET_NATIVE_WINDOW_ID, set_window},
    {MS_VIDEO_DISPLAY_GET_NATIVE_WINDOW_ID, get_window},
    {MS_VIDEO_DISPLAY_SHOW_VIDEO, show}, {MS_VIDEO_DISPLAY_ZOOM, zoom},
    {MS_VIDEO_DISPLAY_ENABLE_MIRRORING, mirror}, {MS_VIDEO_DISPLAY_SET_MODE, mode},
    {MS_OGL_RENDER, render}, {MS_OGL_DISPLAY_SET_EGL_TARGET_CONTEXT, egl_context}, {0, NULL}
};
/* Retain the MSOGL method namespace for its render/context methods. The name
 * selects this adapter; its child is explicitly created by the original name. */
static MSFilterDesc descriptor = {MS_OGL_ID, "ZmalaPreviewOGL", "Antialiased small preview with MSOGL",
    MS_FILTER_OTHER, NULL, 2, 0, initialize, start, process, stop, destroy, methods, 0};
int zmala_preview_register(MSFactory *factory) {
    if (!factory || !ms_factory_lookup_filter_by_name(factory, "MSOGL")) return -1;
    ms_factory_register_filter(factory, &descriptor);
    return 0;
}
