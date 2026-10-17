/* Camera/network-free regression: fragmented Pi H.264 must decode unchanged. */
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
#include <bctoolbox/crypto.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int run(MSFactory *factory, const unsigned char *bytes, size_t length, int out_of_band) {
    MSFilter *decoder = ms_factory_create_decoder(factory, "H264");
    MSQueue input, output, nals;
    ms_queue_init(&input); ms_queue_init(&output); ms_queue_init(&nals);
    decoder->inputs[0] = &input; decoder->outputs[0] = &output;
    MSTicker ticker = {0}; decoder->ticker = &ticker;
    if (decoder->desc->preprocess) decoder->desc->preprocess(decoder);
    Rfc3984Context *packer = rfc3984_new_with_factory(factory);
    rfc3984_set_mode(packer, 1); rfc3984_enable_stap_a(packer, FALSE);
    unsigned frames = 0, wrong = 0;
    uint16_t sequence = 0;
    char parameters[2048] = "sprop-parameter-sets=";
    for (size_t position = 0; position + 3 < length;) {
        if (bytes[position] || bytes[position + 1] || bytes[position + 2] != 1) { ++position; continue; }
        size_t start = position + 3, end = start;
        while (end + 3 < length && (bytes[end] || bytes[end + 1] || bytes[end + 2] != 1)) ++end;
        if (end + 3 >= length) end = length;
        position = end;
        while (end > start && bytes[end - 1] == 0) --end;
        unsigned type = bytes[start] & 31;
        if (out_of_band && (type == 7 || type == 8)) {
            if (type == 7) strcpy(parameters, "sprop-parameter-sets=");
            unsigned char encoded[1024]; size_t count = sizeof(encoded);
            if (bctbx_base64_encode(encoded, &count, bytes + start, end - start)) { puts("base64 encoding failed"); return 1; }
            encoded[count] = 0;
            strcat(parameters, (char *)encoded);
            if (type == 7) strcat(parameters, ",");
            else if (ms_filter_call_method(decoder, MS_FILTER_ADD_FMTP, parameters)) { printf("SDP parsing failed: %s\n", parameters); return 1; }
            continue;
        }
        mblk_t *nal = allocb(end - start, 0);
        memcpy(nal->b_wptr, bytes + start, end - start); nal->b_wptr += end - start;
        ms_queue_put(&nals, nal);
        if (type != 1 && type != 5) continue;
        MSQueue packets; ms_queue_init(&packets);
        rfc3984_pack(packer, &nals, &packets, (uint32_t)(ticker.time * 90));
        mblk_t *packet;
        while ((packet = ms_queue_get(&packets))) {
            mblk_set_cseq(packet, sequence++); ms_queue_put(&input, packet);
        }
        decoder->desc->process(decoder);
        mblk_t *frame;
        while ((frame = ms_queue_get(&output))) {
            MSPicture picture;
            if (ms_yuv_buf_init_from_mblk(&picture, frame) < 0 || picture.w != 1920 || picture.h != 1080) ++wrong;
            ++frames; freemsg(frame);
        }
        ticker.time += 67;
    }
    if (decoder->desc->postprocess) decoder->desc->postprocess(decoder);
    decoder->inputs[0] = NULL; decoder->outputs[0] = NULL; decoder->ticker = NULL;
    ms_filter_destroy(decoder); rfc3984_destroy(packer);
    ms_queue_flush(&input); ms_queue_flush(&output); ms_queue_flush(&nals);
    printf("%s parameter sets: %u 1080p frames, %u wrong sizes\n", out_of_band ? "SDP" : "in-band", frames, wrong);
    return frames != 3 || wrong;
}

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    FILE *input = fopen(argv[2], "rb");
    if (!input) return 2;
    unsigned char bytes[32768]; size_t length = fread(bytes, 1, sizeof(bytes), input); fclose(input);
    MSFactory *factory = ms_factory_new_with_voip();
    HMODULE library = LoadLibraryA(argv[1]);
    if (!library) return 2;
    int (*register_decoder)(MSFactory *) = (void *)GetProcAddress(library, "zmala_h264_decoder_register");
    if (!register_decoder || register_decoder(factory)) return 2;
    int failed = run(factory, bytes, length, 0) | run(factory, bytes, length, 1);
    ms_factory_destroy(factory); FreeLibrary(library);
    return failed;
}
