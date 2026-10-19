#pragma once
#include "../../../zmala_terminal/common/native/turn-write.h"
#include <vector>

inline bool verifyTurnWrites() {
    std::vector<unsigned char> input(4096), output;
    for (size_t i = 0; i < input.size(); ++i) input[i] = uint8_t(i);
    uint64_t time = 0;
    int writes = 0, waits = 0;
    const unsigned char *blockedAt = nullptr;
    size_t blockedSize = 0;
    bool sameBuffer = true, sawRead = false, sawWrite = false;
    auto writer = [&](const unsigned char *data, size_t size) {
        if (blockedAt) {
            sameBuffer &= data == blockedAt && size == blockedSize;
            blockedAt = nullptr;
        }
        if (++writes % 3 == 0) {
            blockedAt = data; blockedSize = size;
            return writes % 2 ? zmala::waitRead : zmala::waitWrite;
        }
        size_t count = size < 97 ? size : 97;
        output.insert(output.end(), data, data + count);
        return int(count);
    };
    auto wait = [&](int mode) {
        ++waits; time += 5;
        sawRead |= mode == zmala::waitRead; sawWrite |= mode == zmala::waitWrite;
        return 1;
    };
    auto clock = [&]() { return time; };
    if (zmala::writeTurnFrame(input.data(), input.size(), writer, wait, clock) != int(input.size()) ||
        output != input || !sameBuffer || !sawRead || !sawWrite || waits == 0) return false;
    time = 0;
    if (zmala::writeTurnFrame(input.data(), input.size(), [](auto, auto) { return zmala::waitWrite; },
        [&](int) { time += 100; return 0; }, clock) != -1 || time != 3000) return false;
    int calls = 0;
    if (zmala::writeTurnFrame(input.data(), input.size(), [&](auto, auto) { return ++calls == 1 ? 17 : 0; },
        wait, clock) != -1 || calls != 2) return false;
    calls = 0;
    return zmala::writeTurnFrame(input.data(), input.size(), [&](auto, auto) { ++calls; return zmala::waitRead; },
        [](int) { return -1; }, clock) == -1 && calls == 1;
}
