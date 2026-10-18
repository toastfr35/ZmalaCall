/* Benchmark the installed echo canceller, without a microphone or SIP call.
 * Build: cc -O2 probe-audio-processing.c -o probe-audio-processing
 *        -lmediastreamer2 -lortp -lbctoolbox
 * Each row processes five seconds of deterministic near/far mono audio.
 * This tests processing cost, not acoustic echo-removal quality.
 */
#define _POSIX_C_SOURCE 200809L
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <stdio.h>
#include <time.h>

static double seconds(void) {
    struct timespec time;
    clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &time);
    return time.tv_sec + time.tv_nsec / 1e9;
}

static void benchmark(MSFactory *factory, int rate, int tail) {
    MSFilter *filter = ms_factory_create_filter_from_name(factory, "MSSpeexEC");
    if (!filter) return;
    MSQueue input[2], output[2];
    MSTicker ticker = {0};
    filter->ticker = &ticker;
    for (int pin = 0; pin < 2; ++pin) {
        ms_queue_init(&input[pin]); ms_queue_init(&output[pin]);
        filter->inputs[pin] = &input[pin]; filter->outputs[pin] = &output[pin];
    }
    ms_filter_call_method(filter, MS_FILTER_SET_SAMPLE_RATE, &rate);
    ms_filter_call_method(filter, MS_ECHO_CANCELLER_SET_TAIL_LENGTH, &tail);
    filter->desc->preprocess(filter);
    unsigned random = 1;
    double before = seconds();
    for (int tick = 0; tick < 500; ++tick) {
        for (int pin = 0; pin < 2; ++pin) {
            mblk_t *message = allocb(rate / 100 * 2, 0);
            short *samples = (short *)message->b_wptr;
            for (int sample = 0; sample < rate / 100; ++sample) {
                random = random * 1664525u + 1013904223u;
                samples[sample] = (short)((random >> 16) & 4095) - 2048;
            }
            message->b_wptr += rate / 100 * 2;
            ms_queue_put(&input[pin], message);
        }
        ticker.time = tick * 10;
        filter->desc->process(filter);
        for (int pin = 0; pin < 2; ++pin) ms_queue_flush(&output[pin]);
    }
    double cpu = seconds() - before;
    printf("{\"rate_hz\":%d,\"tail_ms\":%d,\"audio_seconds\":5,\"cpu_seconds\":%.3f,\"one_core_percent\":%.1f}\n",
           rate, tail, cpu, cpu / 5 * 100);
    filter->desc->postprocess(filter);
    for (int pin = 0; pin < 2; ++pin) {
        ms_queue_flush(&input[pin]); ms_queue_flush(&output[pin]);
        filter->inputs[pin] = NULL; filter->outputs[pin] = NULL;
    }
    ms_filter_destroy(filter);
}

int main(void) {
    MSFactory *factory = ms_factory_new_with_voip();
    if (!factory) return 1;
    benchmark(factory, 48000, 250);
    benchmark(factory, 16000, 250);
    benchmark(factory, 16000, 100);
    ms_factory_destroy(factory);
    return 0;
}
