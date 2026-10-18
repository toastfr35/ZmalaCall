// @test T-LLT-073
// @requirements LLR-TERM-VIDEO-004, LLR-TERM-VIDEO-018
// @environment native-sdk
// @plan Replace V4L2 open/ioctl/mmap/poll and thread creation/join boundaries, retaining the real capture loop, frame-rate controller, buffers and cleanup. Inject each startup failure, driver format clamping, EINTR/EAGAIN, invalid buffers and queue errors. Verify requested dimensions never silently change, only valid frames replace the latest slot, and join precedes unmap/close on stop.
// @pass Every buffer ownership, counter, format and cleanup assertion passes without opening any real device. Hardware USB reliability remains a separate system test.
#include "../../../zmala_terminal/linux/media/video/mjpeg-stream.h"
#include <mediastreamer2/msfactory.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <bctoolbox/port.h>

static unsigned long failure;
static int open_error, clamp, short_count, huge_buffer, map_error, thread_error;
static int opened, closed, mapped, unmapped, joined, streaming, dq, polls, interrupted, q_error, dq_error;
static uint64_t clock_ms;
static void *(*entry)(void *);
static void *argument;
static int fake_open(const char *name, int flags) {
    assert(strcmp(name,"/fixture/C20") == 0 && (flags & O_NONBLOCK));
    if (open_error) { errno=ENODEV; return -1; } ++opened; return 91;
}
static int fake_close(int fd) { assert(fd == 91); ++closed; return 0; }
static int fake_ioctl(int fd, unsigned long request, void *value) {
    assert(fd == 91);
    if (request == failure) { errno=EIO; return -1; }
    if (request == VIDIOC_S_FMT) {
        struct v4l2_format *format=value; assert(format->fmt.pix.width == 1920 && format->fmt.pix.height == 1080);
        if (clamp == 1) format->fmt.pix.width=320;
        if (clamp == 2) format->fmt.pix.pixelformat=V4L2_PIX_FMT_YUYV;
    } else if (request == VIDIOC_REQBUFS) {
        struct v4l2_requestbuffers *buffers=value; buffers->count=short_count ? 1 : 6;
    } else if (request == VIDIOC_QUERYBUF) {
        struct v4l2_buffer *buffer=value; buffer->length=huge_buffer ? 17*1024*1024 : 128; buffer->m.offset=buffer->index*4096;
    } else if (request == VIDIOC_STREAMON) streaming=1;
    else if (request == VIDIOC_STREAMOFF) streaming=0;
    else if (request == VIDIOC_DQBUF) {
        if (!interrupted++) { errno=EINTR; return -1; }
        if (!dq++) { errno=EAGAIN; return -1; }
        if (dq_error) { errno=EIO; return -1; }
        struct v4l2_buffer *buffer=value; buffer->index=0; buffer->bytesused=64;
        if (dq == 4) buffer->bytesused=0;
        if (dq == 5) buffer->bytesused=129;
        if (dq == 6) buffer->flags=V4L2_BUF_FLAG_ERROR;
        if (dq >= 7) buffer->index=99;
    } else if (request == VIDIOC_QBUF && q_error && streaming) { errno=EIO; return -1; }
    return 0;
}
static void *fake_mmap(void *address, size_t length, int protection, int flags, int fd, off_t offset) {
    (void)address; (void)protection; (void)flags; (void)offset; assert(fd == 91);
    if (map_error) return MAP_FAILED;
    ++mapped; void *data=malloc(length); assert(data); memset(data,0x66,length); return data;
}
static int fake_munmap(void *address, size_t length) {
    assert(length == 128); assert(!entry || joined); ++unmapped; free(address); return 0;
}
static int fake_poll(struct pollfd *fds, nfds_t count, int timeout) {
    assert(count == 1 && fds[0].fd == 91 && timeout == 100);
    clock_ms+=1000; return polls++ ? 1 : 0;
}
static uint64_t fake_time(void) { return clock_ms; }
static int fake_create(pthread_t *thread, const pthread_attr_t *attr, void *(*worker)(void *), void *data) {
    (void)attr; if (thread_error) return EAGAIN; *thread=pthread_self(); entry=worker; argument=data; return 0;
}
static int fake_join(pthread_t thread, void **result) { (void)thread; (void)result; joined=1; return 0; }
#define open fake_open
#define close fake_close
#define ioctl fake_ioctl
#define mmap fake_mmap
#define munmap fake_munmap
#define poll fake_poll
#define pthread_create fake_create
#define pthread_join fake_join
#define bctbx_get_cur_time_ms fake_time
#include "../../../zmala_terminal/linux/media/video/mjpeg-stream.c"

static void reset(MjpegCamera *c) {
    memset(c,0,sizeof(*c)); c->fd=-1; c->device="/fixture/C20"; c->size=(MSVideoSize){1920,1080}; c->fps=20;
    pthread_mutex_init(&c->mutex,NULL); atomic_init(&c->stopping,true); atomic_init(&c->received,0); atomic_init(&c->copied,0); atomic_init(&c->rejected,0);
    failure=0; open_error=clamp=short_count=huge_buffer=map_error=thread_error=0;
    opened=closed=mapped=unmapped=joined=streaming=dq=polls=interrupted=q_error=dq_error=0; clock_ms=1; entry=NULL; argument=NULL;
}
static void cleanup(MjpegCamera *c) {
    zmala_mjpeg_stop(c); zmala_mjpeg_stop(c);
    assert(opened == closed && mapped == unmapped && c->fd == -1 && c->count == 0 && c->latest == NULL);
    pthread_mutex_destroy(&c->mutex);
}
int main(void) {
    MSFactory *factory=ms_factory_new_with_voip(); MjpegCamera c;
    const unsigned long requests[]={VIDIOC_S_FMT,VIDIOC_REQBUFS,VIDIOC_QUERYBUF,VIDIOC_QBUF,VIDIOC_STREAMON};
    for (size_t i=0;i<sizeof(requests)/sizeof(requests[0]);++i) {
        reset(&c); failure=requests[i]; int result=zmala_mjpeg_start(&c); assert(result == -1); cleanup(&c);
    }
    for (int which=0;which<7;++which) {
        reset(&c);
        if (which == 0) open_error=1; else if (which == 1) clamp=1; else if (which == 2) clamp=2;
        else if (which == 3) short_count=1; else if (which == 4) huge_buffer=1; else if (which == 5) map_error=1; else thread_error=1;
        int result=zmala_mjpeg_start(&c); assert(result == -1 && c.size.width == 1920 && c.size.height == 1080); cleanup(&c);
    }
    for (int mode=0;mode<3;++mode) {
        reset(&c); int result=zmala_mjpeg_start(&c); assert(result == 0 && c.started && c.count == 4);
        result=zmala_mjpeg_configure(&c); assert(result == 0 && opened == 1);
        if (mode == 1) q_error=1;
        if (mode == 2) dq_error=1;
        entry(argument);
        assert(atomic_load(&c.received) == (mode == 0 ? 5u : mode == 1 ? 1u : 0u));
        assert(atomic_load(&c.copied) == (mode == 0 ? 2u : mode == 1 ? 1u : 0u));
        assert(atomic_load(&c.rejected) == (mode == 0 ? 3u : 0u));
        if (mode != 2) { assert(c.latest && c.latest->b_cont); assert(c.latest->b_cont->b_wptr-c.latest->b_cont->b_rptr == 64); }
        cleanup(&c); assert(joined);
    }
    ms_factory_destroy(factory); puts("V4L2 capture format, buffer failure and cleanup checks: PASS"); return 0;
}
