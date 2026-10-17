/* Inspect the installed MediaStreamer factory without registering a SIP account.
 * Build: cc probe-video-codecs.c -o probe-video-codecs -lmediastreamer2
 */
#include <stdio.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msfilter.h>

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    if (!factory) return 1;
    const char *codecs[] = {"H264", "VP8"};
    for (unsigned i = 0; i < 2; ++i) {
        MSFilterDesc *encoder = ms_factory_get_encoder(factory, codecs[i]);
        MSFilterDesc *decoder = ms_factory_get_decoder(factory, codecs[i]);
        printf("%s encoder=%s hardware=%d decoder=%s hardware=%d\n", codecs[i],
               encoder ? encoder->name : "none",
               encoder ? !!(encoder->flags & MS_FILTER_IS_HW_ACCELERATED) : 0,
               decoder ? decoder->name : "none",
               decoder ? !!(decoder->flags & MS_FILTER_IS_HW_ACCELERATED) : 0);
    }
    ms_factory_destroy(factory);
    return 0;
}
