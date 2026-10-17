// ZmalaCall four-button serial keypad: classic 5 V ATmega328P Nano.
// Protocol and wiring: ../../spec.md. No libraries beyond the Arduino core.
// D6-D9 -> 1 kohm -> bare LED anode; cathode -> GND.
// Each output also has a 10 kohm pull-down to GND. HIGH = LED on.
#include <Arduino.h>
#include <stdint.h>

namespace {
constexpr uint8_t BUTTON_COUNT = 4;
constexpr uint8_t SWITCH_PINS[BUTTON_COUNT] = {2, 3, 4, 5};
constexpr uint8_t LAMP_PINS[BUTTON_COUNT] = {6, 7, 8, 9};
constexpr char PRESS_BYTES[BUTTON_COUNT] = {'L', 'R', 'G', 'X'};
constexpr char OFF_BYTES[BUTTON_COUNT] = {'l', 'r', 'g', 'x'};
constexpr uint32_t DEBOUNCE_MS = 30;
constexpr uint32_t HEARTBEAT_TIMEOUT_MS = 5000;
constexpr uint8_t MAX_RX_PER_LOOP = 8;

struct SwitchState {
  bool rawPressed;
  bool stablePressed;
  uint32_t changedAt;
};

SwitchState switches[BUTTON_COUNT];
bool connected = false;
bool armed = false;
uint32_t lastHeartbeat = 0;
uint32_t sessionStarted = 0;

// Subtraction, rather than timestamp addition, also works across millis() wrap.
uint32_t elapsed(uint32_t now, uint32_t since) {
  return static_cast<uint32_t>(now - since);
}

void lampsOff() {
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    digitalWrite(LAMP_PINS[i], LOW);
  }
}

void expireSession(uint32_t now) {
  if (connected && elapsed(now, lastHeartbeat) >= HEARTBEAT_TIMEOUT_MS) {
    connected = false;
    armed = false;
    lampsOff();
  }
}

// Scan every loop, even without a host. Debounce press and release separately.
// The returned mask contains transitions from this scan only; nothing is replayed.
uint8_t scanSwitches(uint32_t now) {
  uint8_t pressed = 0;
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    SwitchState &button = switches[i];
    const bool raw = digitalRead(SWITCH_PINS[i]) == LOW;
    if (raw != button.rawPressed) {
      button.rawPressed = raw;
      button.changedAt = now;
    }
    if (raw != button.stablePressed && elapsed(now, button.changedAt) >= DEBOUNCE_MS) {
      button.stablePressed = raw;
      if (raw) {
        pressed |= static_cast<uint8_t>(1U << i);
      }
    }
  }
  return pressed;
}

bool allReleased(uint32_t now) {
  if (elapsed(now, sessionStarted) < DEBOUNCE_MS) {
    return false;
  }
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    const SwitchState &button = switches[i];
    // Check raw state as well: a newly held button must not slip through before
    // its press has finished debouncing.
    if (button.rawPressed || button.stablePressed ||
        elapsed(now, button.changedAt) < DEBOUNCE_MS) {
      return false;
    }
  }
  return true;
}

void receiveByte(char command, uint32_t now) {
  if (command == '?') {
    if (!connected) {
      connected = true;
      armed = false;
      sessionStarted = now;
    }
    lastHeartbeat = now;
    Serial.write(static_cast<uint8_t>('!'));
    return;
  }
  if (!connected) {
    return;
  }
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    if (command == PRESS_BYTES[i]) {
      digitalWrite(LAMP_PINS[i], HIGH);
      return;
    }
    if (command == OFF_BYTES[i]) {
      digitalWrite(LAMP_PINS[i], LOW);
      return;
    }
  }
  // No echo or debug output. Unknown bytes do not extend the session.
}
}  // namespace

void setup() {
  connected = false;
  armed = false;
  const uint32_t now = millis();
  lastHeartbeat = now;
  sessionStarted = now;
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    // Set the output latch before enabling the output. External pull-downs
    // keep lamps off while the bootloader runs and the GPIO pins are inputs.
    digitalWrite(LAMP_PINS[i], LOW);
    pinMode(LAMP_PINS[i], OUTPUT);
    pinMode(SWITCH_PINS[i], INPUT_PULLUP);
    const bool held = digitalRead(SWITCH_PINS[i]) == LOW;
    switches[i] = {held, held, now};
  }
  Serial.begin(9600, SERIAL_8N1);
}

void loop() {
  const uint32_t now = millis();
  // Expire before accepting a late query so it starts a fresh, unarmed session.
  expireSession(now);
  const uint8_t pressed = scanSwitches(now);

  // Bound work per loop and reserve four TX slots for simultaneous presses.
  // Even a burst of queries cannot make Serial.write block switch scanning.
  for (uint8_t n = 0; n < MAX_RX_PER_LOOP && Serial.available() > 0; ++n) {
    if (Serial.availableForWrite() < BUTTON_COUNT + 1) {
      break;
    }
    receiveByte(static_cast<char>(Serial.read()), now);
  }

  if (!connected) {
    return;
  }
  if (!armed) {
    armed = allReleased(now);
    return;  // Never report a press from the arming scan.
  }
  for (uint8_t i = 0; i < BUTTON_COUNT; ++i) {
    if ((pressed & static_cast<uint8_t>(1U << i)) != 0) {
      // A full TX buffer is abnormal at 9600 baud with four debounced switches.
      // Drop an event rather than block or queue an action for a later screen.
      if (Serial.availableForWrite() > 0) {
        Serial.write(static_cast<uint8_t>(PRESS_BYTES[i]));
      }
    }
  }
}
