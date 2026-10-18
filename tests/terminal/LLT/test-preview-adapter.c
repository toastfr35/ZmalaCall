// @test T-LLT-076
// @requirements LLR-TERM-VIDEO-010, LLR-TERM-VIDEO-011
// @environment native-sdk
// @plan Substitute only the child OpenGL display and SDK lifecycle/event boundaries while running the actual preview adapter. Verify method IDs/arguments, window dimensions, event forwarding, latest-frame reduction and timestamp retention, dirty/idle scheduling and detached-input cleanup. Exercise missing-display fallback without opening X11 or a GPU context.
// @pass Adapter lifecycle and frame assertions pass using real YUV buffers; physical compositing and tearing remain display-system checks.
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msogl_functions.h>
#include <mediastreamer2/msogl.h>
#include <mediastreamer2/msvideo.h>
#include <mediastreamer2/msticker.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

static MSFilter child;
static MSQueue *child_inputs[2];
static int missing,preprocessed,postprocessed,destroyed,draw_count,call_result;
static unsigned called_method,notified;
static void *called_argument,*notify_argument,*notify_context;
static MSVideoSize received_size;
static uint32_t received_time;
static MSFilterNotifyFunc child_notify;
static MSFilter *fake_create(MSFactory *factory,const char *name) { (void)factory; assert(strcmp(name,"MSOGL") == 0); return missing ? NULL : &child; }
static void fake_add_notify(MSFilter *f,MSFilterNotifyFunc fn,void *context,bool_t synchronous) { assert(f == &child && synchronous); child_notify=fn; notify_context=context; }
static void fake_notify(MSFilter *f,unsigned event,void *value) { assert(f == notify_context); notified=event; notify_argument=value; }
static void fake_preprocess(MSFilter *f,MSTicker *ticker) { assert(f == &child && ticker); ++preprocessed; }
static void fake_postprocess(MSFilter *f) { assert(f == &child); ++postprocessed; }
static int fake_method(MSFilter *f,unsigned method,void *value) { assert(f == &child); called_method=method; called_argument=value; return call_result; }
static void fake_destroy(MSFilter *f) { assert(f == &child && !f->inputs[0] && !f->inputs[1]); ++destroyed; }
static MSFilterDesc *fake_lookup(MSFactory *factory,const char *name) { (void)factory; (void)name; return missing ? NULL : child.desc; }
static void fake_register(MSFactory *factory,MSFilterDesc *desc) { assert(factory && strcmp(desc->name,"ZmalaPreviewOGL") == 0); }
static void draw_child(MSFilter *f) {
    ++draw_count; mblk_t *frame;
    while ((frame=ms_queue_get(f->inputs[0]))) {
        MSPicture picture; int result=ms_yuv_buf_init_from_mblk(&picture,frame); assert(result == 0);
        received_size=(MSVideoSize){picture.w,picture.h}; received_time=mblk_get_timestamp_info(frame); freemsg(frame);
    }
}
#define ms_factory_create_filter_from_name fake_create
#define ms_filter_add_notify_callback fake_add_notify
#define ms_filter_notify fake_notify
#define ms_filter_preprocess fake_preprocess
#define ms_filter_postprocess fake_postprocess
#define ms_filter_call_method fake_method
#define ms_filter_destroy fake_destroy
#define ms_factory_lookup_filter_by_name fake_lookup
#define ms_factory_register_filter fake_register
#include "../../../zmala_terminal/linux/media/video/preview-display.c"

int main(void) {
    MSFilterDesc child_desc={.process=draw_child}; child.desc=&child_desc; child.inputs=child_inputs;
    MSQueue in,unused; ms_queue_init(&in); ms_queue_init(&unused); MSQueue *inputs[]={&in,&unused}; MSTicker ticker={0};
    MSFilter f={0}; f.inputs=inputs; f.ticker=&ticker;
    // The factory token is never dereferenced by the mocked child boundary.
    f.factory=(MSFactory *)&f;
    int result=zmala_preview_register(NULL); assert(result == -1);
    result=zmala_preview_register(f.factory); assert(result == 0);
    initialize(&f); PreviewDisplay *s=f.data; assert(s->display == &child && child.inputs[0] == &s->frame);
    start(&f); assert(preprocessed == 1 && s->dirty);
    int payload=123; child_notify(notify_context,&child,456,&payload); assert(notified == 456 && notify_argument == &payload);
    MSOglContextInfo context={0}; context.width=120; context.height=67; const MSOglContextInfo *pointer=&context;
    result=set_window(&f,&pointer); assert(result == 0 && s->width == 120 && s->height == 67);
    assert(called_method == MS_VIDEO_DISPLAY_SET_NATIVE_WINDOW_ID && called_argument == &pointer);
    int (*functions[])(MSFilter *,void *)={set_size,get_window,show,zoom,mirror,mode,render,egl_context};
    const unsigned methods_expected[]={MS_FILTER_SET_VIDEO_SIZE,MS_VIDEO_DISPLAY_GET_NATIVE_WINDOW_ID,MS_VIDEO_DISPLAY_SHOW_VIDEO,MS_VIDEO_DISPLAY_ZOOM,MS_VIDEO_DISPLAY_ENABLE_MIRRORING,MS_VIDEO_DISPLAY_SET_MODE,MS_OGL_RENDER,MS_OGL_DISPLAY_SET_EGL_TARGET_CONTEXT};
    call_result=7;
    for (unsigned i=0;i<sizeof(functions)/sizeof(functions[0]);++i) { s->dirty=0; result=functions[i](&f,&payload); assert(result == 7 && s->dirty && called_method == methods_expected[i] && called_argument == &payload); }
    MSPicture picture; mblk_t *frame=ms_yuv_buf_allocator_get(s->allocator,&picture,960,540);
    for (int plane=0;plane<3;++plane) memset(picture.planes[plane],80,(size_t)picture.strides[plane]*(plane ? 270 : 540));
    mblk_set_timestamp_info(frame,987); ms_queue_put(&in,frame); ms_queue_put(&unused,allocb(1,0)); ticker.time=100; process(&f);
    assert(received_size.width == 480 && received_size.height == 270 && received_time == 987); assert(ms_queue_empty(&unused) && ms_queue_empty(&in));
    int before=draw_count; ticker.time=110; process(&f); assert(draw_count == before);
    pointer=NULL; result=set_window(&f,&pointer); assert(result == 7 && s->width == 0 && s->height == 0);
    frame=ms_yuv_buf_allocator_get(s->allocator,&picture,32,16); ms_queue_put(&in,frame); process(&f); assert(received_size.width == 32 && received_size.height == 16);
    stop(&f); destroy(&f); assert(postprocessed == 1 && destroyed == 1);
    missing=1; result=zmala_preview_register(f.factory); assert(result == -1); initialize(&f); start(&f);
    result=show(&f,&payload); assert(result == -1); stop(&f); destroy(&f); assert(destroyed == 1);
    puts("Preview child method, frame, window and lifecycle checks: PASS"); return 0;
}
