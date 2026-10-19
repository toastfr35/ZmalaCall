/* MediaStreamer interfaces and RFC3984 packetization stay on the ticker.
 * The worker only exchanges complete compressed access units or raw pictures.
 */
#include "codec.h"
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <string.h>

static const MSVideoConfiguration base_configurations[] = {
    /* Liblinphone limits outgoing size to this advertised ladder. Include
     * every server preset; capture-device format limits can still reduce the
     * negotiated size independently of the hardware encoder's capability. */
    {1800000, 2500000, {1920, 1080}, 15, 1, NULL},
    {900000, 1500000, {1280, 720}, 15, 1, NULL},
    {500000, 750000, {640, 480}, 15, 1, NULL},
    {350000, 700000, {640, 360}, 15, 1, NULL},
    {250000, 500000, {320, 240}, 15, 1, NULL},
    {100000, 250000, {320, 240}, 10, 1, NULL},
    {0, 100000, {320, 240}, 5, 1, NULL}
};

static MSVideoConfiguration configurations[sizeof(base_configurations) / sizeof(base_configurations[0])];
static int configurations_ready;

/* One engine per terminal process. Called before the core starts, after an
 * idle-only graph rebuild; never change the ladder under a running encoder. */
int zmala_video_set_framerate(int fps) {
    if (fps != 10 && fps != 15 && fps != 20 && fps != 25 && fps != 30) return -1;
    for (size_t i = 0; i < sizeof(configurations) / sizeof(configurations[0]); ++i) {
        configurations[i] = base_configurations[i];
        configurations[i].required_bitrate = base_configurations[i].required_bitrate * fps / 15;
        configurations[i].bitrate_limit = base_configurations[i].bitrate_limit * fps / 15;
        configurations[i].fps = base_configurations[i].fps == 15 ? fps
            : (base_configurations[i].fps < fps ? base_configurations[i].fps : fps);
    }
    configurations_ready = 1;
    return 0;
}

static void encoder_init(MSFilter *f) { zmala_codec_init(f, 1); }
static void decoder_init(MSFilter *f) { zmala_codec_init(f, 0); }

static void remember_parameter_set(Codec *s, mblk_t *nal) {
    int type = nal->b_rptr[0] & 31;
    mblk_t **slot = type == 7 ? &s->sps : type == 8 ? &s->pps : NULL;
    if (slot) {
        if (*slot) freemsg(*slot);
        *slot = dupmsg(nal);
    }
}

static size_t start_code(const uint8_t *data, size_t size, size_t from, size_t *length) {
    for (size_t i = from; i + 3 <= size; ++i) {
        if (data[i] || data[i + 1]) continue;
        if (data[i + 2] == 1) { *length = 3; return i; }
        if (i + 4 <= size && data[i + 2] == 0 && data[i + 3] == 1) {
            *length = 4;
            return i;
        }
    }
    *length = 0;
    return size;
}

void zmala_packetize_access_unit(Codec *s, mblk_t *unit, MSQueue *output) {
    MSQueue nals;
    ms_queue_init(&nals);
    size_t size = (size_t)(unit->b_wptr - unit->b_rptr), length;
    size_t position = start_code(unit->b_rptr, size, 0, &length);
    int has_sps = 0, has_pps = 0, idr = 0;
    while (position < size) {
        size_t begin = position + length, next_length;
        size_t next = start_code(unit->b_rptr, size, begin, &next_length);
        if (next > begin) {
            /* NAL views retain the shared packet allocation through RTP packing. */
            mblk_t *nal = dupb(unit);
            nal->b_rptr = unit->b_rptr + begin;
            nal->b_wptr = unit->b_rptr + next;
            int type = nal->b_rptr[0] & 31;
            has_sps |= type == 7;
            has_pps |= type == 8;
            idr |= type == 5;
            remember_parameter_set(s, nal);
            ms_queue_put(&nals, nal);
        }
        position = next;
        length = next_length;
    }
    /* Some V4L2 implementations only emit headers once. Repeat them before
     * subsequent IDRs, so a receiver can recover after packet loss or reset. */
    MSQueue complete;
    ms_queue_init(&complete);
    if (idr && !has_sps && s->sps) ms_queue_put(&complete, dupmsg(s->sps));
    if (idr && !has_pps && s->pps) ms_queue_put(&complete, dupmsg(s->pps));
    mblk_t *nal;
    while ((nal = ms_queue_get(&nals))) ms_queue_put(&complete, nal);
    rfc3984_pack(s->rtp, &complete, output, mblk_get_timestamp_info(unit));
    freemsg(unit);
}

static void encoder_process(MSFilter *f) {
    Codec *s = f->data;
    mblk_t *message;
    while ((message = zmala_codec_take(s))) zmala_packetize_access_unit(s, message, f->outputs[0]);
    /* After a delayed tick, several raw frames may arrive together. Submit
     * only the newest: stamping the entire batch with the same ticker time
     * would merge distinct encoded pictures into one RTP access unit. Dropping
     * raw capture frames is safe; dropping compressed reference frames is not.
     */
    mblk_t *latest = NULL;
    while ((message = ms_queue_get(f->inputs[0]))) {
        if (latest) freemsg(latest);
        latest = message;
    }
    if (latest) {
        mblk_set_timestamp_info(latest, (uint32_t)(f->ticker->time * 90));
        zmala_codec_submit(s, latest);
    }
    if (zmala_codec_failed(s)) zmala_codec_keyframe(s);
}

static void request_keyframe(MSFilter *f) {
    Codec *s = f->data;
    uint64_t now = f->ticker->time;
    if (!s->last_pli || now - s->last_pli >= 1000) {
        ms_filter_notify_no_arg(f, MS_VIDEO_DECODER_SEND_PLI);
        s->last_pli = now;
    }
}

static void submit_access_unit(Codec *s, MSQueue *nals, uint32_t timestamp) {
    mblk_t *nal;
    size_t size = 0;
    MSQueue saved;
    ms_queue_init(&saved);
    int has_sps = 0, has_pps = 0;
    while ((nal = ms_queue_get(nals))) {
        if (nal->b_rptr == nal->b_wptr) { freemsg(nal); continue; }
        int type = nal->b_rptr[0] & 31;
        has_sps |= type == 7;
        has_pps |= type == 8;
        remember_parameter_set(s, nal);
        size += msgdsize(nal) + 4;
        ms_queue_put(&saved, nal);
    }
    if (!size) return;
    if (!has_sps && s->sps) size += msgdsize(s->sps) + 4;
    if (!has_pps && s->pps) size += msgdsize(s->pps) + 4;
    mblk_t *unit = allocb(size + AV_INPUT_BUFFER_PADDING_SIZE, 0);
    MSQueue complete;
    ms_queue_init(&complete);
    if (!has_sps && s->sps) ms_queue_put(&complete, dupmsg(s->sps));
    if (!has_pps && s->pps) ms_queue_put(&complete, dupmsg(s->pps));
    while ((nal = ms_queue_get(&saved))) ms_queue_put(&complete, nal);
    while ((nal = ms_queue_get(&complete))) {
        memcpy(unit->b_wptr, "\0\0\0\1", 4);
        unit->b_wptr += 4;
        /* Fragmented NALs may contain chained mblk buffers. */
        for (mblk_t *part = nal; part; part = part->b_cont) {
            size_t count = part->b_wptr - part->b_rptr;
            memcpy(unit->b_wptr, part->b_rptr, count);
            unit->b_wptr += count;
        }
        freemsg(nal);
    }
    memset(unit->b_wptr, 0, AV_INPUT_BUFFER_PADDING_SIZE);
    mblk_set_timestamp_info(unit, timestamp);
    zmala_codec_submit(s, unit);
}

// @llr LLR-TERM-VIDEO-008
static void decoder_process(MSFilter *f) {
    Codec *s = f->data;
    mblk_t *message;
    bool_t produced = FALSE;
    while ((message = ms_queue_get(f->inputs[0]))) {
        uint32_t timestamp = mblk_get_timestamp_info(message);
        MSQueue nals;
        ms_queue_init(&nals);
        unsigned status = rfc3984_unpack2(s->rtp, message, &nals);
        if (status & Rfc3984FrameCorrupted) {
            // An IDR may lose a slice while its separate SPS/PPS arrive intact.
            // Preserve the received parameter NALs for recovery, but never send
            // this damaged frame's slices to the decoder worker.
            mblk_t *nal;
            while ((nal = ms_queue_get(&nals))) {
                if (nal->b_rptr < nal->b_wptr) remember_parameter_set(s, nal);
                freemsg(nal);
            }
            request_keyframe(f);
        } else if (status & Rfc3984FrameAvailable) submit_access_unit(s, &nals, timestamp);
        else ms_queue_flush(&nals);
    }
    /* Decode every compressed reference frame, but display only the newest
     * completed picture after a delayed ticker. Raw display frames are safe
     * to discard; H.264 inputs must retain their reference dependency chain. */
    mblk_t *latest = NULL;
    while ((message = zmala_codec_take(s))) {
        if (latest) { freemsg(latest); ++s->display_dropped; }
        latest = message;
    }
    if ((message = latest)) {
        MSPicture picture;
        ms_yuv_buf_init_from_mblk(&picture, message);
        pthread_mutex_lock(&s->mutex);
        int changed = s->config.vsize.width != picture.w || s->config.vsize.height != picture.h;
        s->config.vsize = (MSVideoSize){picture.w, picture.h};
        pthread_mutex_unlock(&s->mutex);
        if (changed) ms_filter_notify_no_arg(f, MS_FILTER_OUTPUT_FMT_CHANGED);
        produced = TRUE;
        ms_queue_put(f->outputs[0], message);
        if (!s->first_image) {
            ms_filter_notify_no_arg(f, MS_VIDEO_DECODER_FIRST_IMAGE_DECODED);
            s->first_image = 1;
        }
    }
    if (produced) ms_average_fps_activity(&s->fps, f->ticker->time, TRUE);
    /* A decoder can accept inter frames without an error while still waiting
     * for its first usable SPS/PPS and IDR. ICE may have discarded the initial
     * keyframe before the relay path was ready. Keep asking at the bounded PLI
     * cadence until a picture is actually decoded, even on otherwise quiet ticks.
     */
    if (zmala_codec_failed(s) || !s->first_image) request_keyframe(f);
}

static int get_config(MSFilter *f, void *arg) {
    Codec *s = f->data;
    pthread_mutex_lock(&s->mutex);
    *(MSVideoConfiguration *)arg = s->config;
    pthread_mutex_unlock(&s->mutex);
    return 0;
}
static int set_config(MSFilter *f, void *arg) {
    Codec *s = f->data;
    MSVideoConfiguration next = *(MSVideoConfiguration *)arg;
    if (next.vsize.width < 16 || next.vsize.height < 16 || next.fps <= 0 || next.fps > 30) return -1;
    pthread_mutex_lock(&s->mutex);
    int changed = next.vsize.width != s->config.vsize.width || next.vsize.height != s->config.vsize.height
                  || next.fps != s->config.fps || next.required_bitrate != s->config.required_bitrate;
    s->config = next;
    if (changed) { s->reconfigure = 1; s->force_keyframe = 1; }
    pthread_mutex_unlock(&s->mutex);
    return 0;
}
static int get_size(MSFilter *f, void *arg) { MSVideoConfiguration c; get_config(f, &c); *(MSVideoSize *)arg = c.vsize; return 0; }
static int get_fps(MSFilter *f, void *arg) {
    Codec *s = f->data;
    MSVideoConfiguration c;
    get_config(f, &c);
    *(float *)arg = s->encoder ? c.fps : ms_average_fps_get(&s->fps);
    if (!s->encoder && f->ticker && f->ticker->time - s->fps.last_frame_time >= 1000) *(float *)arg = 0;
    return 0;
}
static int config_list(MSFilter *f, void *arg) { (void)f; *(const MSVideoConfiguration **)arg = configurations; return 0; }
static int keyframe(MSFilter *f, void *arg) { (void)arg; zmala_codec_keyframe(f->data); return 0; }
static int pixfmt(MSFilter *f, void *arg) { (void)f; *(MSPixFmt *)arg = MS_YUV420P; return 0; }
static int supports_pixfmt(MSFilter *f, void *arg) { (void)f; MSVideoEncoderPixFmt *fmt = arg; fmt->supported = fmt->pixfmt == MS_YUV420P; return 0; }
static int accelerated(MSFilter *f, void *arg) { (void)f; *(bool_t *)arg = TRUE; return 0; }
static int ignore(MSFilter *f, void *arg) { (void)f; (void)arg; return 0; }
static int reset_first(MSFilter *f, void *arg) { (void)arg; ((Codec *)f->data)->first_image = 0; return 0; }
static int fmtp(MSFilter *f, void *arg) {
    Codec *s = f->data;
    char value[8];
    if (fmtp_get_value(arg, "packetization-mode", value, sizeof(value))) {
        s->packetization_mode = atoi(value);
        rfc3984_set_mode(s->rtp, s->packetization_mode);
    }
    return 0;
}
static int mtu(MSFilter *f, void *arg) {
    ms_factory_set_payload_max_size(f->factory, *(int *)arg);
    return 0;
}

static MSFilterMethod encoder_methods[] = {
    {MS_FILTER_GET_PIX_FMT, pixfmt}, {MS_FILTER_ADD_FMTP, fmtp}, {MS_FILTER_SET_MTU, mtu},
    {MS_VIDEO_ENCODER_SUPPORTS_PIXFMT, supports_pixfmt},
    {MS_VIDEO_ENCODER_GET_CONFIGURATION_LIST, config_list},
    {MS_VIDEO_ENCODER_SET_CONFIGURATION, set_config}, {MS_VIDEO_ENCODER_GET_CONFIGURATION, get_config},
    {MS_VIDEO_ENCODER_REQ_VFU, keyframe}, {MS_VIDEO_ENCODER_NOTIFY_PLI, keyframe},
    {MS_VIDEO_ENCODER_NOTIFY_FIR, keyframe}, {MS_VIDEO_ENCODER_ENABLE_AVPF, ignore},
    {MS_VIDEO_ENCODER_IS_HARDWARE_ACCELERATED, accelerated}, {0, NULL}
};
static MSFilterMethod decoder_methods[] = {
    {MS_FILTER_GET_VIDEO_SIZE, get_size}, {MS_FILTER_GET_FPS, get_fps},
    {MS_FILTER_GET_PIX_FMT, pixfmt}, {MS_FILTER_ADD_FMTP, fmtp},
    {MS_VIDEO_DECODER_ENABLE_AVPF, ignore}, {MS_VIDEO_DECODER_RESET_FIRST_IMAGE_NOTIFICATION, reset_first},
    {MS_VIDEO_DECODER_FREEZE_ON_ERROR, ignore}, {0, NULL}
};
static MSFilterDesc encoder_desc = {
    MS_FILTER_PLUGIN_ID, "ZmalaV4L2H264Enc", "Pi V4L2 H264 encoder", MS_FILTER_ENCODER, "H264", 1, 1,
    encoder_init, zmala_codec_start, encoder_process, zmala_codec_stop, zmala_codec_free,
    encoder_methods, MS_FILTER_IS_HW_ACCELERATED
};
static MSFilterDesc decoder_desc = {
    MS_FILTER_PLUGIN_ID, "ZmalaFFmpegH264Dec", "FFmpeg H264 decoder", MS_FILTER_DECODER, "H264", 1, 1,
    decoder_init, zmala_codec_start, decoder_process, zmala_codec_stop, zmala_codec_free,
    decoder_methods, 0
};
/* Explicit registration keeps other applications' SDK plugin paths intact. */
int zmala_video_register(MSFactory *factory) {
    if (!configurations_ready) zmala_video_set_framerate(15);
    if (!factory || !avcodec_find_encoder_by_name("h264_v4l2m2m")) return -1;
    ms_factory_enable_filter_from_name(factory, "MSOpenH264Enc", FALSE);
    ms_factory_enable_filter_from_name(factory, "MSOpenH264Dec", FALSE);
    if (ms_factory_lookup_filter_by_name(factory, "MSH264Dec"))
        ms_factory_enable_filter_from_name(factory, "MSH264Dec", FALSE);
    ms_factory_register_filter(factory, &encoder_desc);
    ms_factory_register_filter(factory, &decoder_desc);
    if (ms_factory_get_encoder(factory, "H264") != &encoder_desc ||
        ms_factory_get_decoder(factory, "H264") != &decoder_desc) return -1;
    ms_message("Zmala C20 video registered: encoding=V4L2 decoding=FFmpeg software");
    return 0;
}
