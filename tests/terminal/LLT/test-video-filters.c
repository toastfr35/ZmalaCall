// @test T-LLT-072
// @requirements LLR-TERM-VIDEO-006, LLR-TERM-VIDEO-008
// @environment native-sdk
// @plan Exercise real H264 Annex-B parsing/RFC3984 packing, cached SPS/PPS recovery, frame coalescing and SDK filter methods with real queues and buffers. Stub decoder unpack statuses and event notifications to inject lost/corrupt/incomplete frames deterministically. Retain received SPS/PPS from a damaged frame without submitting its slices, then assert they precede the next intact access unit. Tick a decoder without frames or errors and require rate-limited PLI retries until its first decoded picture; check retries resume after notification reset. Assert padded/chained input ownership, newest-picture display, configuration validation and supported rate ladders without starting codecs or hardware. Inject a mismatched SDK encoder selection and assert registration refuses it.
// @pass All byte, timestamp, queue, event and configuration assertions pass using the supported MediaStreamer SDK; no camera or encoder device is opened.
#include "../../../zmala_terminal/linux/media/video/codec.h"
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned unpack_status;
static unsigned notifications[32];
static int notification_count;
static int wrong_encoder;
static MSFilterDesc *fake_encoder(MSFactory *factory, const char *mime) {
    return wrong_encoder ? NULL : ms_factory_get_encoder(factory, mime);
}
static void fake_notify(MSFilter *filter, unsigned event) {
    (void)filter; assert(notification_count < 32); notifications[notification_count++] = event;
}
static unsigned fake_unpack(Rfc3984Context *rtp, mblk_t *input, MSQueue *nals) {
    (void)rtp; ms_queue_put(nals, input); return unpack_status;
}
#define ms_filter_notify_no_arg fake_notify
#define rfc3984_unpack2 fake_unpack
#define ms_factory_get_encoder fake_encoder
#include "../../../zmala_terminal/linux/media/video/filters.c"

static mblk_t *bytes(const uint8_t *data, size_t length) {
    mblk_t *message = allocb(length, 0);
    if (length) memcpy(message->b_wptr, data, length);
    message->b_wptr += length; mblk_set_timestamp_info(message, 9000); return message;
}
static const uint8_t headers[] = {0,0,0,1,0x67,0x42,0,0x1f,0,0,1,0x68,0xaa,0,0,0,1,0x65,0x44};
static const uint8_t idr[] = {0,0,1,0x65,0x55};

static void test_packetization(MSFilter *f) {
    Codec *s = f->data; MSQueue packed; ms_queue_init(&packed);
    size_t length = 77; size_t position = start_code((const uint8_t *)"bad", 3, 0, &length);
    assert(position == 3 && length == 0);
    zmala_packetize_access_unit(s, bytes(headers, sizeof(headers)), &packed);
    assert(s->sps && s->pps);
    int count = 0; mblk_t *message;
    while ((message = ms_queue_get(&packed))) { assert(mblk_get_timestamp_info(message) == 9000); ++count; freemsg(message); }
    assert(count == 3);
    zmala_packetize_access_unit(s, bytes(idr, sizeof(idr)), &packed);
    const int expected[] = {7,8,5}; count = 0;
    while ((message = ms_queue_get(&packed))) {
        assert(count < 3 && (message->b_rptr[0] & 31) == expected[count]); ++count; freemsg(message);
    }
    assert(count == 3);
    zmala_packetize_access_unit(s, bytes((const uint8_t *)"bad", 3), &packed);
    assert(ms_queue_empty(&packed));
}

static void test_encoder_tick(MSFilter *f) {
    Codec *s = f->data;
    ms_queue_put(&s->output, bytes(headers, sizeof(headers))); s->output_count++;
    ms_queue_put(f->inputs[0], bytes((const uint8_t *)"older", 5));
    ms_queue_put(f->inputs[0], bytes((const uint8_t *)"newest", 6));
    s->failed = 1; f->ticker->time = 123;
    encoder_process(f);
    assert(s->input_count == 1 && s->force_keyframe);
    mblk_t *raw = ms_queue_get(&s->input); --s->input_count;
    assert(raw->b_wptr - raw->b_rptr == 6 && memcmp(raw->b_rptr, "newest", 6) == 0);
    assert(mblk_get_timestamp_info(raw) == 123 * 90); freemsg(raw);
    assert(!ms_queue_empty(f->outputs[0])); ms_queue_flush(f->outputs[0]);
    encoder_process(f); assert(s->input_count == 0);
}

static void test_reassembly(MSFilter *f) {
    Codec *s = f->data; MSQueue nals; ms_queue_init(&nals);
    ms_queue_put(&nals, bytes(NULL, 0)); submit_access_unit(s, &nals, 77); assert(s->input_count == 0);
    mblk_t *nal = bytes((const uint8_t *)"\x65\x11", 2);
    nal->b_cont = bytes((const uint8_t *)"\x22\x33", 2); ms_queue_put(&nals, nal);
    submit_access_unit(s, &nals, 77); assert(s->input_count == 1);
    mblk_t *unit = ms_queue_get(&s->input); --s->input_count;
    const uint8_t expected[] = {0,0,0,1,0x67,0x42,0,0x1f,0,0,0,1,0x68,0xaa,0,0,0,1,0x65,0x11,0x22,0x33};
    assert(unit->b_wptr-unit->b_rptr == (int)sizeof(expected)); assert(memcmp(unit->b_rptr,expected,sizeof(expected)) == 0);
    for (int i=0;i<AV_INPUT_BUFFER_PADDING_SIZE;++i) assert(unit->b_wptr[i] == 0);
    assert(mblk_get_timestamp_info(unit) == 77); freemsg(unit);
}

static void test_decoder_tick(MSFilter *f) {
    Codec *s=f->data; f->ticker->time=100; unpack_status=Rfc3984FrameCorrupted;
    ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x65",1)); decoder_process(f);
    assert(notification_count == 1 && notifications[0] == MS_VIDEO_DECODER_SEND_PLI);
    ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x67\x42\x00\x1f",4)); decoder_process(f);
    ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x68\xaa",2)); decoder_process(f);
    assert(s->sps && s->pps && s->input_count == 0);
    ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x65",1)); decoder_process(f); assert(notification_count == 1);
    f->ticker->time=1100; s->failed=1; decoder_process(f); assert(notification_count == 2);
    unpack_status=0; ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x65",1)); decoder_process(f); assert(s->input_count == 0);
    unpack_status=Rfc3984FrameAvailable; ms_queue_put(f->inputs[0],bytes((const uint8_t *)"\x65\x33",2)); decoder_process(f); assert(s->input_count == 1);
    mblk_t *recovered=ms_queue_peek_first(&s->input);
    const uint8_t expected[]={0,0,0,1,0x67,0x42,0,0x1f,0,0,0,1,0x68,0xaa,0,0,0,1,0x65,0x33};
    assert(msgdsize(recovered)==sizeof(expected) && !memcmp(recovered->b_rptr,expected,sizeof(expected)));
    ms_queue_flush(&s->input); s->input_count=0;
    for (int i=0;i<2;++i) {
        MSPicture picture; mblk_t *raw=ms_yuv_buf_allocator_get(s->allocator,&picture,32,16);
        memset(picture.planes[0],40+i,(size_t)picture.strides[0]*16); ms_queue_put(&s->output,raw); ++s->output_count;
    }
    decoder_process(f); assert(s->display_dropped == 1 && s->first_image == 1);
    assert(notification_count == 4 && notifications[2] == MS_FILTER_OUTPUT_FMT_CHANGED && notifications[3] == MS_VIDEO_DECODER_FIRST_IMAGE_DECODED);
    mblk_t *raw=ms_queue_get(f->outputs[0]); MSPicture picture;
    int result=ms_yuv_buf_init_from_mblk(&picture,raw); assert(result == 0 && picture.planes[0][0] == 41); freemsg(raw);
    float fps=0; f->ticker->time+=1000; result=get_fps(f,&fps); assert(result == 0 && fps == 0);
    result=reset_first(f,NULL); assert(result == 0 && !s->first_image);
}

static void test_methods(MSFilter *f) {
    Codec *s=f->data; const MSVideoConfiguration *ladder;
    for (int fps=10;fps<=30;fps+=5) {
        int result=zmala_video_set_framerate(fps); assert(result == 0);
        result=config_list(f,&ladder); assert(result == 0 && ladder[0].fps == fps);
        assert(ladder[0].required_bitrate == 1800000*fps/15 && ladder[6].fps == 5);
    }
    int result=zmala_video_set_framerate(17); assert(result == -1);
    MSVideoConfiguration next={700000,900000,{640,480},20,1,NULL}, actual;
    result=set_config(f,&next); assert(result == 0 && s->reconfigure && s->force_keyframe);
    s->reconfigure=0; result=set_config(f,&next); assert(result == 0 && !s->reconfigure);
    next.fps=31; result=set_config(f,&next); assert(result == -1);
    next.fps=20; next.vsize.width=8; result=set_config(f,&next); assert(result == -1);
    result=get_config(f,&actual); assert(result == 0 && actual.vsize.width == 640 && actual.fps == 20);
    MSVideoSize size; result=get_size(f,&size); assert(result == 0 && size.height == 480);
    float fps; result=get_fps(f,&fps); assert(result == 0 && fps == 20);
    MSPixFmt format; result=pixfmt(f,&format); assert(result == 0 && format == MS_YUV420P);
    MSVideoEncoderPixFmt supported={0}; supported.pixfmt=MS_YUV420P; result=supports_pixfmt(f,&supported); assert(result == 0 && supported.supported);
    supported.pixfmt=MS_RGB24; result=supports_pixfmt(f,&supported); assert(result == 0 && !supported.supported);
    bool_t hardware=FALSE; result=accelerated(f,&hardware); assert(result == 0 && hardware);
    result=ignore(f,NULL); assert(result == 0); result=keyframe(f,NULL); assert(result == 0);
    result=fmtp(f,"packetization-mode=0"); assert(result == 0 && s->packetization_mode == 0);
    result=fmtp(f,"profile-level-id=42e01f"); assert(result == 0 && s->packetization_mode == 0);
    int payload=1200; result=mtu(f,&payload); assert(result == 0 && ms_factory_get_payload_max_size(f->factory) == 1200);
}

static void test_first_picture_recovery(MSFilter *f) {
    Codec *s = f->data;
    notification_count = 0;
    f->ticker->time = 100;
    decoder_process(f);
    assert(notification_count == 1 && notifications[0] == MS_VIDEO_DECODER_SEND_PLI);
    f->ticker->time = 1099; decoder_process(f); assert(notification_count == 1);
    f->ticker->time = 1100; decoder_process(f); assert(notification_count == 2);
    assert(!s->failed && !s->first_image);
    MSPicture picture;
    ms_queue_put(&s->output, ms_yuv_buf_allocator_get(s->allocator, &picture, 32, 16));
    ++s->output_count;
    decoder_process(f); assert(s->first_image);
    int after_picture = notification_count;
    f->ticker->time = 3100; decoder_process(f); assert(notification_count == after_picture);
    reset_first(f, NULL); decoder_process(f);
    assert(notification_count == after_picture + 1 && notifications[after_picture] == MS_VIDEO_DECODER_SEND_PLI);
    ms_queue_flush(f->outputs[0]);
}

int main(void) {
    MSFactory *factory=ms_factory_new_with_voip();
    int result=zmala_video_register(NULL); assert(result == -1);
    result=zmala_video_register(factory); assert(result == 0);
    wrong_encoder=1; result=zmala_video_register(factory); assert(result == -1); wrong_encoder=0;
    MSQueue input,output; ms_queue_init(&input); ms_queue_init(&output);
    MSQueue *inputs[]={&input}, *outputs[]={&output}; MSTicker ticker={0};
    MSFilter filter={0}; filter.factory=factory; filter.inputs=inputs; filter.outputs=outputs; filter.ticker=&ticker;
    encoder_init(&filter); test_packetization(&filter); test_encoder_tick(&filter); test_reassembly(&filter); test_methods(&filter); zmala_codec_free(&filter);
    decoder_init(&filter); test_decoder_tick(&filter); zmala_codec_free(&filter);
    decoder_init(&filter); test_first_picture_recovery(&filter); zmala_codec_free(&filter);
    ms_queue_flush(&input); ms_queue_flush(&output); ms_factory_destroy(factory);
    puts("H264 filter packetization, recovery, queue and configuration checks: PASS"); return 0;
}
