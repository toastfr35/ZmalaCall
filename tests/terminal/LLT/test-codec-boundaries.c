// @test T-LLT-070
// @requirements LLR-TERM-VIDEO-006, LLR-TERM-VIDEO-008, LLR-TERM-VIDEO-009
// @environment native-sdk
// @plan Stub only FFmpeg codec discovery/open/submission and frame delivery while retaining real AV buffers, MediaStreamer queues, mutexes and the codec worker. Check H264 configuration, decoded pixel/timestamp ownership, encoded packet delivery, bounded input/output queues, error reporting and worker shutdown. No V4L2 encoder or physical camera is opened. Inject scaler failure and assert a rejected encode preserves the source frame.
// @pass All allocation, queue, pixel, configuration and lifecycle assertions pass under the supported SDK; these do not establish hardware encoder quality or timing.
#include "../../../zmala_terminal/linux/media/video/codec.h"
#include <mediastreamer2/msfactory.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int absent, open_failure, send_failure, packet_pending, frame_pending;
static int scaler_failure;
static int fake_scale(MSScalerContext *context, uint8_t *source[], int source_strides[], uint8_t *dest[], int dest_strides[]) {
    return scaler_failure ? -1 : ms_scaler_process(context, source, source_strides, dest, dest_strides);
}
static int64_t timestamp;
static const AVCodec *fake_find(const char *name) {
    assert(strcmp(name, "h264") == 0 || strcmp(name, "h264_v4l2m2m") == 0);
    return absent ? NULL : avcodec_find_decoder_by_name("h264");
}
static int fake_open(AVCodecContext *context, const AVCodec *codec, AVDictionary **options) {
    (void)codec; (void)options;
    assert(context->time_base.num == 1 && context->time_base.den == 90000);
    return open_failure ? AVERROR(EIO) : 0;
}
static int fake_send_frame(AVCodecContext *context, const AVFrame *frame) {
    assert(frame->width == context->width && frame->height == context->height);
    assert(frame->data[0][0] == 77);
    timestamp = frame->pts; packet_pending = 1;
    return send_failure ? AVERROR(EIO) : 0;
}
static int fake_receive_packet(AVCodecContext *context, AVPacket *packet) {
    (void)context;
    if (!packet_pending) return AVERROR(EAGAIN);
    packet_pending = 0;
    int result = av_new_packet(packet, 4); assert(result == 0);
    memcpy(packet->data, "unit", 4); packet->pts = timestamp;
    return 0;
}
static int fake_send_packet(AVCodecContext *context, const AVPacket *packet) {
    (void)context;
    assert(packet->size >= 0 && packet->buf && packet->buf->size >= (size_t)packet->size + AV_INPUT_BUFFER_PADDING_SIZE);
    timestamp = packet->pts; frame_pending = 1;
    return send_failure ? AVERROR(EIO) : 0;
}
static int fake_receive_frame(AVCodecContext *context, AVFrame *frame) {
    (void)context;
    if (!frame_pending) return AVERROR(EAGAIN);
    frame_pending = 0; frame->format = AV_PIX_FMT_YUV420P; frame->width = 16; frame->height = 16;
    int result = av_frame_get_buffer(frame, 32); assert(result == 0); frame->pts = timestamp;
    for (int plane = 0; plane < 3; ++plane)
        memset(frame->data[plane], 30 + plane, (size_t)frame->linesize[plane] * (plane ? 8 : 16));
    return 0;
}
#define avcodec_find_decoder_by_name fake_find
#define avcodec_find_encoder_by_name fake_find
#define avcodec_open2 fake_open
#define avcodec_send_frame fake_send_frame
#define avcodec_receive_packet fake_receive_packet
#define avcodec_send_packet fake_send_packet
#define avcodec_receive_frame fake_receive_frame
#define ms_scaler_process fake_scale
#include "../../../zmala_terminal/linux/media/video/codec.c"

static mblk_t *packet(int value) {
    mblk_t *result = allocb(4 + AV_INPUT_BUFFER_PADDING_SIZE, 0);
    memset(result->b_wptr, 0, 4 + AV_INPUT_BUFFER_PADDING_SIZE);
    result->b_wptr[0] = (uint8_t)value; result->b_wptr += 4;
    mblk_set_timestamp_info(result, 1234);
    return result;
}

static void test_queue_policy(MSFactory *factory, int encoder) {
    MSFilter filter = {0}; filter.factory = factory;
    zmala_codec_init(&filter, encoder); Codec *s = filter.data;
    int limit = encoder ? 2 : 16;
    for (int i = 0; i < limit + 2; ++i) zmala_codec_submit(s, packet(i));
    assert(s->input_count == limit && s->peak_input == limit && s->dropped == 2);
    int failed = zmala_codec_failed(s); assert(failed == !encoder);
    failed = zmala_codec_failed(s); assert(failed == 0);
    for (int i = 0; i < 10; ++i) publish(s, packet(i));
    assert(s->output_count == 8 && s->peak_output == 8 && s->dropped == 4);
    assert(s->reconfigure == encoder);
    mblk_t *first = zmala_codec_take(s); assert(first->b_rptr[0] == (encoder ? 0 : 2)); freemsg(first);
    for (int i = 0; i < 7; ++i) freemsg(zmala_codec_take(s));
    first = zmala_codec_take(s); assert(first == NULL && s->output_count == 0);
    zmala_codec_free(&filter);
}

static void test_context_and_frames(MSFactory *factory) {
    MSFilter filter = {0}; filter.factory = factory; zmala_codec_init(&filter, 1);
    Codec *s = filter.data;
    MSVideoConfiguration config = {1200000, 1500000, {32, 16}, 20, 1, NULL};
    absent = 1; int result = open_context(s, config); assert(result == AVERROR(ENOSYS)); absent = 0;
    open_failure = 1; result = open_context(s, config); assert(result == AVERROR(EIO)); close_context(s); open_failure = 0;
    result = open_context(s, config); assert(result == 0);
    assert(s->context->bit_rate == 1200000 && s->context->gop_size == 40);
    assert(s->context->max_b_frames == 0 && s->context->profile == AV_PROFILE_H264_BASELINE);
    MSPicture picture; mblk_t *input = ms_yuv_buf_allocator_get(s->allocator, &picture, 32, 16);
    memset(picture.planes[0], 77, (size_t)picture.strides[0] * 16); mblk_set_timestamp_info(input, 1234);
    s->force_keyframe = 1; result = encode(s, input); assert(result == 0); assert(!s->force_keyframe && s->frame->pict_type == AV_PICTURE_TYPE_I);
    mblk_t *output = zmala_codec_take(s); assert(output && output->b_wptr - output->b_rptr == 4);
    assert(memcmp(output->b_rptr, "unit", 4) == 0 && mblk_get_timestamp_info(output) == 1234); freemsg(output);
    send_failure = 1; result = encode(s, input); assert(result == AVERROR(EIO)); send_failure = 0; freemsg(input);
    input = ms_yuv_buf_allocator_get(s->allocator, &picture, 64, 32);
    memset(picture.planes[0], 77, (size_t)picture.strides[0] * 32);
    scaler_failure = 1; result = encode(s, input); scaler_failure = 0;
    assert(result == AVERROR(EINVAL) && picture.planes[0][0] == 77);
    freemsg(input);
    close_context(s); s->encoder = 0; result = open_context(s, config); assert(result == 0); assert(s->context->thread_count == 2);
    input = packet(7); result = decode(s, input); assert(result == 0); freemsg(input);
    output = zmala_codec_take(s); assert(output); result = ms_yuv_buf_init_from_mblk(&picture, output); assert(result == 0);
    assert(picture.w == 16 && picture.h == 16 && mblk_get_timestamp_info(output) == 1234);
    for (int plane = 0; plane < 3; ++plane) assert(picture.planes[plane][0] == 30 + plane);
    freemsg(output); input = packet(7); send_failure = 1; result = decode(s, input); assert(result == AVERROR(EIO)); send_failure = 0; freemsg(input);
    close_context(s); zmala_codec_free(&filter);
}

static void test_worker(MSFactory *factory) {
    MSFilter filter = {0}; filter.factory = factory; zmala_codec_init(&filter, 0);
    Codec *s = filter.data; s->reconfigure = 1;
    zmala_codec_submit(s, packet(1)); zmala_codec_start(&filter); assert(s->started);
    mblk_t *output = NULL;
    for (int attempt = 0; attempt < 1000 && !output; ++attempt) { output = zmala_codec_take(s); if (!output) usleep(1000); }
    assert(output); freemsg(output); zmala_codec_stop(&filter);
    assert(!s->started && !s->context && s->input_count == 0); zmala_codec_stop(&filter);
    send_failure = 1; zmala_codec_submit(s, packet(2)); zmala_codec_start(&filter);
    int failed = 0;
    for (int attempt = 0; attempt < 1000 && !failed; ++attempt) { failed = zmala_codec_failed(s); if (!failed) usleep(1000); }
    assert(failed); zmala_codec_stop(&filter); send_failure = 0; zmala_codec_free(&filter);
}

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    test_queue_policy(factory, 0); test_queue_policy(factory, 1);
    test_context_and_frames(factory); test_worker(factory);
    ms_factory_destroy(factory); puts("Codec boundary ownership, queue limits and worker recovery: PASS"); return 0;
}
