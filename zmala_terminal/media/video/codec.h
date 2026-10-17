/* C20 media path: Pi H.264 encoding and FFmpeg software decoding.
 * Liblinphone owns SIP, RTP transport and the UI-facing call state. */
#ifndef ZMALA_HW_CODEC_H
#define ZMALA_HW_CODEC_H
#include <pthread.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/rfc3984.h>
#include <libavcodec/avcodec.h>

typedef struct {
    pthread_t thread;
    pthread_mutex_t mutex;
    pthread_cond_t ready;
    MSQueue input, output;
    int started, stopping, encoder, failed, force_keyframe;
    int input_count, output_count, dropped, reconfigure;
    int peak_input, peak_output, display_dropped;
    uint64_t input_times[16], max_queue_ms;
    unsigned input_head, input_tail;
    MSVideoConfiguration config;
    AVCodecContext *context;
    AVFrame *frame;
    AVPacket *packet;
    MSScalerContext *scaler; /* worker-owned fallback when SDK input is not resized */
    int scaler_width, scaler_height;
    Rfc3984Context *rtp;
    MSYuvBufAllocator *allocator;
    int first_image, packetization_mode;
    uint64_t last_pli, last_keyframe_request;
    MSAverageFPS fps;
    mblk_t *sps, *pps; /* ticker-owned parameter sets for keyframe recovery */
} Codec;

void zmala_codec_init(MSFilter *filter, int encoder);
void zmala_codec_start(MSFilter *filter);
void zmala_codec_stop(MSFilter *filter);
void zmala_codec_free(MSFilter *filter);
/* submit transfers message ownership even if it is dropped; take transfers it
 * back to the ticker. Stop/join the worker before freeing queues or codec state. */
void zmala_codec_submit(Codec *codec, mblk_t *message);
mblk_t *zmala_codec_take(Codec *codec);
int zmala_codec_failed(Codec *codec);
void zmala_codec_keyframe(Codec *codec);
void zmala_packetize_access_unit(Codec *codec, mblk_t *unit, MSQueue *output);
#endif
