// @llr LLR-TERM-VIDEO-018
/* C20 camera entry using public SDK interfaces. This source acquires strict-size
 * MJPEG frames; separate decoder/framing adapters and the SDK own downstream
 * scaling, preview and H.264 encoding. */
#include "mjpeg-stream.h"
#include <fcntl.h>
#include <glob.h>
#include <linux/videodev2.h>
#include <math.h>
#include <stdbool.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <mediastreamer2/msfactory.h>
#include <mediastreamer2/msinterfaces.h>
#include <mediastreamer2/msticker.h>
#include <mediastreamer2/mswebcam.h>

static void initialize(MSFilter *f) {
    MjpegCamera *c = ms_new0(MjpegCamera, 1);
    c->fd = -1;
    c->size = (MSVideoSize){640, 360};
    c->fps = 15;
    pthread_mutex_init(&c->mutex, NULL);
    atomic_init(&c->stopping, true);
    atomic_init(&c->received, 0);
    atomic_init(&c->rejected, 0);
    atomic_init(&c->copied, 0);
    ms_average_fps_init(&c->average, "Zmala MJPEG fps=%f");
    f->data = c;
}
static void start(MSFilter *f) {
    MjpegCamera *c = f->data;
    if (zmala_mjpeg_start(c)) ms_error("Zmala MJPEG capture failed: %s", c->device);
}
static void process(MSFilter *f) {
    MjpegCamera *c = f->data;
    /* Capture already paces JPEG copies. A second rate gate here can discard
     * good frames when the independent USB/ticker clocks drift in phase. */
    pthread_mutex_lock(&c->mutex);
    mblk_t *frame = c->latest;
    c->latest = NULL;
    pthread_mutex_unlock(&c->mutex);
    /* The SDK estimator averages intervals on every invocation, including
     * empty ticks. Sampling only real frames avoids reporting ticker speed
     * as camera speed and repeatedly reopening the H.264 encoder. */
    if (frame) ms_average_fps_activity(&c->average, f->ticker->time, TRUE);
    if (frame) {
        mblk_set_timestamp_info(frame, (uint32_t)(f->ticker->time * 90));
        mblk_set_marker_info(frame, TRUE);
        ms_queue_put(f->outputs[0], frame);
    }
}
static void stop(MSFilter *f) { zmala_mjpeg_stop(f->data); }
static void destroy(MSFilter *f) {
    MjpegCamera *c = f->data;
    zmala_mjpeg_stop(c);
    pthread_mutex_destroy(&c->mutex);
    ms_free(c->device);
    ms_free(c);
}
static int set_size(MSFilter *f, void *arg) {
    MjpegCamera *c = f->data;
    MSVideoSize size = *(MSVideoSize *)arg;
    if (c->started || size.width < 16 || size.height < 16 || size.width > 1920 || size.height > 1080) return -1;
    zmala_mjpeg_stop(c);
    c->size = size;
    return 0;
}
// @llr LLR-TERM-VIDEO-019
static int get_size(MSFilter *f, void *arg) {
    MjpegCamera *c = f->data;
    /* Size negotiation must not open the USB camera before audio startup.
     * The capture worker validates the requested hardware format later. */
    *(MSVideoSize *)arg = c->size;
    return 0;
}
static int set_fps(MSFilter *f, void *arg) {
    MjpegCamera *c = f->data;
    float fps = *(float *)arg;
    if (!isfinite(fps) || fps < 1 || fps > 30) return -1;
    c->fps = fps;
    return 0;
}
static int get_fps(MSFilter *f, void *arg) {
    MjpegCamera *c = f->data;
    /* Capture reports its configured rate, including before its first frame.
     * The video quality controller measures actual delivery separately. */
    *(float *)arg = c->fps;
    return 0;
}
static int get_format(MSFilter *f, void *arg) { (void)f; *(MSPixFmt *)arg = MS_MJPEG; return 0; }
static int ignore(MSFilter *f, void *arg) { (void)f; (void)arg; return 0; }
static MSFilterMethod methods[] = {
    {MS_FILTER_SET_VIDEO_SIZE, set_size}, {MS_FILTER_GET_VIDEO_SIZE, get_size},
    {MS_FILTER_SET_FPS, set_fps}, {MS_FILTER_GET_FPS, get_fps}, {MS_FILTER_GET_PIX_FMT, get_format},
    {MS_VIDEO_CAPTURE_SET_DEVICE_ORIENTATION, ignore}, {0, NULL}
};
static MSFilterDesc filter = {MS_FILTER_PLUGIN_ID, "ZmalaMJPEGSource", "Strict V4L2 MJPEG capture",
    MS_FILTER_OTHER, NULL, 0, 1, initialize, start, process, stop, destroy, methods, 0};
static MSFilter *create_reader(MSWebCam *cam) {
    MSFilter *f = ms_factory_create_filter_from_desc(ms_web_cam_get_factory(cam), &filter);
    if (f) ((MjpegCamera *)f->data)->device = ms_strdup(cam->name);
    return f;
}
static void detect(MSWebCamManager *manager);
static MSWebCamDesc webcam = {"ZmalaMJPEG", detect, NULL, create_reader, NULL, NULL};

static void detect(MSWebCamManager *manager) {
    glob_t paths = {0};
    if (glob("/dev/video*", 0, NULL, &paths)) { globfree(&paths); return; }
    for (size_t i = 0; i < paths.gl_pathc; ++i) {
        int fd = open(paths.gl_pathv[i], O_RDWR | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) continue;
        struct v4l2_capability capability = {0};
        /* Metadata nodes and other cameras must not masquerade as the C20.
         * Names come from the kernel's USB device, rather than /dev ordering. */
        if (ioctl(fd, VIDIOC_QUERYCAP, &capability) < 0 ||
            (!strstr((const char *)capability.card, "Nuroum C20") &&
             !strstr((const char *)capability.card, "Nuroum C10"))) { close(fd); continue; }
        struct v4l2_fmtdesc format = {0};
        format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        while (ioctl(fd, VIDIOC_ENUM_FMT, &format) == 0) {
            if (format.pixelformat == V4L2_PIX_FMT_MJPEG) {
                MSWebCam *cam = ms_web_cam_new(&webcam);
                cam->name = ms_strdup(paths.gl_pathv[i]);
                ms_web_cam_manager_prepend_cam(manager, cam);
                break;
            }
            ++format.index;
        }
        close(fd);
    }
    globfree(&paths);
}

int zmala_mjpeg_register(MSFactory *factory) {
    if (!factory) return -1;
    ms_factory_register_filter(factory, &filter);
    /* Register detection as well as current devices, so SDK catalog refreshes
     * and later USB reconnects retain this camera choice. */
    ms_web_cam_manager_register_desc(ms_factory_get_web_cam_manager(factory), &webcam);
    return 0;
}
