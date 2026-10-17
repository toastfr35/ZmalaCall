// Minimal Arduino core substitute for executing the actual sketch on a PC.
#pragma once
#include <cstdint>
#include <deque>
#include <string>

constexpr int LOW = 0;
constexpr int HIGH = 1;
constexpr int OUTPUT = 1;
constexpr int INPUT_PULLUP = 2;
constexpr int SERIAL_8N1 = 6;

extern uint32_t testMillis;
extern int testInputs[20];
extern int testOutputs[20];
extern int testModes[20];
inline unsigned long millis() { return testMillis; }
inline int digitalRead(uint8_t pin) { return testInputs[pin]; }
inline void digitalWrite(uint8_t pin, int value) { testOutputs[pin] = value; }
inline void pinMode(uint8_t pin, int mode) { testModes[pin] = mode; }

struct FakeSerial {
  std::deque<char> input;
  std::string output;
  unsigned long baud = 0;
  int format = 0;
  int capacity = 63;
  void begin(unsigned long speed, int config) { baud = speed; format = config; }
  int available() const { return static_cast<int>(input.size()); }
  int availableForWrite() const { return capacity; }
  int read() {
    if (input.empty()) return -1;
    char value = input.front();
    input.pop_front();
    return static_cast<unsigned char>(value);
  }
  void write(uint8_t value) { output += static_cast<char>(value); }
  void receive(const std::string &bytes) {
    for (char value : bytes) input.push_back(value);
  }
};
extern FakeSerial Serial;
