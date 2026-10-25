// @llr LLR-TERM-VIDEO-018
/* Strict C20 MJPEG capture. Some drivers clamp an unsupported raw HD request to
 * VGA while returning success; checking dimensions prevents silent fallback.
 * Camera I/O runs off the MediaStreamer ticker, with one latest-frame slot. */
#include "mjpeg-stream.h"
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <bctoolbox/port.h>

static int prepare_capture(MjpegCamera *c);
static void release_capture(MjpegCamera *c);

// @llr LLR-TERM-VIDEO-019
static int microphone_running(void) {
    FILE *status = fopen("/proc/asound/C20/pcm0c/sub0/status", "r");
    if (!status) return 0;
    char line[128], state[32];
    int running = 0;
    while (fgets(line, sizeof(line), status)) {
        if (sscanf(line, "state: %31s", state) == 1) {
            running = strcmp(state, "RUNNING") == 0;
            break;
        }
    }
    fclose(status);
    return running;
}

// @llr LLR-TERM-VIDEO-019
static int wait_for_microphone(MjpegCamera *c) {
    uint64_t deadline = bctbx_get_cur_time_ms() + 5000, stable = 0;
    while (!atomic_load(&c->stopping)) {
        uint64_t now = bctbx_get_cur_time_ms();
        if (now >= deadline) {
            ms_error("C20 camera startup: microphone did not become ready");
            return 0;
        }
        if (microphone_running()) {
            if (!stable) stable = now;
            if (now - stable >= 750) return 1;
        } else stable = 0;
        usleep(20000);
    }
    return 0;
}

static int control(int fd, unsigned long request, void *value) {
    int result;
    do { result = ioctl(fd, request, value); } while (result < 0 && errno == EINTR);
    return result;
}

// @llr LLR-TERM-VIDEO-004, LLR-TERM-VIDEO-018
int zmala_mjpeg_configure(MjpegCamera *c) {
    if (c->fd >= 0) return 0;
    c->fd = open(c->device, O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (c->fd < 0) {
        ms_error("Zmala MJPEG open %s failed: %s", c->device, strerror(errno));
        return -1;
    }
    struct v4l2_format format = {0};
    format.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    format.fmt.pix.width = c->size.width;
    format.fmt.pix.height = c->size.height;
    format.fmt.pix.pixelformat = V4L2_PIX_FMT_MJPEG;
    format.fmt.pix.field = V4L2_FIELD_ANY;
    int result = control(c->fd, VIDIOC_S_FMT, &format);
    if (result < 0) {
        ms_error("Zmala MJPEG format %s %dx%d failed: %s", c->device,
                 c->size.width, c->size.height, strerror(errno));
    } else if (format.fmt.pix.pixelformat != V4L2_PIX_FMT_MJPEG ||
               (int)format.fmt.pix.width != c->size.width || (int)format.fmt.pix.height != c->size.height) {
        ms_error("Zmala MJPEG format %s requested %dx%d, received %ux%u format=%08x",
                 c->device, c->size.width, c->size.height,
                 format.fmt.pix.width, format.fmt.pix.height, format.fmt.pix.pixelformat);
    }
    if (result < 0 || format.fmt.pix.pixelformat != V4L2_PIX_FMT_MJPEG ||
        (int)format.fmt.pix.width != c->size.width || (int)format.fmt.pix.height != c->size.height) {
        close(c->fd); c->fd = -1;
        return -1;
    }
    ms_message("Zmala MJPEG configured %s: %dx%d", c->device, c->size.width, c->size.height);
    return 0;
}

// @llr LLR-TERM-VIDEO-018, LLR-TERM-VIDEO-019
static void *capture(void *data) {
    MjpegCamera *c = data;
    if (!wait_for_microphone(c) || prepare_capture(c)) {
        release_capture(c);
        return NULL;
    }
    MSFrameRateController copy_rate;
    ms_video_init_framerate_controller(&copy_rate, c->fps);
    while (!atomic_load(&c->stopping)) {
        struct pollfd ready = {c->fd, POLLIN, 0};
        if (poll(&ready, 1, 100) <= 0) continue;
        struct v4l2_buffer buffer = {0};
        buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buffer.memory = V4L2_MEMORY_MMAP;
        if (control(c->fd, VIDIOC_DQBUF, &buffer) < 0) {
            if (errno != EAGAIN) break;
            continue;
        }
        if (buffer.index >= c->count) break;
        atomic_fetch_add(&c->received, 1);
        int valid = buffer.bytesused > 30 && buffer.bytesused <= c->buffers[buffer.index].length &&
                    !(buffer.flags & V4L2_BUF_FLAG_ERROR);
        /* Drain/requeue every USB buffer, but only copy the requested rate.
         * The C20 runs at 30 camera fps; unused JPEGs need no heap allocation.
         * Use the SDK rate controller so camera jitter does not accumulate drift. */
        if (valid && ms_video_capture_new_frame(&copy_rate, bctbx_get_cur_time_ms())) {
            mblk_t *bytes = allocb(buffer.bytesused, 0);
            memcpy(bytes->b_wptr, c->buffers[buffer.index].address, buffer.bytesused);
            bytes->b_wptr += buffer.bytesused;
            /* SDK MJPEG decoders expect the same picture metadata as V4L2. */
            mblk_t *frame = ms_yuv_buf_alloc_from_buffer(c->size.width, c->size.height, bytes);
            pthread_mutex_lock(&c->mutex);
            if (c->latest) freemsg(c->latest);
            c->latest = frame;
            pthread_mutex_unlock(&c->mutex);
            atomic_fetch_add(&c->copied, 1);
        } else if (!valid) atomic_fetch_add(&c->rejected, 1);
        if (control(c->fd, VIDIOC_QBUF, &buffer) < 0) break;
    }
    return NULL;
}

// @llr LLR-TERM-VIDEO-018
static int prepare_capture(MjpegCamera *c) {
    if (zmala_mjpeg_configure(c)) return -1;
    struct v4l2_requestbuffers request = {0};
    request.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    request.memory = V4L2_MEMORY_MMAP;
    request.count = 4;
    if (control(c->fd, VIDIOC_REQBUFS, &request) < 0 || request.count < 2) goto failed;
    c->count = request.count < 4 ? request.count : 4;
    for (unsigned i = 0; i < c->count; ++i) {
        struct v4l2_buffer buffer = {0};
        buffer.type = request.type;
        buffer.memory = request.memory;
        buffer.index = i;
        if (control(c->fd, VIDIOC_QUERYBUF, &buffer) < 0 || buffer.length > 16*1024*1024) goto failed;
        void *address = mmap(NULL, buffer.length, PROT_READ | PROT_WRITE, MAP_SHARED, c->fd, buffer.m.offset);
        if (address == MAP_FAILED) goto failed;
        c->buffers[i] = (MjpegBuffer){address, buffer.length};
        if (control(c->fd, VIDIOC_QBUF, &buffer) < 0) goto failed;
    }
    enum v4l2_buf_type type = request.type;
    if (control(c->fd, VIDIOC_STREAMON, &type) < 0) goto failed;
    c->streaming = 1;
    ms_message("Zmala MJPEG capture: %s %dx%d at %.0f fps", c->device, c->size.width, c->size.height, c->fps);
    return 0;
failed:
    release_capture(c);
    return -1;
}

// @llr LLR-TERM-VIDEO-019
int zmala_mjpeg_start(MjpegCamera *c) {
    if (c->started) return 0;
    atomic_store(&c->stopping, false);
    if (pthread_create(&c->thread, NULL, capture, c)) {
        atomic_store(&c->stopping, true);
        release_capture(c);
        return -1;
    }
    c->started = 1;
    return 0;
}

// @llr LLR-TERM-VIDEO-018
static void release_capture(MjpegCamera *c) {
    if (c->streaming) {
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        control(c->fd, VIDIOC_STREAMOFF, &type);
        c->streaming = 0;
    }
    for (unsigned i = 0; i < c->count; ++i) {
        if (c->buffers[i].length) munmap(c->buffers[i].address, c->buffers[i].length);
        c->buffers[i] = (MjpegBuffer){0};
    }
    c->count = 0;
    if (c->fd >= 0) { close(c->fd); c->fd = -1; }
}

// @llr LLR-TERM-VIDEO-018
void zmala_mjpeg_stop(MjpegCamera *c) {
    /* Stop/join before unmapping: the worker may still be copying a USB frame. */
    atomic_store(&c->stopping, true);
    if (c->started) {
        pthread_join(c->thread, NULL); c->started = 0;
        ms_message("Zmala MJPEG stopped: received=%u copied=%u rejected=%u",
                   atomic_load(&c->received), atomic_load(&c->copied), atomic_load(&c->rejected));
    }
    release_capture(c);
    if (c->latest) { freemsg(c->latest); c->latest = NULL; }
}
