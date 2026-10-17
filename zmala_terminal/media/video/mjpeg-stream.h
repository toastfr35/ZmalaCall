/* C20 V4L2 ownership is separate from the SDK filter: the camera thread only
 * publishes the newest compressed frame, keeping backlog and memory bounded. */
#ifndef ZMALA_MJPEG_STREAM_H
#define ZMALA_MJPEG_STREAM_H
#include <stdatomic.h>
#include <pthread.h>
#include <mediastreamer2/msfilter.h>
#include <mediastreamer2/msvideo.h>

typedef struct {
    void *address;
    size_t length;
} MjpegBuffer;

typedef struct {
    char *device;
    int fd, started, streaming;
    MSVideoSize size;
    float fps;
    MjpegBuffer buffers[4];
    unsigned count;
    pthread_t thread;
    pthread_mutex_t mutex;
    atomic_bool stopping;
    atomic_uint received, rejected, copied;
    mblk_t *latest;
    MSAverageFPS average;
} MjpegCamera;

int zmala_mjpeg_configure(MjpegCamera *camera);
int zmala_mjpeg_start(MjpegCamera *camera);
void zmala_mjpeg_stop(MjpegCamera *camera);
#endif
