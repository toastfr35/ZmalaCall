// @test T-LLT-054
// @requirements LLR-TERM-AUDIO-003
// @environment native-sdk
// @plan Register a recording echo-canceller child in a real MediaStreamer factory. Exercise speech/normal sample-rate negotiation, rejected changes, every forwarded control, notifications and all lifecycle callbacks; verify independent child state and shared queue/ticker identity without opening audio hardware.
// @pass Speech capture is capped at 16 kHz and normal capture at 48 kHz, failed changes preserve the last rate, controls/events retain their arguments, and destroying the wrapper releases its child exactly once.

#include "../../../zmala_terminal/linux/media/audio/echo-rate.c"
#include <assert.h>
#include <stdio.h>

static int child_state, calls, destroyed, requested_rate, rate_result, notified;
static MSFilter *expected_child;
static MSFilter *parent_filter;

static void child_init(MSFilter *filter) { filter->data = &child_state; }
static void child_uninit(MSFilter *filter) { assert(filter->data == &child_state); destroyed++; }
static void lifecycle(MSFilter *filter) {
    assert(filter == expected_child && filter->data == &child_state);
    assert(filter->ticker == parent_filter->ticker);
    for (int i = 0; i < 2; i++) {
        assert(filter->inputs[i] == parent_filter->inputs[i]);
        assert(filter->outputs[i] == parent_filter->outputs[i]);
    }
    calls++;
}
static int record_rate(MSFilter *filter, void *argument) {
    assert(filter == expected_child);
    requested_rate = *(int *)argument;
    return rate_result;
}
static int record_control(MSFilter *filter, void *argument) {
    assert(filter == expected_child && argument == &child_state);
    calls++;
    return 42;
}
static void record_notification(void *data, MSFilter *filter, unsigned event, void *argument) {
    assert(data == &child_state && filter == parent_filter);
    assert(event == MS_FILTER_OUTPUT_FMT_CHANGED && argument == &child_state);
    notified++;
}
static MSFilterMethod child_methods[] = {
    {MS_FILTER_SET_SAMPLE_RATE, record_rate},
    {MS_ECHO_CANCELLER_SET_DELAY, record_control},
    {MS_ECHO_CANCELLER_SET_FRAMESIZE, record_control},
    {MS_ECHO_CANCELLER_SET_TAIL_LENGTH, record_control},
    {MS_ECHO_CANCELLER_SET_BYPASS_MODE, record_control},
    {MS_ECHO_CANCELLER_GET_BYPASS_MODE, record_control},
    {MS_ECHO_CANCELLER_SET_STATE_STRING, record_control},
    {MS_ECHO_CANCELLER_GET_STATE_STRING, record_control}, {0, NULL}
};
static MSFilterDesc child_descriptor = {
    .id = MS_FILTER_PLUGIN_ID, .name = "MSSpeexEC", .text = "Recording DSP boundary",
    .category = MS_FILTER_OTHER, .ninputs = 2, .noutputs = 2,
    .init = child_init, .uninit = child_uninit, .preprocess = lifecycle,
    .process = lifecycle, .postprocess = lifecycle, .methods = child_methods
};

int main(void) {
    int result = zmala_speech_audio_register(NULL, 16000);
    assert(result == -1);
    MSFactory *factory = ms_factory_new();
    result = zmala_speech_audio_register(factory, 16000);
    assert(result == -1);
    result = zmala_speech_audio_register(factory, 22050);
    assert(result == -1);
    ms_factory_register_filter(factory, &child_descriptor);
    for (int mode = 0; mode < 2; mode++) {
        int cap = mode ? 48000 : 16000;
        result = zmala_speech_audio_register(factory, cap);
        assert(result == 0);
        parent_filter = ms_factory_create_filter_from_desc(factory, &descriptor);
        EchoState *wrapper = parent_filter->data;
        expected_child = wrapper->child;
        assert(expected_child != parent_filter && expected_child->data == &child_state);
        int rate = 0;
        assert(get_rate(parent_filter, &rate) == 0 && rate == 8000);
        rate_result = 0; rate = 96000;
        assert(set_rate(parent_filter, &rate) == 0 && requested_rate == cap);
        assert(rate == 96000); // Caller-owned request remains unchanged.
        assert(get_rate(parent_filter, &rate) == 0 && rate == cap);
        rate_result = -7; rate = 8000;
        assert(set_rate(parent_filter, &rate) == -7);
        assert(get_rate(parent_filter, &rate) == 0 && rate == cap);
        rate_result = 0; rate = 8000;
        assert(set_rate(parent_filter, &rate) == 0);
        assert(get_rate(parent_filter, &rate) == 0 && rate == 8000);
        calls = 0;
        for (MSFilterMethod *method = methods+2; method->method; ++method)
            assert(ms_filter_call_method(parent_filter, method->id, &child_state) == 42);
        assert(calls == 7);
        assert(forward(parent_filter, 0xffffffffu, NULL) == -1);
        child_descriptor.methods = NULL;
        assert(forward(parent_filter, MS_FILTER_SET_SAMPLE_RATE, &rate) == -1);
        child_descriptor.methods = child_methods;
        MSQueue input[2], output[2];
        for (int i = 0; i < 2; ++i) {
            ms_queue_init(&input[i]); ms_queue_init(&output[i]);
            parent_filter->inputs[i] = &input[i]; parent_filter->outputs[i] = &output[i];
        }
        preprocess(parent_filter); process(parent_filter); postprocess(parent_filter);
        assert(calls == 10);
        invoke(parent_filter, NULL); assert(calls == 10);
        ms_filter_add_notify_callback(parent_filter, record_notification, &child_state, TRUE);
        notify(parent_filter, expected_child, MS_FILTER_OUTPUT_FMT_CHANGED, &child_state);
        assert(notified == mode+1);
        ms_filter_destroy(parent_filter);
        assert(destroyed == mode+1);
    }
    ms_factory_destroy(factory);
    puts("Echo-rate wrapper: negotiation, controls, events, lifecycle and cleanup PASS");
    return 0;
}
