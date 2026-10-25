/**
 * Arduino Uno: receive ranked messages from laptop over USB serial,
 * then transmit each message with an OOK laser.
 *
 * USB serial protocol:
 * - Python waits for "READY"
 * - Python sends one UTF-8 message ending in '\n'
 * - Uno transmits it optically, then replies "SENT <number>"
 */

#include <Arduino.h>

constexpr uint8_t LASER_PIN = 9;
constexpr uint32_t SERIAL_BAUD = 115200;

// Must match the ESP32 receiver exactly.
constexpr uint32_t BIT_MS = 200;

constexpr uint32_t INITIAL_OFF_MS = 8000;
constexpr uint32_t BEACON_ON_MS = 4000;
constexpr uint32_t BEACON_OFF_MS = 4000;
constexpr uint32_t BYTE_GAP_MS = BIT_MS;
constexpr uint32_t END_OFF_MS = BIT_MS;

constexpr size_t MAX_MESSAGE_LENGTH = 96;

char incomingMessage[MAX_MESSAGE_LENGTH];
size_t incomingLength = 0;
bool discardingOversizeMessage = false;
uint16_t sentMessageCount = 0;

void setLaser(bool on) {
  digitalWrite(LASER_PIN, on ? HIGH : LOW);
}

void sendByte(uint8_t value) {
  // Start bit: ON.
  setLaser(true);
  delay(BIT_MS);

  // Eight data bits, least-significant bit first.
  for (uint8_t i = 0; i < 8; ++i) {
    setLaser((value & (1u << i)) != 0);
    delay(BIT_MS);
  }

  // Stop bit plus idle gap: OFF.
  setLaser(false);
  delay(BIT_MS);
  delay(BYTE_GAP_MS);
}

void finishOpticalFrame() {
  // Flush the final OFF run for the ESP32 receiver.
  setLaser(false);
  delay(END_OFF_MS);

  setLaser(true);
  delay(BIT_MS);

  setLaser(false);
}

void transmitMessage(const char* message) {
  for (size_t i = 0; message[i] != '\0'; ++i) {
    sendByte(static_cast<uint8_t>(message[i]));
  }

  // The ESP32 uses this newline as the end of one ranked message.
  sendByte('\n');
  finishOpticalFrame();
}

void processSerialInput() {
  while (Serial.available() > 0) {
    const char received = static_cast<char>(Serial.read());

    // Accept either LF or CRLF from the laptop.
    if (received == '\r') {
      continue;
    }

    if (discardingOversizeMessage) {
      if (received == '\n') {
        discardingOversizeMessage = false;
        Serial.println("ERROR message too long");
      }
      continue;
    }

    if (received == '\n') {
      if (incomingLength == 0) {
        continue;
      }

      incomingMessage[incomingLength] = '\0';
      ++sentMessageCount;

      Serial.print("[TX] Sending ranked message ");
      Serial.println(sentMessageCount);

      // Blocks until the full laser payload has been transmitted.
      transmitMessage(incomingMessage);

      // Python waits for this before sending the next ranked message.
      Serial.print("SENT ");
      Serial.println(sentMessageCount);

      incomingLength = 0;
      return;
    }

    if (incomingLength >= MAX_MESSAGE_LENGTH - 1) {
      incomingLength = 0;
      discardingOversizeMessage = true;
      continue;
    }

    incomingMessage[incomingLength++] = received;
  }
}

void setup() {
  pinMode(LASER_PIN, OUTPUT);
  setLaser(false);

  Serial.begin(SERIAL_BAUD);

  Serial.println();
  Serial.println("=== UNO RANKED LASER TRANSMITTER ===");
  Serial.println("USB Serial: 115200 baud; optical: 5 bits/s");

  // ESP32 should already be running and measuring its ambient baseline.
  Serial.println("[TX] 8 seconds laser OFF");
  delay(INITIAL_OFF_MS);

  Serial.println("[TX] Calibration beacon ON for 4 seconds");
  setLaser(true);
  delay(BEACON_ON_MS);

  setLaser(false);
  Serial.println("[TX] Calibration beacon OFF for 4 seconds");
  delay(BEACON_OFF_MS);

  // Python will wait for this exact status before sending ranked messages.
  Serial.println("READY");
}

void loop() {
  processSerialInput();
}