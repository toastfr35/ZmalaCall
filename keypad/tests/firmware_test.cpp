// Behaviour tests execute the production .ino with simulated pins/time/serial.
#include "Arduino.h"
#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <limits>

uint32_t testMillis = 0;
int testInputs[20];
int testOutputs[20];
int testModes[20];
FakeSerial Serial;
#include "../firmware/ZmalaCallKeypad/ZmalaCallKeypad.ino"

int checks = 0;
void check(bool condition, const char *message) {
  ++checks;
  if (!condition) {
    std::cerr << "FAIL: " << message << '\n';
    std::exit(1);
  }
}

void reset(uint32_t time = 0, int heldPin = -1) {
  testMillis = time;
  std::fill_n(testInputs, 20, HIGH);
  std::fill_n(testOutputs, 20, -1);
  std::fill_n(testModes, 20, -1);
  if (heldPin >= 0) testInputs[heldPin] = LOW;
  Serial = FakeSerial();
  setup();
}

void advance(uint32_t milliseconds) {
  for (uint32_t i = 0; i < milliseconds; ++i) {
    ++testMillis;
    loop();
  }
}

void send(const std::string &bytes) {
  Serial.receive(bytes);
  while (Serial.available()) loop();
}

void connect() {
  send("?");
  advance(30);
  check(Serial.output == "!", "connection replies with one byte, no banner");
  Serial.output.clear();
}

void setSwitch(int pin, bool pressed) {
  testInputs[pin] = pressed ? LOW : HIGH;
  loop();
}

void tap(int pin) {
  setSwitch(pin, true);
  advance(30);
  setSwitch(pin, false);
  advance(30);
}

int main() {
  reset();
  check(Serial.baud == 9600 && Serial.format == SERIAL_8N1, "9600 8N1");
  for (int i = 0; i < 4; ++i) {
    check(testModes[2 + i] == INPUT_PULLUP, "switch pull-up configured");
    check(testModes[6 + i] == OUTPUT && testOutputs[6 + i] == LOW, "lamp initially off");
  }
  send("LRGX\r\n");
  tap(4);
  check(Serial.output.empty() && testOutputs[8] == LOW, "disconnected commands/presses ignored");

  reset();
  connect();
  send("LRGX");
  for (int pin = 6; pin <= 9; ++pin) check(testOutputs[pin] == HIGH, "lamp-on mapping");
  send("LRGXlrgx\r\n!z");
  for (int pin = 6; pin <= 9; ++pin) check(testOutputs[pin] == LOW, "lamp-off mapping");
  check(Serial.output.empty(), "lamp commands and unknown bytes never echo");
  for (int pin = 2; pin <= 5; ++pin) tap(pin);
  check(Serial.output == "LRGX", "all four presses mapped, including unlit buttons");

  reset();
  connect();
  setSwitch(4, true); advance(10);
  setSwitch(4, false); advance(10);
  setSwitch(4, true); advance(29);
  check(Serial.output.empty(), "bounce and sub-30ms press suppressed");
  advance(1);
  check(Serial.output == "G", "one event at stable 30ms press");
  Serial.output.clear();
  for (int second = 0; second < 30; ++second) {
    send("?"); advance(1000);
  }
  check(Serial.output == std::string(30, '!'), "30-second hold sends no repeats");
  Serial.output.clear();
  setSwitch(4, false); advance(10);
  setSwitch(4, true); advance(30);
  check(Serial.output.empty(), "release bounce does not rearm a held button");
  setSwitch(4, false); advance(30);
  tap(4);
  check(Serial.output == "G", "distinct release and repress sends a fresh event");

  reset(0, 4);
  connect();
  tap(2);
  check(Serial.output.empty(), "held-at-start button inhibits every button");
  setSwitch(4, false); advance(30);
  check(Serial.output.empty(), "initial release causes no press");
  tap(4);
  check(Serial.output == "G", "startup release permits subsequent fresh press");

  reset();
  send("?"); advance(20);
  setSwitch(4, true); advance(30);
  check(Serial.output == "!", "raw hold during initial arming window is suppressed");

  reset();
  connect();
  for (int pin = 2; pin <= 5; ++pin) testInputs[pin] = LOW;
  loop(); advance(30);
  check(Serial.output == "LRGX", "simultaneous presses have deterministic order");

  reset();
  connect();
  send("LRGX");
  advance(4969);
  check(testOutputs[6] == HIGH, "session remains active before exact deadline");
  advance(1);
  for (int pin = 6; pin <= 9; ++pin) check(testOutputs[pin] == LOW, "heartbeat timeout turns lamps off");
  tap(4); send("G");
  check(Serial.output.empty() && testOutputs[8] == LOW, "timeout inhibits buttons and lamp commands");
  setSwitch(4, true); advance(30);
  send("?"); advance(30);
  check(Serial.output == "!", "reconnect with held button replies but reports no press");
  Serial.output.clear();
  setSwitch(4, false); advance(30); tap(4);
  check(Serial.output == "G", "reconnect requires release before fresh press");

  reset(); connect();
  for (int second = 0; second < 5; ++second) { send("G\r\nz"); advance(1000); }
  check(testOutputs[8] == LOW && !connected, "lamp/unknown commands cannot replace heartbeat");

  reset(); connect();
  testMillis = 5000; setSwitch(4, true); send("?"); advance(30);
  check(Serial.output == "!", "late heartbeat expires session before reconnect; held press discarded");

  reset(std::numeric_limits<uint32_t>::max() - 20);
  connect(); tap(5);
  check(Serial.output == "X", "debounce and arming survive millis rollover");
  send("X"); advance(4910);
  check(testOutputs[9] == LOW, "heartbeat timeout survives millis rollover");

  reset(); connect();
  for (int i = 0; i < 10; ++i) tap(5);
  check(Serial.output == std::string(10, 'X'), "ten distinct red presses produce ten events");

  reset(); connect();
  Serial.output.clear(); Serial.receive(std::string(16, '?'));
  loop();
  check(Serial.available() == 8 && Serial.output.size() == 8, "serial work bounded to eight bytes per scan");
  Serial.capacity = 0; setSwitch(4, true); advance(30);
  check(Serial.output.size() == 8, "TX congestion never blocks or queues a press");
  Serial.capacity = 63; loop();
  check(Serial.output == std::string(16, '!'), "congested press is not replayed later");

  std::cout << checks << " checks passed: protocol, GPIO, debounce, holds, reconnect, timeout, rollover and TX backpressure.\n";
}
