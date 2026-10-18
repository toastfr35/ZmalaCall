/* Opt-in Pi hardware regression: synthetic pictures only, no camera or calls.
 * Stop the terminal first. Build from repository root:
 * cc -std=c11 -D_GNU_SOURCE -O2 -Wall -Wextra -Werror -pthread
 *   -Izmala_terminal/linux/media/video build_tools/linux/test-video-resize.c
 *   zmala_terminal/linux/media/video/codec.c -o /tmp/test-video-resize
 *   $(pkg-config --cflags --libs libavcodec libavutil)
 *   -lmediastreamer2 -lortp -lbctoolbox
 * Run under an external timeout: timeout 30 /tmp/test-video-resize
 */
#include "codec.h"
#include <mediastreamer2/msfactory.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int receive(Codec *encoder, AVCodecContext *decoder, int width, int height) {
    int count = 0;
    mblk_t *unit;
    AVPacket *packet = av_packet_alloc();
    AVFrame *frame = av_frame_alloc();
    while ((unit = zmala_codec_take(encoder))) {
        int size = (int)(unit->b_wptr - unit->b_rptr);
        if (av_new_packet(packet, size) < 0) return -1;
        memcpy(packet->data, unit->b_rptr, size);
        freemsg(unit);
        if (avcodec_send_packet(decoder, packet) < 0) return -1;
        av_packet_unref(packet);
        while (avcodec_receive_frame(decoder, frame) == 0) {
            if (frame->width == width && frame->height == height) ++count;
            av_frame_unref(frame);
        }
    }
    av_frame_free(&frame);
    av_packet_free(&packet);
    return count;
}

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    MSFilter filter = {0};
    filter.factory = factory;
    zmala_codec_init(&filter, 1);
    Codec *encoder = filter.data;
    AVCodecContext *decoder = avcodec_alloc_context3(avcodec_find_decoder(AV_CODEC_ID_H264));
    if (!decoder || avcodec_open2(decoder, decoder->codec, NULL) < 0) return 1;
    zmala_codec_start(&filter);
    /* Same size, target-only change, source-only change, then restore target.
     * The source-only phase checks cached scaler replacement without a reopen. */
    const int phases[][4] = {{640,480,640,480}, {640,480,320,240},
                            {1280,720,320,240}, {640,480,640,480}};
    int failed = 0;
    for (unsigned phase = 0; phase < sizeof(phases)/sizeof(phases[0]); ++phase) {
        int source_w = phases[phase][0], source_h = phases[phase][1];
        int target_w = phases[phase][2], target_h = phases[phase][3];
        pthread_mutex_lock(&encoder->mutex);
        encoder->reconfigure = encoder->config.vsize.width != target_w || encoder->config.vsize.height != target_h;
        encoder->config.vsize = (MSVideoSize){target_w, target_h};
        encoder->force_keyframe = 1;
        pthread_mutex_unlock(&encoder->mutex);
        int decoded = 0;
        for (int index = 0; index < 30; ++index) {
            MSPicture picture;
            mblk_t *input = ms_yuv_buf_alloc(&picture, source_w, source_h);
            for (int plane = 0; plane < 3; ++plane) {
                int rows = plane ? source_h/2 : source_h;
                int columns = plane ? source_w/2 : source_w;
                for (int y = 0; y < rows; ++y)
                    memset(picture.planes[plane] + y * picture.strides[plane], plane ? 128 : 32+index*4, columns);
            }
            mblk_set_timestamp_info(input, (phase*30+index)*6000);
            zmala_codec_submit(encoder, input);
            usleep(70000);
            int count = receive(encoder, decoder, target_w, target_h);
            if (count < 0) { failed = 1; break; }
            decoded += count;
        }
        int error = zmala_codec_failed(encoder);
        printf("source=%dx%d target=%dx%d decoded=%d failed=%d\n", source_w, source_h, target_w, target_h, decoded, error);
        if (decoded < 20 || error) failed = 1;
    }
    zmala_codec_free(&filter);
    avcodec_free_context(&decoder);
    ms_factory_destroy(factory);
    return failed;
}
