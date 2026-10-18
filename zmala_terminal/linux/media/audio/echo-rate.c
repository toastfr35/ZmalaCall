/* Process the C20 microphone at its native 16 kHz speech sample rate.
 * The original filter owns its DSP state, tail length and buffer management.
 * Returning the capped rate through GET_SAMPLE_RATE lets MediaStreamer adjust
 * Opus and its existing sound-device resamplers; RTP's Opus clock stays 48 kHz.
 */
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msinterfaces.h>

static MSFilterDesc *original;
static int maximum_rate = 16000;

typedef struct { MSFilter *child; int rate; } EchoState;

/* A child filter owns Speex state and its lock. Never swap filter->data:
 * media processing and configuration methods can execute on different threads. */
static void notify(void *parent, MSFilter *child, unsigned event, void *argument) {
    (void)child;
    ms_filter_notify(parent, event, argument);
}
static void init(MSFilter *filter) {
    EchoState *wrapper = ms_new0(EchoState, 1);
    wrapper->child = ms_factory_create_filter_from_desc(filter->factory, original);
    ms_filter_add_notify_callback(wrapper->child, notify, filter, TRUE);
    wrapper->rate = 8000; /* Speex's initial rate, before the SDK configures it. */
    filter->data = wrapper;
}
static void invoke(MSFilter *filter, void (*callback)(MSFilter *)) {
    EchoState *wrapper = filter->data;
    MSFilter *child = wrapper->child;
    child->ticker = filter->ticker;
    for (int i = 0; i < 2; ++i) {
        child->inputs[i] = filter->inputs[i];
        child->outputs[i] = filter->outputs[i];
    }
    if (callback) callback(child);
}
static void preprocess(MSFilter *filter) { invoke(filter, original->preprocess); }
static void process(MSFilter *filter) { invoke(filter, original->process); }
static void postprocess(MSFilter *filter) { invoke(filter, original->postprocess); }
static void uninit(MSFilter *filter) {
    EchoState *wrapper = filter->data;
    ms_filter_destroy(wrapper->child);
    ms_free(wrapper);
    filter->data = NULL;
}

static int forward(MSFilter *filter, unsigned method, void *argument) {
    for (MSFilterMethod *entry = original->methods; entry && entry->method; ++entry) {
        if (entry->id != method) continue;
        EchoState *wrapper = filter->data;
        return entry->method(wrapper->child, argument);
    }
    return -1;
}
static int set_rate(MSFilter *filter, void *argument) {
    int rate = *(int *)argument;
    if (rate > maximum_rate) rate = maximum_rate;
    int result = forward(filter, MS_FILTER_SET_SAMPLE_RATE, &rate);
    if (result == 0) ((EchoState *)filter->data)->rate = rate;
    return result;
}
/* Speex has no GET_SAMPLE_RATE method. Report our actual rate so the SDK
 * adapts the whole audio graph instead of feeding 48 kHz samples into 16 kHz DSP. */
static int get_rate(MSFilter *filter, void *argument) {
    *(int *)argument = ((EchoState *)filter->data)->rate;
    return 0;
}
static int delay(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_SET_DELAY, argument); }
static int framesize(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_SET_FRAMESIZE, argument); }
static int tail(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_SET_TAIL_LENGTH, argument); }
static int bypass(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_SET_BYPASS_MODE, argument); }
static int get_bypass(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_GET_BYPASS_MODE, argument); }
static int state(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_SET_STATE_STRING, argument); }
static int get_state(MSFilter *filter, void *argument) { return forward(filter, MS_ECHO_CANCELLER_GET_STATE_STRING, argument); }

static MSFilterMethod methods[] = {
    {MS_FILTER_SET_SAMPLE_RATE, set_rate}, {MS_FILTER_GET_SAMPLE_RATE, get_rate},
    {MS_ECHO_CANCELLER_SET_DELAY, delay}, {MS_ECHO_CANCELLER_SET_FRAMESIZE, framesize},
    {MS_ECHO_CANCELLER_SET_TAIL_LENGTH, tail}, {MS_ECHO_CANCELLER_SET_BYPASS_MODE, bypass},
    {MS_ECHO_CANCELLER_GET_BYPASS_MODE, get_bypass}, {MS_ECHO_CANCELLER_SET_STATE_STRING, state},
    {MS_ECHO_CANCELLER_GET_STATE_STRING, get_state}, {0, NULL}
};
static MSFilterDesc descriptor = {
    .id = MS_FILTER_PLUGIN_ID, .name = "ZmalaSpeechEC", .text = "Speex echo cancellation at speech sample rate",
    .category = MS_FILTER_OTHER, .ninputs = 2, .noutputs = 2, .methods = methods
};

// @llr LLR-TERM-AUDIO-003
int zmala_speech_audio_register(MSFactory *factory, int rate) {
    if (!factory || (rate != 16000 && rate != 48000)) return -1;
    original = ms_factory_lookup_filter_by_name(factory, "MSSpeexEC");
    if (!original) return -1;
    maximum_rate = rate;
    descriptor.init = init;
    descriptor.preprocess = preprocess;
    descriptor.process = process;
    descriptor.postprocess = postprocess;
    descriptor.uninit = uninit;
    ms_factory_register_filter(factory, &descriptor);
    ms_factory_set_echo_canceller_filter_name(factory, descriptor.name);
    return 0;
}
