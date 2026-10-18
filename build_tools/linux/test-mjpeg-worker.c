/* A deliberately blocked decoder must not block the ticker or grow queues. */
#include "../../zmala_terminal/linux/media/video/auto-framing.c"
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <unistd.h>

static atomic_int entered, release_decoder;
static void slow_decode(MSFilter *f) {
    atomic_store(&entered, 1);
    while (!atomic_load(&release_decoder)) usleep(1000);
    mblk_t *m;
    while ((m = ms_queue_get(f->inputs[0]))) {
        mblk_set_timestamp_info(m, 999); /* adapter must restore capture metadata */
        ms_queue_put(f->outputs[0], m);
    }
}
static MSFilterDesc fake = {MS_FILTER_PLUGIN_ID, "BlockedJpegTest", "Worker test",
    MS_FILTER_OTHER, NULL, 1, 1, NULL, NULL, slow_decode, NULL, NULL, NULL, 0};
static mblk_t *picture(Framing *s, unsigned timestamp) {
    MSPicture p;
    mblk_t *m = ms_yuv_buf_allocator_get(s->allocator, &p, 64, 48);
    assert(m);
    memset(p.planes[0], 80, 64 * 48);
    mblk_set_timestamp_info(m, timestamp);
    return m;
}
static void wait_entered(void) {
    for (int i = 0; i < 1000 && !atomic_load(&entered); ++i) usleep(1000);
    assert(atomic_load(&entered));
}
static void real_jpeg(const char *path) {
    FILE *file = fopen(path, "rb"); assert(file);
    int seek_result = fseek(file, 0, SEEK_END); assert(!seek_result);
    long length = ftell(file); rewind(file);
    assert(length > 30 && length < 8 * 1024 * 1024);
    mblk_t *jpeg = allocb(length, 0);
    size_t read_count = fread(jpeg->b_wptr, 1, length, file);
    assert(read_count == (size_t)length);
    jpeg->b_wptr += length; fclose(file);
    MSFactory *factory = ms_factory_new_with_voip();
    int registered = zmala_framing_register(factory); assert(!registered);
    MSFilter *f = ms_factory_create_filter(factory, MS_MJPEG_DEC_ID);
    MSQueue in, out; ms_queue_init(&in); ms_queue_init(&out);
    f->inputs[0] = &in; f->outputs[0] = &out;
    MSVideoSize wanted = {640, 480};
    int configured = ms_filter_call_method(f, MS_FILTER_SET_VIDEO_SIZE, &wanted);
    assert(!configured);
    MSTicker ticker = {0};
    for (int round = 0; round < 4; ++round) {
        ms_filter_preprocess(f, &ticker);
        /* A malformed picture must not prevent the next valid JPEG decoding. */
        mblk_t *bad = allocb(64, 0); memset(bad->b_wptr, 0, 64); bad->b_wptr += 64;
        ms_queue_put(&in, bad); process(f); usleep(30000);
        mblk_t *input = ms_yuv_buf_alloc_from_buffer(640, 480, dupmsg(jpeg));
        mblk_set_timestamp_info(input, 9000 + round);
        ms_queue_put(&in, input); process(f);
        mblk_t *output = NULL;
        for (int i = 0; i < 1000 && !output; ++i) {
            usleep(1000); ++ticker.time; process(f); output = ms_queue_get(&out);
        }
        assert(output && mblk_get_timestamp_info(output) == (uint32_t)(9000 + round));
        MSPicture picture; assert(!ms_yuv_buf_init_from_mblk(&picture, output));
        assert(picture.w == 640 && picture.h == 480);
        freemsg(output); ms_filter_postprocess(f);
    }
    f->inputs[0] = f->outputs[0] = NULL;
    ms_filter_destroy(f); ms_factory_destroy(factory); freemsg(jpeg);
    puts("Real JPEG decoding, invalid input recovery and repeated start/stop passed");
}
int main(int argc, char **argv) {
    MSFactory *factory = ms_factory_new_with_voip();
    original = &fake;
    MSFilter *f = ms_factory_create_filter_from_desc(factory, &descriptor);
    Framing *s = f->data;
    MSQueue in, out; ms_queue_init(&in); ms_queue_init(&out);
    f->inputs[0] = &in; f->outputs[0] = &out;
    MSTicker ticker = {0}; ticker.time = 100;
    zmala_framing_enable(0);
    ms_filter_preprocess(f, &ticker);
    assert(s->started);
    ms_queue_put(&in, picture(s, 1)); process(f); wait_entered();
    uint64_t before = bctbx_get_cur_time_ms();
    ms_queue_put(&in, picture(s, 2)); process(f);
    ms_queue_put(&in, picture(s, 3)); process(f);
    assert(bctbx_get_cur_time_ms() - before < 50);
    pthread_mutex_lock(&s->queue_mutex);
    assert(s->pending && mblk_get_timestamp_info(s->pending) == 3 && s->input_dropped == 1);
    pthread_mutex_unlock(&s->queue_mutex);
    atomic_store(&release_decoder, 1);
    int ready = 0;
    for (int i = 0; i < 1000 && !ready; ++i) {
        pthread_mutex_lock(&s->queue_mutex);
        ready = s->completed && mblk_get_timestamp_info(s->completed) == 3;
        pthread_mutex_unlock(&s->queue_mutex);
        if (!ready) usleep(1000);
    }
    assert(ready);
    ticker.time += 50; process(f);
    mblk_t *result = ms_queue_get(&out);
    assert(result && mblk_get_timestamp_info(result) == 3);
    freemsg(result);
    ms_filter_postprocess(f);
    assert(!s->started && !s->pending && !s->completed);
    /* Repeated calls cannot return an earlier call's frame. */
    for (int i = 0; i < 20; ++i) {
        ms_filter_preprocess(f, &ticker);
        process(f); assert(ms_queue_empty(&out));
        ms_queue_put(&in, picture(s, 4)); process(f);
        ms_filter_postprocess(f);
        assert(!s->started && !s->pending && !s->completed);
    }
    f->inputs[0] = f->outputs[0] = NULL;
    ms_filter_destroy(f); ms_factory_destroy(factory);
    puts("JPEG worker: nonblocking ticker, bounded queues, metadata and restart checks passed");
    if (argc == 2) real_jpeg(argv[1]);
    return 0;
}
