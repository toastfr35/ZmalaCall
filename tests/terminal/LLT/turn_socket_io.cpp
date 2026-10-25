// @test T-LLT-080
// @requirements LLR-TERM-COM-010
// @environment native-sdk
// @plan Compile the pinned SDK implementation into this fixture so its actual TLS socket callbacks run against a local nonblocking socketpair. Read an empty socket and fill its send buffer to real EAGAIN, then check WANT_READ/WANT_WRITE rather than connection reset. Drain and retry the exact bytes; check EOF and fatal write after peer closure. build-turn.py runs the original source as a failing negative control before the corrected source. No network service, credentials or TLS handshake is involved.
// @pass Original callbacks fail the EAGAIN assertion. Corrected callbacks report retryable backpressure, preserve successful payloads, return EOF and distinguish a real closed peer.
#ifndef ZMALA_TURN_SOURCE
#define ZMALA_TURN_SOURCE "turn_tcp.cpp"
#endif
#include ZMALA_TURN_SOURCE
#include <cassert>
#include <csignal>
#include <fcntl.h>
#include <iostream>

int main() {
    std::signal(SIGPIPE, SIG_IGN);
    int pair[2];
    assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
    for (int fd : pair) assert(fcntl(fd, F_SETFL, O_NONBLOCK) == 0);
    unsigned char buffer[4096]{};
    assert(ms2::turn::tls_callback_read(&pair[0], buffer, sizeof(buffer)) == BCTBX_ERROR_NET_WANT_READ);
    int size = 4096;
    assert(setsockopt(pair[0], SOL_SOCKET, SO_SNDBUF, &size, sizeof(size)) == 0);
    while (::send(pair[0], buffer, sizeof(buffer), 0) > 0) {}
    assert(errno == EAGAIN || errno == EWOULDBLOCK);
    assert(ms2::turn::tls_callback_write(&pair[0], buffer, sizeof(buffer)) == BCTBX_ERROR_NET_WANT_WRITE);
    while (::recv(pair[1], buffer, sizeof(buffer), 0) > 0) {}
    const unsigned char message[] = {0x40, 1, 0, 3, 1, 2, 3, 0};
    assert(ms2::turn::tls_callback_write(&pair[0], message, sizeof(message)) == sizeof(message));
    assert(::recv(pair[1], buffer, sizeof(buffer), 0) == sizeof(message));
    assert(memcmp(buffer, message, sizeof(message)) == 0);
    ::close(pair[1]);
    assert(ms2::turn::tls_callback_read(&pair[0], buffer, sizeof(buffer)) == 0);
    assert(ms2::turn::tls_callback_write(&pair[0], message, sizeof(message)) == BCTBX_ERROR_NET_CONN_RESET);
    ::close(pair[0]);
    std::cout << "TURN socket callbacks: real EAGAIN, retry, EOF and fatal error passed\n";
}
