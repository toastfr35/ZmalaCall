// SPDX-License-Identifier: AGPL-3.0-or-later
#pragma once
#include <cstddef>
#include <cstdint>

// @llr LLR-AND-CALL-006
// @llr LLR-TERM-COM-010
namespace zmala {
constexpr int waitRead = -2, waitWrite = -3;

// A TLS write must retain its buffer across WANT_READ/WANT_WRITE. A successful
// short write advances only by the accepted bytes. Failure closes the transport
// at the caller, so a partial frame can never be followed by another frame.
template<class Write, class Wait, class Clock>
int writeTurnFrame(const unsigned char *data, size_t size, Write write, Wait wait, Clock now) {
    const uint64_t deadline = now() + 3000;
    size_t sent = 0;
    while (sent < size && now() < deadline) {
        int count = write(data + sent, size - sent);
        if (count > 0) {
            if (size_t(count) > size - sent) return -1;
            sent += size_t(count);
        } else if (count == waitRead || count == waitWrite) {
            if (wait(count) < 0) return -1;
        } else return -1;
    }
    return sent == size ? int(sent) : -1;
}
}
