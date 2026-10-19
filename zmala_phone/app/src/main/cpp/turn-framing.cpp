// SPDX-License-Identifier: AGPL-3.0-or-later
// @llr LLR-AND-CALL-006
#include "turn-packet.h"
#include <atomic>
#include <jni.h>
#include <chrono>
#include <poll.h>
#include "zmala_terminal/common/native/turn-write.h"

static std::atomic<long> reads{0};
static std::atomic<long> writes{0};

int ms2::turn::SslContext::write(const unsigned char *buffer, size_t length) {
    ++writes;
    int result = zmala::writeTurnFrame(buffer, length,
        [&](const unsigned char *data, size_t size) {
            int value = bctbx_ssl_write(mContext, data, size);
            if (value == BCTBX_ERROR_NET_WANT_READ) return zmala::waitRead;
            if (value == BCTBX_ERROR_NET_WANT_WRITE) return zmala::waitWrite;
            return value > 0 ? value : -1;
        },
        [&](int mode) {
            pollfd fd{mSocket, short(mode == zmala::waitRead ? POLLIN : POLLOUT), 0};
            int ready = poll(&fd, 1, 100);
            return (fd.revents & (POLLERR | POLLHUP | POLLNVAL)) ? -1 : ready;
        },
        []() { return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count(); });
    if (result < 0) shutdown(mSocket, SHUT_RDWR);
    return result;
}

// The SDK inlines SslContext::write into its send method. Interpose this exported
// call boundary as well, so the correction is reached by the actual SDK thread.
int ms2::turn::TurnSocket::send(std::unique_ptr<Packet> packet) {
    if (mSsl) return mSsl->write(packet->data(), packet->length());
    int result = zmala::writeTurnFrame(packet->data(), packet->length(),
        [&](const unsigned char *data, size_t size) {
            int value = ::send(mSocket, data, size, MSG_NOSIGNAL);
            if (value < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) return zmala::waitWrite;
            return value > 0 ? value : -1;
        },
        [&](int) { pollfd fd{mSocket, POLLOUT, 0}; return poll(&fd, 1, 100); },
        []() { return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count(); });
    if (result < 0) shutdown(mSocket, SHUT_RDWR);
    return result;
}

// The pinned SDK's reader loses alignment when TLS splits ChannelData padding.
// Keep incomplete wire frames; remove padding only when emitting a whole frame.
int ms2::turn::PacketReader::parseData(std::unique_ptr<Packet> rawPacket) {
    ++reads;
    if (mCurPacket) mCurPacket->concat(rawPacket);
    else mCurPacket = std::move(rawPacket);
    size_t used = 0, total = mCurPacket->length();
    const uint8_t *data = mCurPacket->data();
    while (total - used >= 4) {
        const uint8_t *p = data + used;
        const bool channel = (p[0] & 0xc0) == 0x40;
        const size_t header = channel ? 4 : 20;
        const size_t length = (size_t(p[2]) << 8) | p[3];
        const size_t wire = header + ((length + 3) & ~size_t(3));
        if (total - used < wire) break;
        mTurnPackets.push_back(std::make_unique<Packet>(p, header + length));
        used += wire;
    }
    if (used == total) mCurPacket.reset();
    else if (used) mCurPacket = std::make_unique<Packet>(data + used, total - used);
    return 0;
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_zmala_phone_TurnTransport_readCount(JNIEnv *, jclass) {
    return reads.load();
}

extern "C" JNIEXPORT jlong JNICALL
Java_org_zmala_phone_TurnTransport_writeCount(JNIEnv *, jclass) {
    return writes.load();
}
