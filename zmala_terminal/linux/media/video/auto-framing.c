/* MJPEG decoder adapter: full-frame thumbnail -> detector worker, then crop
 * before the SDK preview/encoder tee. No camera reopen or encoder resize.
 * The disabled path forwards the original decoded frame without a copy. */
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <string.h>
#include <bctoolbox/port.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/msticker.h>

static MSFilterDesc *original;
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static struct {
    int enabled, ready, width, height;
    uint32_t session, sequence;
    uint64_t sampled, updated;
    float x, y, size;
    uint8_t rgb[256 * 256 * 3];
} control = {.x = .5f, .y = .5f, .size = 1.f};

void zmala_framing_enable(int enabled) {
    pthread_mutex_lock(&mutex);
    if (control.enabled != !!enabled) {
        control.enabled = !!enabled;
        ++control.session;
        control.ready = 0;
        control.sampled = control.updated = 0;
        control.x = control.y = .5f;
        control.size = 1.f;
    }
    pthread_mutex_unlock(&mutex);
}

uint64_t zmala_framing_take(uint8_t *rgb, int *width, int *height) {
    uint64_t token = 0;
    pthread_mutex_lock(&mutex);
    if (control.enabled && control.ready) {
        *width = control.width;
        *height = control.height;
        memcpy(rgb, control.rgb, (size_t)*width * *height * 3);
        token = ((uint64_t)control.session << 32) | control.sequence;
        control.ready = 0;
    }
    pthread_mutex_unlock(&mutex);
    return token;
}

// @llr LLR-TERM-VIDEO-016
void zmala_framing_target(uint64_t token, float x, float y, float size) {
    if (!isfinite(x) || !isfinite(y) || !isfinite(size) || size < .5f || size > 1.f ||
        x < size / 2 - .00001f || y < size / 2 - .00001f ||
        x > 1 - size / 2 + .00001f || y > 1 - size / 2 + .00001f) return;
    x = fmaxf(size / 2, fminf(1 - size / 2, x));
    y = fmaxf(size / 2, fminf(1 - size / 2, y));
    pthread_mutex_lock(&mutex);
    uint64_t expected = ((uint64_t)control.session << 32) | control.sequence;
    uint64_t now = bctbx_get_cur_time_ms();
    if (control.enabled && token == expected && now - control.sampled < 3500) {
        control.x = x;
        control.y = y;
        control.size = size;
        control.updated = now;
    }
    pthread_mutex_unlock(&mutex);
}

typedef struct {
    MSFilter *decoder;
    MSQueue encoded, decoded; /* worker-only SDK queues */
    pthread_t thread;
    pthread_mutex_t queue_mutex, decoder_mutex;
    pthread_cond_t ready;
    int started, stopping;
    mblk_t *pending, *completed; /* one waiting frame in each direction */
    MSTicker clock; /* worker-owned clock; never borrow the live ticker */
    uint64_t pending_time;
    MSVideoSize output_size;
    MSAverageFPS output_fps;
    unsigned input_dropped, output_dropped;
    MSYuvBufAllocator *allocator;
    MSScalerContext *thumbnail, *scaler;
    int width, height, crop_w, crop_h;
    float x, y, size;
    uint64_t last;
    uint8_t rgb[256 * 256 * 3];
} Framing;

static void reset(void) {
    pthread_mutex_lock(&mutex);
    ++control.session;
    control.ready = 0;
    control.sampled = control.updated = 0;
    control.x = control.y = .5f;
    control.size = 1.f;
    pthread_mutex_unlock(&mutex);
}

// @llr LLR-TERM-VIDEO-014
static void sample(Framing *s, MSPicture *src, uint64_t now) {
    pthread_mutex_lock(&mutex);
    int due = control.enabled && now - control.sampled >= 2000;
    uint32_t session = control.session;
    pthread_mutex_unlock(&mutex);
    if (!due) return;
    int w = 256, h = (src->h * 256 / src->w) & ~1;
    if (h > 256) { h = 256; w = (src->w * 256 / src->h) & ~1; }
    if (w < 2 || h < 2) return;
    if (!s->thumbnail)
        s->thumbnail = ms_scaler_create_context(src->w, src->h, MS_YUV420P,
            w, h, MS_RGB24, MS_SCALER_METHOD_BILINEAR);
    uint8_t *planes[4] = {s->rgb, NULL, NULL, NULL};
    int strides[4] = {w * 3, 0, 0, 0};
    if (!s->thumbnail || ms_scaler_process(s->thumbnail, src->planes, src->strides, planes, strides) < 0) return;
    pthread_mutex_lock(&mutex);
    if (control.enabled && session == control.session) {
        memcpy(control.rgb, s->rgb, (size_t)w * h * 3);
        control.width = w;
        control.height = h;
        control.sampled = now;
        ++control.sequence;
        control.ready = 1;
    }
    pthread_mutex_unlock(&mutex);
}

// @llr LLR-TERM-VIDEO-013, LLR-TERM-VIDEO-015, LLR-TERM-VIDEO-016
static mblk_t *frame(Framing *s, mblk_t *input) {
    MSPicture src, dst;
    if (ms_yuv_buf_init_from_mblk(&src, input)) return input;
    uint64_t now = bctbx_get_cur_time_ms();
    if (s->width != src.w || s->height != src.h) {
        if (s->thumbnail) ms_scaler_context_free(s->thumbnail);
        if (s->scaler) ms_scaler_context_free(s->scaler);
        s->thumbnail = s->scaler = NULL;
        s->width = src.w; s->height = src.h;
        s->x = s->y = .5f; s->size = 1.f;
        reset();
    }
    sample(s, &src, now);
    pthread_mutex_lock(&mutex);
    int valid = control.enabled && control.updated && now - control.updated < 8000;
    float x = valid ? control.x : .5f, y = valid ? control.y : .5f, size = valid ? control.size : 1.f;
    pthread_mutex_unlock(&mutex);
    // Exponential easing is time-based, independent of frame-rate jitter.
    float dt = s->last ? fminf((now - s->last) / 1000.f, .2f) : 0.f;
    float alpha = 1.f - expf(-dt / .45f);
    s->last = now;
    s->x += (x - s->x) * alpha;
    s->y += (y - s->y) * alpha;
    s->size += (size - s->size) * alpha;
    if (size == 1.f && s->size > .999f) { s->x = s->y = .5f; s->size = 1.f; }
    if (s->size >= 1.f) return input;
    // Round upwards to even YUV420 sizes: never exceed the 2x zoom cap.
    int w = (int)ceilf(src.w * fmaxf(.5f, s->size) / 2) * 2;
    int h = (int)ceilf(src.h * fmaxf(.5f, s->size) / 2) * 2;
    int left = ((int)(s->x * src.w - w / 2) / 2) * 2;
    int top = ((int)(s->y * src.h - h / 2) / 2) * 2;
    left = left < 0 ? 0 : left > src.w - w ? src.w - w : left;
    top = top < 0 ? 0 : top > src.h - h ? src.h - h : top;
    if (!s->scaler || s->crop_w != w || s->crop_h != h) {
        if (s->scaler) ms_scaler_context_free(s->scaler);
        s->scaler = ms_scaler_create_context(w, h, MS_YUV420P, src.w, src.h,
            MS_YUV420P, MS_SCALER_METHOD_BILINEAR);
        s->crop_w = w; s->crop_h = h;
    }
    if (!s->scaler) return input;
    mblk_t *out = ms_yuv_buf_allocator_get(s->allocator, &dst, src.w, src.h);
    if (!out) return input;
    for (int p = 0; p < 3; ++p)
        src.planes[p] += (top >> (p != 0)) * src.strides[p] + (left >> (p != 0));
    if (ms_scaler_process(s->scaler, src.planes, src.strides, dst.planes, dst.strides) < 0) {
        freemsg(out);
        return input;
    }
    mblk_meta_copy(input, out);
    freemsg(input);
    return out;
}

/* JPEGs are independent pictures. Replace stale waiting work before decoding;
 * H.264 packets farther downstream must never be dropped this way. */
// @llr LLR-TERM-VIDEO-007
static void *decode_worker(void *context) {
    Framing *s = context;
    for (;;) {
        pthread_mutex_lock(&s->queue_mutex);
        while (!s->stopping && !s->pending) pthread_cond_wait(&s->ready, &s->queue_mutex);
        if (s->stopping) { pthread_mutex_unlock(&s->queue_mutex); break; }
        mblk_t *input = s->pending;
        s->pending = NULL;
        s->clock.time = s->pending_time;
        pthread_mutex_unlock(&s->queue_mutex);
        /* Keep metadata alive: the child consumes its input and rewrites RTP time. */
        mblk_t *metadata = dupmsg(input);
        pthread_mutex_lock(&s->decoder_mutex);
        ms_queue_put(&s->encoded, input);
        s->decoder->desc->process(s->decoder);
        pthread_mutex_unlock(&s->decoder_mutex);
        mblk_t *output;
        while ((output = ms_queue_get(&s->decoded))) {
            mblk_meta_copy(metadata, output);
            output = frame(s, output);
            MSPicture picture;
            int valid = !ms_yuv_buf_init_from_mblk(&picture, output);
            pthread_mutex_lock(&s->queue_mutex);
            if (s->completed) { freemsg(s->completed); ++s->output_dropped; }
            s->completed = output;
            if (valid) s->output_size = (MSVideoSize){picture.w, picture.h};
            pthread_mutex_unlock(&s->queue_mutex);
        }
        freemsg(metadata);
    }
    return NULL;
}
static void initialize(MSFilter *f) {
    Framing *s = ms_new0(Framing, 1);
    f->data = s;
    s->x = s->y = .5f; s->size = 1.f;
    pthread_mutex_init(&s->queue_mutex, NULL);
    pthread_mutex_init(&s->decoder_mutex, NULL);
    pthread_cond_init(&s->ready, NULL);
    ms_queue_init(&s->encoded);
    ms_queue_init(&s->decoded);
    s->allocator = ms_yuv_buf_allocator_new();
    s->decoder = ms_factory_create_filter_from_desc(f->factory, original);
    if (s->decoder) {
        s->decoder->inputs[0] = &s->encoded;
        s->decoder->outputs[0] = &s->decoded;
    }
}
static void start(MSFilter *f) {
    Framing *s = f->data;
    reset();
    s->x = s->y = .5f; s->size = 1.f; s->last = 0;
    s->stopping = 0;
    s->input_dropped = s->output_dropped = 0;
    ms_average_fps_init(&s->output_fps, "Zmala framing output fps=%f");
    if (s->decoder) {
        s->clock.time = f->ticker->time;
        ms_filter_preprocess(s->decoder, &s->clock);
        if (!pthread_create(&s->thread, NULL, decode_worker, s)) s->started = 1;
        else {
            ms_filter_postprocess(s->decoder);
            ms_error("Zmala JPEG worker could not start");
        }
    }
}
static void process(MSFilter *f) {
    Framing *s = f->data;
    mblk_t *input, *latest = NULL;
    while ((input = ms_queue_get(f->inputs[0]))) {
        if (latest) { freemsg(latest); ++s->input_dropped; }
        latest = input;
    }
    pthread_mutex_lock(&s->queue_mutex);
    if (latest) {
        if (s->started && !s->stopping) {
            if (s->pending) { freemsg(s->pending); ++s->input_dropped; }
            s->pending = latest;
            s->pending_time = f->ticker->time;
            pthread_cond_signal(&s->ready);
        } else freemsg(latest);
    }
    mblk_t *output = s->completed;
    s->completed = NULL;
    pthread_mutex_unlock(&s->queue_mutex);
    if (output) {
        ms_queue_put(f->outputs[0], output);
        ms_average_fps_activity(&s->output_fps, f->ticker->time, TRUE);
    }
}
static void stop(MSFilter *f) {
    Framing *s = f->data;
    if (s->started) {
        pthread_mutex_lock(&s->queue_mutex);
        s->stopping = 1;
        pthread_cond_signal(&s->ready);
        pthread_mutex_unlock(&s->queue_mutex);
        pthread_join(s->thread, NULL);
        s->started = 0;
        ms_filter_postprocess(s->decoder);
        ms_message("Zmala JPEG worker stopped: input_dropped=%u output_dropped=%u",
                   s->input_dropped, s->output_dropped);
    }
    if (s->pending) freemsg(s->pending);
    if (s->completed) freemsg(s->completed);
    s->pending = s->completed = NULL;
    ms_queue_flush(&s->encoded);
    ms_queue_flush(&s->decoded);
    reset();
}
static void destroy(MSFilter *f) {
    Framing *s = f->data;
    stop(f); /* also safe after failed start or an earlier postprocess */
    if (s->decoder) {
        s->decoder->inputs[0] = s->decoder->outputs[0] = NULL;
        ms_filter_destroy(s->decoder);
    }
    if (s->thumbnail) ms_scaler_context_free(s->thumbnail);
    if (s->scaler) ms_scaler_context_free(s->scaler);
    ms_yuv_buf_allocator_free(s->allocator);
    pthread_cond_destroy(&s->ready);
    pthread_mutex_destroy(&s->queue_mutex);
    pthread_mutex_destroy(&s->decoder_mutex);
    ms_free(s);
}
/* Configuration methods may be used while constructing/reconfiguring the graph.
 * Only these rare methods serialize with decoding; the process callback never does. */
#define FORWARD(name, id) static int name(MSFilter *f, void *arg) { \
    Framing *s = f->data; \
    pthread_mutex_lock(&s->decoder_mutex); \
    int result = s->decoder ? ms_filter_call_method(s->decoder, id, arg) : -1; \
    pthread_mutex_unlock(&s->decoder_mutex); \
    return result; }
static int set_size(MSFilter *f, void *arg) {
    Framing *s = f->data;
    pthread_mutex_lock(&s->decoder_mutex);
    int result = s->decoder ? ms_filter_call_method(s->decoder, MS_FILTER_SET_VIDEO_SIZE, arg) : -1;
    pthread_mutex_unlock(&s->decoder_mutex);
    if (!result) {
        pthread_mutex_lock(&s->queue_mutex);
        s->output_size = *(MSVideoSize *)arg;
        pthread_mutex_unlock(&s->queue_mutex);
    }
    return result;
}
FORWARD(add_fmtp, MS_FILTER_ADD_FMTP)
static int get_size(MSFilter *f, void *arg) {
    Framing *s = f->data;
    pthread_mutex_lock(&s->queue_mutex);
    *(MSVideoSize *)arg = s->output_size;
    pthread_mutex_unlock(&s->queue_mutex);
    return 0;
}
static int get_fps(MSFilter *f, void *arg) {
    Framing *s = f->data;
    *(float *)arg = f->ticker ? ms_average_fps_get(&s->output_fps) : 60;
    return 0;
}
static MSFilterMethod methods[] = {
    {MS_FILTER_GET_VIDEO_SIZE, get_size}, {MS_FILTER_SET_VIDEO_SIZE, set_size},
    {MS_FILTER_GET_FPS, get_fps}, {MS_FILTER_ADD_FMTP, add_fmtp}, {0, NULL}
};
static MSFilterDesc descriptor = {MS_MJPEG_DEC_ID, "ZmalaFramingMJPEG", "C20 automatic group framing",
    MS_FILTER_OTHER, NULL, 1, 1, initialize, start, process, stop, destroy, methods, 0};

int zmala_framing_register(MSFactory *factory) {
    MSFilterDesc *decoder = ms_factory_lookup_filter_by_id(factory, MS_MJPEG_DEC_ID);
    if (!decoder) return -1;
    if (decoder == &descriptor) return 0;
    original = decoder;
    ms_factory_register_filter(factory, &descriptor);
    return 0;
}
