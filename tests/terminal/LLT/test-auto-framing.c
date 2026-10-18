// @test T-LLT-001
// @requirements LLR-TERM-VIDEO-013, LLR-TERM-VIDEO-014, LLR-TERM-VIDEO-015, LLR-TERM-VIDEO-016, LLR-TERM-VIDEO-017
// @environment native-sdk
// @plan Feed synthetic 1080p YUV frames through the framing filter; assert crop bounds, 200 percent ceiling, unchanged source pixels/metadata, full-frame copy bypass and stale-detector fencing. Inject scaler and worker-start failures and exercise size/FPS reporting with and without a decoder.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

/* Crop safety/metadata, stale-result fencing and 1080p per-frame cost. */
#include <pthread.h>
#include <errno.h>
#include <mediastreamer2/msvideo.h>
static int fail_thread, fail_scaler;
static int unit_thread_create(pthread_t *thread, const pthread_attr_t *attributes, void *(*worker)(void *), void *context) {
    return fail_thread ? EAGAIN : pthread_create(thread, attributes, worker, context);
}
static int unit_scaler_process(MSScalerContext *context, uint8_t *source[], int source_strides[], uint8_t *dest[], int dest_strides[]) {
    return fail_scaler ? -1 : ms_scaler_process(context, source, source_strides, dest, dest_strides);
}
#define pthread_create unit_thread_create
#define ms_scaler_process unit_scaler_process
#include "../../../zmala_terminal/linux/media/video/auto-framing.c"
#include <assert.h>
#include <stdio.h>
#include <time.h>

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    int registered = zmala_framing_register(factory);
    assert(registered == 0);
    MSFilter *filter = ms_factory_create_filter(factory, MS_MJPEG_DEC_ID);
    assert(filter && filter->desc == &descriptor);
    Framing *s = filter->data;
    assert(s->decoder && s->decoder->desc != &descriptor);
    MSPicture src, dst;
    mblk_t *input = ms_yuv_buf_allocator_get(s->allocator, &src, 1920, 1080);
    assert(input);
    for (int p = 0; p < 3; ++p) {
        int w = p ? 960 : 1920, h = p ? 540 : 1080;
        for (int y = 0; y < h; ++y)
            for (int x = 0; x < w; ++x) src.planes[p][y * src.strides[p] + x] = p ? 128 : x * 240 / w;
    }
    mblk_set_timestamp_info(input, 123456);
    mblk_t *output = frame(s, dupmsg(input));
    assert(output->b_datap == input->b_datap); /* disabled: no new picture */
    freemsg(output);
    zmala_framing_enable(1);
    output = frame(s, dupmsg(input));
    assert(output->b_datap == input->b_datap); /* enabled but wide: no crop copy */
    freemsg(output);
    uint8_t rgb[256 * 256 * 3]; int w, h;
    uint64_t token = zmala_framing_take(rgb, &w, &h);
    assert(token && w == 256 && h == 144);
    assert(!zmala_framing_take(rgb, &w, &h));
    zmala_framing_target(token, .75f, .5f, .5f);
    assert(control.size == .5f);
    zmala_framing_target(token, .75f, .5f, .4f);
    assert(control.size == .5f); /* hard 200% ceiling */
    s->x = .75f; s->y = .5f; s->size = .5f;
    output = frame(s, dupmsg(input));
    assert(!ms_yuv_buf_init_from_mblk(&dst, output));
    assert(dst.w == 1920 && dst.h == 1080 && mblk_get_timestamp_info(output) == 123456);
    assert(dst.planes[0][0] >= 118 && dst.planes[0][0] <= 122);
    assert(src.planes[0][0] == 0); /* tee/source data remains immutable */
    freemsg(output);
    clock_t benchmark_started = clock();
    for (int i = 0; i < 120; ++i) {
        output = frame(s, dupmsg(input));
        freemsg(output);
    }
    printf("1080p crop/resize: %.2f ms/frame\n", 1000. * (clock() - benchmark_started) / CLOCKS_PER_SEC / 120);
    for (int p = 0; p < 3; ++p) {
        int w = p ? 960 : 1920, h = p ? 540 : 1080;
        for (int y = 0; y < h; ++y) memset(src.planes[p] + y * src.strides[p], p == 0 ? 81 : p == 1 ? 90 : 240, w);
    }
    control.sampled = 0;
    output = frame(s, dupmsg(input));
    freemsg(output);
    token = zmala_framing_take(rgb, &w, &h);
    assert(token && rgb[0] > 200 && rgb[1] < 50 && rgb[2] < 50); /* RGB, not BGR */
    reset();
    zmala_framing_target(token, .75f, .5f, .5f);
    assert(control.size == 1.f); /* previous call's inference cannot pan this call */
    zmala_framing_enable(0);
    for (int i = 0; i < 40; ++i) {
        s->last = bctbx_get_cur_time_ms() - 100;
        output = frame(s, dupmsg(input));
        freemsg(output);
    }
    assert(s->size == 1.f);
    // Failed scaling must preserve the caller-owned original frame.
    zmala_framing_enable(1); s->size=.5f; fail_scaler=1;
    output=frame(s,dupmsg(input)); assert(output->b_datap == input->b_datap); freemsg(output); fail_scaler=0;
    MSVideoSize reported; int status=get_size(filter,&reported); assert(status == 0);
    float fps; status=get_fps(filter,&fps); assert(status == 0 && fps == 60);
    MSTicker ticker={0}; filter->ticker=&ticker; fail_thread=1; start(filter);
    assert(!s->started); fail_thread=0; status=get_fps(filter,&fps); assert(status == 0);
    MSQueue incoming,outgoing; ms_queue_init(&incoming); ms_queue_init(&outgoing);
    filter->inputs[0]=&incoming; filter->outputs[0]=&outgoing; ms_queue_put(&incoming,dupmsg(input)); process(filter);
    assert(ms_queue_empty(&incoming) && !s->pending);
    status=add_fmtp(filter,"test=value"); (void)status;
    MSFilter *decoder=s->decoder; s->decoder=NULL;
    status=add_fmtp(filter,"test=value"); assert(status == -1);
    s->decoder=decoder; filter->inputs[0]=filter->outputs[0]=NULL; filter->ticker=NULL;
    freemsg(input);
    ms_filter_destroy(filter);
    ms_factory_destroy(factory);
    puts("Framing native checks passed");
    return 0;
}
