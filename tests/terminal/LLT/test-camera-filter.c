// @test T-LLT-075
// @requirements LLR-TERM-VIDEO-004, LLR-TERM-VIDEO-018, LLR-TERM-VIDEO-019
// @environment native-sdk
// @plan Exercise both C10 and C20 identities. Run the real camera filter against mocked device enumeration and capture lifecycle boundaries. Mix inaccessible, other-model, raw-only and C20 MJPEG nodes; assert only the eligible node is registered. Verify reader ownership, requested size/rate validation, size negotiation without device access, newest-frame transfer and RTP timestamps, empty-tick FPS stability and stopped capture cleanup without physical camera access.
// @pass Every catalog, configuration, buffer and metadata assertion passes using real MediaStreamer buffers/filter objects; driver capture is checked separately by the capture-boundary LLT.
#include "../../../zmala_terminal/linux/media/video/mjpeg-stream.h"
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <mediastreamer2/mswebcam.h>
#include <assert.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/videodev2.h>
#include <math.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static MSFactory *factory;
static const char *camera_name = "Nuroum C20";
static MSWebCam *found[8];
static int found_count, opens, closes, freed_glob, glob_error, start_error, starts, stops;
static char *paths[]={"/dev/video0","/dev/video1","/dev/video2","/dev/video3","/dev/video4"};
static int fake_glob(const char *pattern,int flags,int (*error)(const char *,int),glob_t *result) {
    (void)flags; (void)error; assert(strcmp(pattern,"/dev/video*") == 0);
    result->gl_pathc=5; result->gl_pathv=paths; return glob_error;
}
static void fake_globfree(glob_t *result) { (void)result; ++freed_glob; }
static int fake_open(const char *path,int flags) { ++opens; assert(flags & O_NONBLOCK); int index=path[strlen(path)-1]-'0'; return index ? 100+index : -1; }
static int fake_close(int fd) { assert(fd>=101 && fd<=104); ++closes; return 0; }
static int fake_ioctl(int fd,unsigned long request,void *value) {
    if (request == VIDIOC_QUERYCAP) {
        if (fd == 104) return -1;
        struct v4l2_capability *capability=value;
        strcpy((char *)capability->card,fd == 101 ? "Other camera" : camera_name); return 0;
    }
    assert(request == VIDIOC_ENUM_FMT); struct v4l2_fmtdesc *format=value;
    if (format->index == 0) { format->pixelformat=V4L2_PIX_FMT_YUYV; return 0; }
    if (fd == 103 && format->index == 1) { format->pixelformat=V4L2_PIX_FMT_MJPEG; return 0; }
    return -1;
}
static void fake_prepend(MSWebCamManager *manager,MSWebCam *cam) { (void)manager; assert(found_count<8); found[found_count++]=cam; }
static MSFactory *fake_factory(MSWebCam *cam) { (void)cam; return factory; }
static MSWebCamManager *fake_manager(MSFactory *f) { assert(f == factory); return (MSWebCamManager *)&found_count; }
static void fake_register(MSWebCamManager *manager,MSWebCamDesc *desc) { desc->detect(manager); }
static int fake_start(MjpegCamera *c) { ++starts; if (start_error) return -1; c->started=1; return 0; }
static void fake_stop(MjpegCamera *c) { ++stops; c->started=0; }
#define glob fake_glob
#define globfree fake_globfree
#define open fake_open
#define close fake_close
#define ioctl fake_ioctl
#define ms_web_cam_manager_prepend_cam fake_prepend
#define ms_web_cam_get_factory fake_factory
#define ms_factory_get_web_cam_manager fake_manager
#define ms_web_cam_manager_register_desc fake_register
#define zmala_mjpeg_start fake_start
#define zmala_mjpeg_stop fake_stop
#include "../../../zmala_terminal/linux/media/video/mjpeg-filter.c"

int main(void) {
    factory=ms_factory_new_with_voip();
    int result=zmala_mjpeg_register(NULL); assert(result == -1);
    glob_error=GLOB_NOMATCH; detect(NULL); assert(freed_glob == 1 && found_count == 0);
    glob_error=0; result=zmala_mjpeg_register(factory); assert(result == 0 && found_count == 1 && closes == 4);
    assert(strcmp(found[0]->name,"/dev/video3") == 0);
    MSFilter *f=create_reader(found[0]); assert(f); MjpegCamera *c=f->data;
    assert(c->device != found[0]->name && strcmp(c->device,found[0]->name) == 0);
    MSVideoSize wanted={1920,1080},actual;
    result=set_size(f,&wanted); assert(result == 0); result=get_size(f,&actual); assert(result == 0 && actual.width == 1920 && actual.height == 1080);
    assert(opens == 5 && closes == 4 && starts == 0);
    wanted.width=8; result=set_size(f,&wanted); assert(result == -1 && c->size.width == 1920);
    wanted.width=1921; result=set_size(f,&wanted); assert(result == -1);
    for (int i=0;i<4;++i) { float fps=i == 0 ? NAN : i == 1 ? 0 : i == 2 ? 31 : 20; result=set_fps(f,&fps); assert(result == (i == 3 ? 0 : -1)); }
    float fps=0; result=get_fps(f,&fps); assert(result == 0 && fps == 20);
    MSPixFmt format; result=get_format(f,&format); assert(result == 0 && format == MS_MJPEG);
    result=ignore(f,NULL); assert(result == 0);
    start_error=1; start(f); assert(starts == 1 && !c->started);
    start_error=0; start(f); assert(starts == 2 && c->started);
    wanted=(MSVideoSize){640,480}; result=set_size(f,&wanted); assert(result == -1); stop(f); assert(!c->started);
    MSQueue output; ms_queue_init(&output); f->outputs[0]=&output; MSTicker ticker={0}; ticker.time=100; f->ticker=&ticker;
    c->latest=allocb(1,0); *c->latest->b_wptr++=0x55; process(f); assert(c->latest == NULL);
    mblk_t *frame=ms_queue_get(&output); assert(frame && frame->b_rptr[0] == 0x55 && mblk_get_timestamp_info(frame) == 9000 && mblk_get_marker_info(frame)); freemsg(frame);
    uint64_t last=c->average.last_frame_time; ticker.time=900; process(f); assert(ms_queue_empty(&output) && c->average.last_frame_time == last);
    f->outputs[0]=NULL; f->ticker=NULL; ms_filter_destroy(f); assert(stops>=3);
    ms_web_cam_destroy(found[0]); found_count=0;
    camera_name="Nuroum C10"; detect(NULL); assert(found_count == 1);
    ms_web_cam_destroy(found[0]); ms_factory_destroy(factory);
    puts("C10/C20 catalog, adapter configuration and frame delivery checks: PASS"); return 0;
}
