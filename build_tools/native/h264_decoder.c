/* Preserve H.264 NAL bytes between RFC3984 and OpenH264. The bundled SDK
 * decoder rewrites 00 00 03 00 xx sequences, corrupting valid Pi SPS data.
 * OpenH264 itself already handles emulation-prevention bytes. */
#include <winsock2.h>
#include <windows.h>
#ifndef ORTP_PUBLIC
#define ORTP_PUBLIC __declspec(dllimport)
#endif
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/rfc3984.h>
#include <wels/codec_api.h>
#include <bctoolbox/crypto.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    ISVCDecoder *decoder;
    Rfc3984Context *unpacker;
    MSYuvBufAllocator *allocator;
    MSVideoSize size;
    MSAverageFPS fps;
    mblk_t *sps, *pps;
    uint64_t last_pli;
    int initialized, first;
} Decoder;

static void initialize(MSFilter *f) {
    Decoder *d = ms_new0(Decoder, 1);
    d->size = (MSVideoSize){MS_VIDEO_SIZE_UNKNOWN_W, MS_VIDEO_SIZE_UNKNOWN_H};
    d->unpacker = rfc3984_new_with_factory(f->factory);
    d->allocator = ms_yuv_buf_allocator_new();
    ms_average_fps_init(&d->fps, "Zmala OpenH264 fps=%f");
    if (WelsCreateDecoder(&d->decoder) == 0 && d->decoder) {
        SDecodingParam params = {0};
        params.uiTargetDqLayer = 255;
        params.eEcActiveIdc = ERROR_CON_FRAME_COPY_CROSS_IDR;
        params.sVideoProperty.size = sizeof(params.sVideoProperty);
        params.sVideoProperty.eVideoBsType = VIDEO_BITSTREAM_AVC;
        d->initialized = (*d->decoder)->Initialize(d->decoder, &params) == 0;
    }
    if (!d->initialized) ms_error("Zmala OpenH264 initialization failed");
    f->data = d;
}

static void request_picture(MSFilter *f) {
    Decoder *d = f->data;
    uint64_t now = f->ticker->time;
    if (!d->last_pli || now - d->last_pli >= 1000) {
        ms_filter_notify_no_arg(f, MS_VIDEO_DECODER_SEND_PLI);
        d->last_pli = now ? now : 1;
    }
}

static void decode_picture(MSFilter *f, MSQueue *nals, uint32_t timestamp) {
    Decoder *d = f->data;
    size_t size = 0;
    mblk_t *nal;
    int has_sps = 0, has_pps = 0;
    for (nal = ms_queue_peek_first(nals); !ms_queue_end(nals, nal); nal = ms_queue_next(nals, nal)) {
        unsigned type = nal->b_wptr > nal->b_rptr ? nal->b_rptr[0] & 31 : 0;
        has_sps |= type == 7; has_pps |= type == 8;
        mblk_t **slot = type == 7 ? &d->sps : type == 8 ? &d->pps : NULL;
        if (slot) {
            if (*slot) freemsg(*slot);
            *slot = dupmsg(nal);
        }
        size += msgdsize(nal) + 4;
    }
    /* Cache SDP and in-band headers alike. The SDK unpacker's out-of-band
     * injection misses some fragmented IDRs, so prepend missing headers here. */
    if (!has_pps && d->pps) {
        ms_queue_insert(nals, ms_queue_peek_first(nals), dupmsg(d->pps));
        size += msgdsize(d->pps) + 4;
    }
    if (!has_sps && d->sps) {
        ms_queue_insert(nals, ms_queue_peek_first(nals), dupmsg(d->sps));
        size += msgdsize(d->sps) + 4;
    }
    /* Bound memory even for a malformed remote access unit. */
    if (!size || size > 8 * 1024 * 1024 || !d->initialized) {
        ms_queue_flush(nals);
        request_picture(f);
        return;
    }
    mblk_t *bytes = allocb(size, 0);
    while ((nal = ms_queue_get(nals))) {
        memcpy(bytes->b_wptr, "\0\0\0\1", 4);
        bytes->b_wptr += 4;
        for (mblk_t *part = nal; part; part = part->b_cont) {
            size_t length = part->b_wptr - part->b_rptr;
            memcpy(bytes->b_wptr, part->b_rptr, length);
            bytes->b_wptr += length;
        }
        freemsg(nal);
    }
    unsigned char *planes[3] = {0};
    SBufferInfo info = {0};
    info.uiInBsTimeStamp = timestamp;
    DECODING_STATE state = (*d->decoder)->DecodeFrameNoDelay(d->decoder, bytes->b_rptr, (int)size, planes, &info);
    freemsg(bytes);
    if (state != dsErrorFree) request_picture(f);
    if (!info.iBufferStatus) return;
    int width = info.UsrData.sSystemBuffer.iWidth, height = info.UsrData.sSystemBuffer.iHeight;
    if (width < 16 || height < 16 || width > 4096 || height > 2160) return;
    MSPicture picture;
    mblk_t *frame = ms_yuv_buf_allocator_get(d->allocator, &picture, width, height);
    if (!frame) return;
    for (int plane = 0; plane < 3; ++plane) {
        int w = plane ? width / 2 : width, h = plane ? height / 2 : height;
        for (int row = 0; row < h; ++row)
            memcpy(picture.planes[plane] + row * picture.strides[plane],
                   planes[plane] + row * info.UsrData.sSystemBuffer.iStride[plane ? 1 : 0], w);
    }
    if (d->size.width != width || d->size.height != height) {
        d->size = (MSVideoSize){width, height};
        ms_filter_notify_no_arg(f, MS_FILTER_OUTPUT_FMT_CHANGED);
    }
    mblk_set_timestamp_info(frame, (uint32_t)info.uiOutYuvTimeStamp);
    ms_queue_put(f->outputs[0], frame);
    ms_average_fps_activity(&d->fps, f->ticker->time, TRUE);
    if (!d->first) {
        d->first = 1;
        ms_filter_notify_no_arg(f, MS_VIDEO_DECODER_FIRST_IMAGE_DECODED);
    }
}

static void process(MSFilter *f) {
    Decoder *d = f->data;
    MSQueue nals;
    ms_queue_init(&nals);
    mblk_t *packet;
    while ((packet = ms_queue_get(f->inputs[0]))) {
        uint32_t timestamp = mblk_get_timestamp_info(packet);
        unsigned status = rfc3984_unpack2(d->unpacker, packet, &nals);
        if (status & Rfc3984FrameCorrupted) request_picture(f);
        if (status & Rfc3984FrameAvailable) decode_picture(f, &nals, timestamp);
    }
    ms_queue_flush(&nals);
}

static void destroy(MSFilter *f) {
    Decoder *d = f->data;
    if (d->decoder) {
        if (d->initialized) (*d->decoder)->Uninitialize(d->decoder);
        WelsDestroyDecoder(d->decoder);
    }
    rfc3984_destroy(d->unpacker);
    if (d->sps) freemsg(d->sps);
    if (d->pps) freemsg(d->pps);
    ms_yuv_buf_allocator_free(d->allocator);
    ms_free(d);
}
static int size(MSFilter *f, void *arg) { *(MSVideoSize *)arg = ((Decoder *)f->data)->size; return 0; }
static int fps(MSFilter *f, void *arg) {
    Decoder *d = f->data;
    *(float *)arg = f->ticker && f->ticker->time - d->fps.last_frame_time < 1000 ? ms_average_fps_get(&d->fps) : 0;
    return 0;
}
static int format(MSFilter *f, void *arg) { (void)f; *(MSPixFmt *)arg = MS_YUV420P; return 0; }
static mblk_t *parameter_set(const char *text, size_t length) {
    unsigned char decoded[1024];
    size_t size = sizeof(decoded);
    if (bctbx_base64_decode(decoded, &size, (const unsigned char *)text, length) != 0 || !size) return NULL;
    mblk_t *nal = allocb(size, 0);
    memcpy(nal->b_wptr, decoded, size);
    nal->b_wptr += size;
    return nal;
}
static int fmtp(MSFilter *f, void *arg) {
    char value[2048];
    if (!fmtp_get_value(arg, "sprop-parameter-sets", value, sizeof(value))) return 0;
    char *comma = strchr(value, ',');
    if (!comma) return -1;
    mblk_t *sps = parameter_set(value, (size_t)(comma - value));
    mblk_t *pps = parameter_set(comma + 1, strlen(comma + 1));
    if (!sps || !pps || (sps->b_rptr[0] & 31) != 7 || (pps->b_rptr[0] & 31) != 8) {
        if (sps) freemsg(sps);
        if (pps) freemsg(pps);
        return -1;
    }
    Decoder *d = f->data;
    if (d->sps) freemsg(d->sps);
    if (d->pps) freemsg(d->pps);
    d->sps = sps; d->pps = pps;
    return 0;
}
static int ignore(MSFilter *f, void *arg) { (void)f; (void)arg; return 0; }
static int reset(MSFilter *f, void *arg) { (void)arg; ((Decoder *)f->data)->first = 0; return 0; }
static MSFilterMethod methods[] = {
    {MS_FILTER_GET_VIDEO_SIZE, size}, {MS_FILTER_GET_FPS, fps}, {MS_FILTER_GET_PIX_FMT, format},
    {MS_FILTER_ADD_FMTP, fmtp}, {MS_VIDEO_DECODER_ENABLE_AVPF, ignore},
    {MS_VIDEO_DECODER_FREEZE_ON_ERROR, ignore}, {MS_VIDEO_DECODER_RESET_FIRST_IMAGE_NOTIFICATION, reset}, {0, NULL}
};
static MSFilterDesc descriptor = {MS_FILTER_PLUGIN_ID, "ZmalaOpenH264Dec", "Byte-preserving OpenH264 decoder",
    MS_FILTER_DECODER, "H264", 1, 1, initialize, NULL, process, NULL, destroy, methods, 0};

__declspec(dllexport) int zmala_h264_decoder_register(MSFactory *factory) {
    if (!factory) return -1;
    if (ms_factory_lookup_filter_by_name(factory, "MSOpenH264Dec"))
        ms_factory_enable_filter_from_name(factory, "MSOpenH264Dec", FALSE);
    ms_factory_register_filter(factory, &descriptor);
    return ms_factory_get_decoder(factory, "H264") == &descriptor ? 0 : -1;
}
