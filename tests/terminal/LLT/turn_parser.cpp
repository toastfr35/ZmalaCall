// @test T-LLT-078
// @requirements LLR-TERM-COM-010
// @environment native-sdk
// @plan Compile the original and corrected pinned SDK parser. Feed ChannelData with every padding width and coalesced STUN frames at all 3804 chunk sizes, including incomplete headers. Compare each output byte and length. Require the original padded-length assertion to fail as a negative control. Run through build_tools/linux/build-turn.py. Inject short writes, alternating WANT_READ/WANT_WRITE, a stalled socket, peer closure and poll failure; assert exact output bytes, unchanged retry buffer/length and the three-second deadline.
// @pass The corrected parser preserves every frame and omits alignment padding; the original reproduces the known defect. Write retries preserve every byte and buffer identity; error/timeout paths fail within the bound.
#include "turn_tcp.h"
#include <cassert>
#include <cstring>
#include <cstdlib>
#include <iostream>
#include <vector>
#include "../../support/native/turn-write-cases.h"
using namespace ms2::turn;
using Bytes = std::vector<uint8_t>;

int main(int argc, char **argv) {
    MSTurnContext context{};
    context.state = MS_TURN_CONTEXT_STATE_BINDING_CHANNEL;
    std::vector<Bytes> frames;
    Bytes wire;
    for (size_t length : {1, 2, 3, 4, 5, 1239, 1240, 1241}) {
        Bytes packet{0x40, 1, uint8_t(length >> 8), uint8_t(length)};
        for (size_t i = 0; i < length; ++i) packet.push_back(uint8_t(i));
        frames.push_back(packet);
        wire.insert(wire.end(), packet.begin(), packet.end());
        while (wire.size() % 4) wire.push_back(0xaa);
    }
    Bytes stun(24, 0);
    stun[1] = 1; stun[3] = 4;
    frames.push_back(stun);
    wire.insert(wire.end(), stun.begin(), stun.end());
    auto verify = [&](size_t chunk) {
        PacketReader reader(&context);
        size_t count = 0;
        for (size_t offset = 0; offset < wire.size(); offset += chunk) {
            const size_t size = std::min(chunk, wire.size() - offset);
            reader.parseData(std::make_unique<Packet>(wire.data() + offset, size));
            while (auto packet = reader.getTurnPacket()) {
                assert(count < frames.size());
                assert(packet->length() == frames[count].size());
                assert(!memcmp(packet->data(), frames[count].data(), packet->length()));
                ++count;
            }
        }
        assert(count == frames.size());
    };
    if (argc == 2) verify(std::strtoul(argv[1], nullptr, 10));
    else for (size_t chunk = 1; chunk <= wire.size(); ++chunk) verify(chunk);
    assert(verifyTurnWrites());
    std::cout << "TURN framing: " << wire.size() << " chunk sizes passed\n";
}
