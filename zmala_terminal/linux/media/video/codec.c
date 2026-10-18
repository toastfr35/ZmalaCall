/* FFmpeg owns V4L2 buffers. A dedicated worker keeps device waits off the
 * MediaStreamer ticker. Queues are bounded to avoid latency growing forever.
 * All AVCodec objects are confined to that worker until it has been joined.
 */
#include "codec.h"
#include <errno.h>
#include <string.h>
#include <libavutil/error.h>
#include <libavutil/opt.h>
#include <bctoolbox/port.h>

static void close_context(Codec *s) {
    if (s->scaler) ms_scaler_context_free(s->scaler);
    s->scaler = NULL;
    avcodec_free_context(&s->context);
    av_frame_free(&s->frame);
    av_packet_free(&s->packet);
}

// @llr LLR-TERM-VIDEO-006
static int open_context(Codec *s, MSVideoConfiguration config) {
    const char *name = s->encoder ? "h264_v4l2m2m" : "h264";
    const AVCodec *codec = avcodec_find_decoder_by_name(name);
    if (s->encoder) codec = avcodec_find_encoder_by_name(name);
    if (!codec) return AVERROR(ENOSYS);
    s->context = avcodec_alloc_context3(codec);
    s->frame = av_frame_alloc();
    s->packet = av_packet_alloc();
    if (!s->context || !s->frame || !s->packet) return AVERROR(ENOMEM);
    AVCodecContext *ctx = s->context;
    ctx->time_base = (AVRational){1, 90000};
    ctx->pkt_timebase = (AVRational){1, 90000};
    if (s->encoder) {
        ctx->width = config.vsize.width;
        ctx->height = config.vsize.height;
        ctx->pix_fmt = AV_PIX_FMT_YUV420P;
        ctx->framerate = av_d2q(config.fps, 1000);
        ctx->bit_rate = config.required_bitrate;
        ctx->gop_size = (int)(config.fps * 2);
        ctx->max_b_frames = 0;
        ctx->profile = AV_PROFILE_H264_BASELINE;
    } else {
        ctx->thread_count = 2;
    }
    int result = avcodec_open2(ctx, codec, NULL);
    if (result < 0) return result;
    ms_message("Zmala %s: %s %dx%d", s->encoder ? "encoder" : "decoder",
               name, ctx->width, ctx->height);
    return 0;
}

static void publish(Codec *s, mblk_t *message) {
    pthread_mutex_lock(&s->mutex);
    /* Decoder output is display data: the newest frames matter most. Encoded
     * frames cannot be discarded arbitrarily without losing references. */
    if (s->output_count >= 8) {
        if (s->encoder) {
            /* Keep queued headers/reference frames intact. Dropping the oldest
             * packet can lose the only SPS/PPS emitted by V4L2, leaving the
             * receiver unable to decode even subsequent keyframes. Discard this
             * access unit and reopen before encoding again: that emits fresh
             * headers and an IDR without relying on driver support for pict_type.
             */
            freemsg(message);
            ++s->dropped;
            s->reconfigure = 1;
            pthread_mutex_unlock(&s->mutex);
            return;
        }
        freemsg(ms_queue_get(&s->output));
        --s->output_count;
        ++s->dropped;
    }
    ms_queue_put(&s->output, message);
    ++s->output_count;
    if (s->output_count > s->peak_output) s->peak_output = s->output_count;
    pthread_mutex_unlock(&s->mutex);
}

// @llr LLR-TERM-VIDEO-009
static int encode(Codec *s, mblk_t *input) {
    MSPicture picture;
    if (ms_yuv_buf_init_from_mblk(&picture, input) < 0) return AVERROR(EINVAL);
    AVFrame *frame = s->frame;
    frame->format = AV_PIX_FMT_YUV420P;
    frame->width = s->context->width;
    frame->height = s->context->height;
    frame->pts = mblk_get_timestamp_info(input);
    /* Reuse the raw picture allocation. make_writable allocates a replacement
     * only if FFmpeg still holds a reference; it never overwrites in-flight
     * frames. Reconfiguration frees the old buffer with the codec context. */
    int result = frame->buf[0] ? av_frame_make_writable(frame) : av_frame_get_buffer(frame, 32);
    if (result < 0) return result;
    if (picture.w != frame->width || picture.h != frame->height) {
        /* SDK quality changes can leave the source/size converter at its old
         * dimensions. Honor the encoder target instead of reopening forever
         * on EINVAL. Keep conversion off the ticker and reuse its context. */
        if (!s->scaler || s->scaler_width != picture.w || s->scaler_height != picture.h) {
            if (s->scaler) ms_scaler_context_free(s->scaler);
            s->scaler = ms_scaler_create_context(picture.w, picture.h, MS_YUV420P,
                frame->width, frame->height, MS_YUV420P, MS_SCALER_METHOD_BILINEAR);
            s->scaler_width = picture.w;
            s->scaler_height = picture.h;
        }
        if (!s->scaler) return AVERROR(ENOSYS);
        if (ms_scaler_process(s->scaler, picture.planes, picture.strides, frame->data, frame->linesize) < 0)
            return AVERROR(EINVAL);
    } else {
        for (int plane = 0; plane < 3; ++plane) {
            int width = plane ? picture.w / 2 : picture.w;
            int height = plane ? picture.h / 2 : picture.h;
            for (int row = 0; row < height; ++row)
                memcpy(frame->data[plane] + row * frame->linesize[plane],
                       picture.planes[plane] + row * picture.strides[plane], width);
        }
    }
    pthread_mutex_lock(&s->mutex);
    int keyframe = s->force_keyframe;
    s->force_keyframe = 0;
    pthread_mutex_unlock(&s->mutex);
    frame->pict_type = keyframe ? AV_PICTURE_TYPE_I : AV_PICTURE_TYPE_NONE;
    result = avcodec_send_frame(s->context, frame);
    if (result < 0) return result;
    while ((result = avcodec_receive_packet(s->context, s->packet)) == 0) {
        mblk_t *message = allocb(s->packet->size, 0);
        memcpy(message->b_wptr, s->packet->data, s->packet->size);
        message->b_wptr += s->packet->size;
        mblk_set_timestamp_info(message, (uint32_t)s->packet->pts);
        publish(s, message);
        av_packet_unref(s->packet);
    }
    return result == AVERROR(EAGAIN) ? 0 : result;
}

static void release_packet(void *message, uint8_t *bytes) {
    (void)bytes;
    freemsg(message);
}

static int decode(Codec *s, mblk_t *input) {
    int size = (int)(input->b_wptr - input->b_rptr);
    av_packet_unref(s->packet);
    /* submit_access_unit supplies contiguous, padded bytes. A retained mblk
     * lets FFmpeg's decoding threads borrow them without another packet copy. */
    mblk_t *held = dupmsg(input);
    s->packet->buf = av_buffer_create(input->b_rptr, size + AV_INPUT_BUFFER_PADDING_SIZE,
                                     release_packet, held, AV_BUFFER_FLAG_READONLY);
    if (!s->packet->buf) { freemsg(held); return AVERROR(ENOMEM); }
    s->packet->data = input->b_rptr;
    s->packet->size = size;
    s->packet->pts = mblk_get_timestamp_info(input);
    int result = avcodec_send_packet(s->context, s->packet);
    if (result < 0) return result;
    while ((result = avcodec_receive_frame(s->context, s->frame)) == 0) {
        AVFrame *frame = s->frame;
        if (frame->format != AV_PIX_FMT_YUV420P) return AVERROR(ENOSYS);
        MSPicture picture;
        mblk_t *message = ms_yuv_buf_allocator_get(s->allocator, &picture, frame->width, frame->height);
        if (!message) return AVERROR(ENOMEM);
        for (int plane = 0; plane < 3; ++plane) {
            int width = plane ? frame->width / 2 : frame->width;
            int height = plane ? frame->height / 2 : frame->height;
            for (int row = 0; row < height; ++row)
                memcpy(picture.planes[plane] + row * picture.strides[plane],
                       frame->data[plane] + row * frame->linesize[plane], width);
        }
        mblk_set_timestamp_info(message, (uint32_t)frame->pts);
        publish(s, message);
        av_frame_unref(frame);
    }
    return result == AVERROR(EAGAIN) ? 0 : result;
}

// @llr LLR-TERM-VIDEO-008
static void *worker(void *argument) {
    Codec *s = argument;
    for (;;) {
        pthread_mutex_lock(&s->mutex);
        while (!s->stopping && s->input_count == 0) pthread_cond_wait(&s->ready, &s->mutex);
        if (s->stopping) { pthread_mutex_unlock(&s->mutex); break; }
        mblk_t *input = ms_queue_get(&s->input);
        uint64_t queued = bctbx_get_cur_time_ms() - s->input_times[s->input_head];
        s->input_head = (s->input_head + 1) % 16;
        if (queued > s->max_queue_ms) s->max_queue_ms = queued;
        --s->input_count;
        MSVideoConfiguration config = s->config;
        int reconfigure = s->reconfigure;
        s->reconfigure = 0;
        pthread_mutex_unlock(&s->mutex);
        if (reconfigure) close_context(s);
        int result = 0;
        if (!s->context) result = open_context(s, config);
        if (result == 0) result = s->encoder ? encode(s, input) : decode(s, input);
        freemsg(input);
        if (result < 0) {
            char error[AV_ERROR_MAX_STRING_SIZE];
            av_strerror(result, error, sizeof(error));
            ms_warning("Zmala %s error: %s", s->encoder ? "encoder" : "decoder", error);
            pthread_mutex_lock(&s->mutex);
            s->failed = 1;
            pthread_mutex_unlock(&s->mutex);
            close_context(s);
        }
    }
    close_context(s);
    return NULL;
}

void zmala_codec_init(MSFilter *filter, int encoder) {
    Codec *s = ms_new0(Codec, 1);
    filter->data = s;
    s->encoder = encoder;
    s->config = (MSVideoConfiguration){500000, 500000, {640, 480}, 15, 1, NULL};
    s->packetization_mode = 1;
    pthread_mutex_init(&s->mutex, NULL);
    pthread_cond_init(&s->ready, NULL);
    ms_queue_init(&s->input);
    ms_queue_init(&s->output);
    s->rtp = rfc3984_new_with_factory(filter->factory);
    rfc3984_set_mode(s->rtp, 1);
    rfc3984_enable_stap_a(s->rtp, FALSE);
    s->allocator = ms_yuv_buf_allocator_new();
    ms_average_fps_init(&s->fps, "Zmala H264 decoded fps=%f");
}

void zmala_codec_start(MSFilter *filter) {
    Codec *s = filter->data;
    s->stopping = 0;
    s->first_image = 0;
    int result = pthread_create(&s->thread, NULL, worker, s);
    if (result) { s->failed = 1; ms_error("Zmala codec worker start failed: %s", strerror(result)); }
    else s->started = 1;
}

void zmala_codec_stop(MSFilter *filter) {
    Codec *s = filter->data;
    if (!s->started) return;
    pthread_mutex_lock(&s->mutex);
    s->stopping = 1;
    pthread_cond_signal(&s->ready);
    pthread_mutex_unlock(&s->mutex);
    pthread_join(s->thread, NULL);
    s->started = 0;
    ms_message("Zmala %s stopped: dropped=%d display_dropped=%d peak_input=%d peak_output=%d max_queue_ms=%llu",
               s->encoder ? "encoder" : "decoder", s->dropped, s->display_dropped,
               s->peak_input, s->peak_output, (unsigned long long)s->max_queue_ms);
}

void zmala_codec_free(MSFilter *filter) {
    Codec *s = filter->data;
    zmala_codec_stop(filter);
    ms_queue_flush(&s->input);
    ms_queue_flush(&s->output);
    rfc3984_destroy(s->rtp);
    if (s->sps) freemsg(s->sps);
    if (s->pps) freemsg(s->pps);
    ms_yuv_buf_allocator_free(s->allocator);
    pthread_cond_destroy(&s->ready);
    pthread_mutex_destroy(&s->mutex);
    ms_free(s);
}

// @llr LLR-TERM-VIDEO-008
void zmala_codec_submit(Codec *s, mblk_t *message) {
    pthread_mutex_lock(&s->mutex);
    int limit = s->encoder ? 2 : 16;
    if (s->input_count >= limit) {
        freemsg(ms_queue_get(&s->input));
        s->input_head = (s->input_head + 1) % 16;
        --s->input_count;
        ++s->dropped;
        if (!s->encoder) s->failed = 1; /* ticker asks the peer for a new keyframe */
    }
    ms_queue_put(&s->input, message);
    s->input_times[s->input_tail] = bctbx_get_cur_time_ms();
    s->input_tail = (s->input_tail + 1) % 16;
    ++s->input_count;
    if (s->input_count > s->peak_input) s->peak_input = s->input_count;
    pthread_cond_signal(&s->ready);
    pthread_mutex_unlock(&s->mutex);
}

mblk_t *zmala_codec_take(Codec *s) {
    pthread_mutex_lock(&s->mutex);
    mblk_t *message = ms_queue_get(&s->output);
    if (message) --s->output_count;
    pthread_mutex_unlock(&s->mutex);
    return message;
}

int zmala_codec_failed(Codec *s) {
    pthread_mutex_lock(&s->mutex);
    int failed = s->failed;
    s->failed = 0;
    pthread_mutex_unlock(&s->mutex);
    return failed;
}

void zmala_codec_keyframe(Codec *s) {
    uint64_t now = bctbx_get_cur_time_ms();
    pthread_mutex_lock(&s->mutex);
    /* A damaged picture can trigger several PLI/FIR requests. Encoding every
     * following frame as an IDR amplifies loss into a high-bitrate feedback
     * loop. Coalesce recovery requests to at most one per second. */
    if (!s->last_keyframe_request || now - s->last_keyframe_request >= 1000) {
        s->force_keyframe = 1;
        s->last_keyframe_request = now;
    }
    pthread_mutex_unlock(&s->mutex);
}
