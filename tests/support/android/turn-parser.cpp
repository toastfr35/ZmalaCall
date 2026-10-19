// SPDX-License-Identifier: AGPL-3.0-or-later
#include "turn-packet.h"
#include <dlfcn.h>
#include <jni.h>
#include <cstring>
#include <vector>
#include "../native/turn-write-cases.h"

extern "C" MSTurnContext *ms_turn_context_new(int, void *);
extern "C" void ms_turn_context_set_state(MSTurnContext *, int);
extern "C" void ms_turn_context_destroy(MSTurnContext *);

using namespace ms2::turn;
using Bytes = std::vector<uint8_t>;
using Parse = int (*)(PacketReader *, std::unique_ptr<Packet>);

extern "C" JNIEXPORT jstring JNICALL
Java_org_zmala_phone_TurnParserTest_verifyFrames(JNIEnv *env, jclass) {
    std::vector<Bytes> frames;
    Bytes wire;
    for (size_t length : {1, 2, 3, 4, 5, 1239, 1240, 1241}) {
        Bytes frame{0x40, 1, uint8_t(length >> 8), uint8_t(length)};
        for (size_t i = 0; i < length; ++i) frame.push_back(uint8_t(i));
        frames.push_back(frame);
        wire.insert(wire.end(), frame.begin(), frame.end());
        while (wire.size() % 4) wire.push_back(0xaa);
    }
    Bytes stun(24, 0);
    stun[1] = 1; stun[3] = 4;
    frames.push_back(stun);
    wire.insert(wire.end(), stun.begin(), stun.end());
    auto *context = ms_turn_context_new(0, nullptr);
    ms_turn_context_set_state(context, 5); // SDK 5.5.32 BINDING_CHANNEL.
    auto verify = [&](size_t chunk, Parse parse) {
        PacketReader reader(context);
        size_t count = 0;
        for (size_t offset = 0; offset < wire.size(); offset += chunk) {
            auto data = std::make_unique<Packet>(wire.data() + offset, std::min(chunk, wire.size() - offset));
            if (parse) parse(&reader, std::move(data));
            else reader.parseData(std::move(data));
            while (auto packet = reader.getTurnPacket()) {
                if (count >= frames.size() || packet->length() != frames[count].size() ||
                    memcmp(packet->data(), frames[count].data(), packet->length())) return false;
                ++count;
            }
        }
        return count == frames.size();
    };
    const char *result = "3804 chunk sizes passed; original defect reproduced";
    void *sdk = dlopen("libmediastreamer2.so", RTLD_NOW);
    auto original = reinterpret_cast<Parse>(dlsym(sdk,
        "_ZN3ms24turn12PacketReader9parseDataENSt6__ndk110unique_ptrINS0_6PacketENS2_14default_deleteIS4_EEEE"));
    if (!original || verify(4, original)) result = "Original negative control did not fail";
    else {
        for (size_t chunk = 1; chunk <= wire.size(); ++chunk) {
            if (!verify(chunk, nullptr)) { result = "Corrected parser failed"; break; }
        }
    }
    if (sdk) dlclose(sdk);
    ms_turn_context_destroy(context);
    if (!verifyTurnWrites()) result = "TURN write recovery failed";
    return env->NewStringUTF(result);
}
