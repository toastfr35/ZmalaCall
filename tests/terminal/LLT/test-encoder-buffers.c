// @test T-LLT-051
// @requirements TLLR054
// @environment native-sdk
// @plan Replace only FFmpeg frame submission with a deterministic EAGAIN boundary; feed equal-size and resized YUV pictures through the actual encoder preparation path. Check raw buffer and scaler reuse, no scaler on exact-size input and preservation of input pixels.
// @pass Pointer reuse, shape and pixel assertions must all pass without opening a hardware encoder or camera.

#include "../../../zmala_terminal/linux/media/video/codec.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
static int unit_send_frame(AVCodecContext *context, const AVFrame *frame) {
    (void)context;
    assert(frame->data[0]);
    return AVERROR(EAGAIN);
}
#define avcodec_send_frame unit_send_frame
#include "../../../zmala_terminal/linux/media/video/codec.c"
#undef avcodec_send_frame

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    Codec codec = {0};
    int result;
    pthread_mutex_init(&codec.mutex, NULL);
    codec.context = avcodec_alloc_context3(NULL);
    codec.context->width = 640; codec.context->height = 480;
    codec.frame = av_frame_alloc();
    MSYuvBufAllocator *allocator = ms_yuv_buf_allocator_new();
    MSPicture picture;
    mblk_t *input = ms_yuv_buf_allocator_get(allocator, &picture, 640, 480);
    memset(picture.planes[0], 99, (size_t)picture.strides[0] * 480);
    mblk_set_timestamp_info(input, 1234);
    result = encode(&codec, input);
    assert(result == AVERROR(EAGAIN));
    uint8_t *buffer = codec.frame->data[0];
    assert(codec.scaler == NULL);
    assert(codec.frame->pts == 1234 && buffer[0] == 99);
    result = encode(&codec, input);
    assert(result == AVERROR(EAGAIN));
    assert(codec.frame->data[0] == buffer && codec.scaler == NULL);
    assert(picture.planes[0][0] == 99);
    freemsg(input);
    input = ms_yuv_buf_allocator_get(allocator, &picture, 320, 240);
    memset(picture.planes[0], 77, (size_t)picture.strides[0] * 240);
    result = encode(&codec, input);
    assert(result == AVERROR(EAGAIN));
    void *scaler = codec.scaler;
    assert(scaler && codec.frame->data[0] == buffer);
    result = encode(&codec, input);
    assert(result == AVERROR(EAGAIN));
    assert(codec.scaler == scaler && codec.frame->data[0] == buffer);
    assert(picture.planes[0][0] == 77);
    freemsg(input);
    close_context(&codec);
    ms_yuv_buf_allocator_free(allocator);
    pthread_mutex_destroy(&codec.mutex);
    ms_factory_destroy(factory);
    puts("Encoder buffer reuse and exact-size bypass: PASS");
    return 0;
}
