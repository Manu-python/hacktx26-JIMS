/**
 * ESP32-WROOM optical receiver for ranked laser messages.
 *
 * Hardware:
 * - Photoresistor divider -> GPIO34
 * - LCD SDA -> GPIO21
 * - LCD SCL -> GPIO22
 *
 * Optical protocol:
 * - OOK: ON = 1, OFF = 0
 * - Start bit = ON
 * - 8 data bits, least-significant bit first
 * - Stop bit = OFF
 * - Newline character ends one ranked message
 */

#include <Arduino.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <stdlib.h>
#include <string.h>

constexpr uint8_t PHOTO_PIN = 34;
constexpr uint8_t LCD_SDA = 21;
constexpr uint8_t LCD_SCL = 22;
constexpr uint8_t LCD_ADDRESS = 0x27;

constexpr uint32_t SERIAL_BAUD = 115200;

// Must exactly match the Uno transmitter.
constexpr uint32_t BIT_MS = 200;
constexpr uint32_t SAMPLE_MS = 5;

constexpr uint32_t BASELINE_MS = 2500;
constexpr uint32_t BEACON_CONFIRM_MS = 100;
constexpr uint32_t BEACON_MIN_MS = 3000;
constexpr uint32_t BEACON_MAX_MS = 4800;

constexpr int TRIGGER_DELTA = 80;
constexpr int MIN_SIGNAL_DELTA = 100;
constexpr int HYSTERESIS_ADC = 20;

constexpr size_t MAX_MESSAGE_LENGTH = 128;
constexpr uint8_t MAX_RUN_BITS = 16;

LiquidCrystal_I2C lcd(LCD_ADDRESS, 16, 2);

enum class Mode {
  WaitBeacon,
  MeasureBeacon,
  Receive,
  Error
};

enum class FrameState {
  WaitStart,
  Data,
  Stop
};

Mode mode = Mode::WaitBeacon;
FrameState frameState = FrameState::WaitStart;

// Calibration state.
int ambientADC = 0;
int onADC = 0;
int thresholdADC = 0;

bool onRaisesADC = true;
bool opticalOn = false;

uint32_t nextSampleAt = 0;
uint32_t beaconCandidateAt = 0;
uint32_t beaconStartAt = 0;
uint32_t beaconOffAt = 0;
uint32_t beaconSum = 0;
uint32_t beaconSamples = 0;

// Run-duration decoder state.
bool haveRun = false;
bool runWasOn = false;
uint32_t runStartedAt = 0;

// Handles the Uno's post-message marker pulse.
bool waitingForFlushMarker = false;
bool ignoringMarkerIdleOffRun = false;

// Byte and message state.
uint8_t currentByte = 0;
uint8_t bitIndex = 0;

char received[MAX_MESSAGE_LENGTH] = {0};
size_t messageLength = 0;
uint16_t completedMessageCount = 0;

// LCD state.
char visibleBits[9] = "________";
uint8_t lastAscii = 0;
bool showingAscii = false;
bool lcdProgressDirty = false;

void printPadded(const char* text) {
  char padded[17];
  snprintf(padded, sizeof(padded), "%-16.16s", text);
  lcd.print(padded);
}

void display(const char* top, const char* bottom) {
  lcd.clear();

  lcd.setCursor(0, 0);
  printPadded(top);

  lcd.setCursor(0, 1);
  printPadded(bottom);
}

void refreshProgressLCD() {
  if (mode != Mode::Receive || !lcdProgressDirty) {
    return;
  }

  char top[17];

  if (showingAscii) {
    const char printable =
      (lastAscii >= 32 && lastAscii <= 126)
        ? static_cast<char>(lastAscii)
        : '?';

    snprintf(
      top,
      sizeof(top),
      "ASCII %u: %c",
      static_cast<unsigned int>(lastAscii),
      printable
    );
  } else {
    snprintf(top, sizeof(top), "BIN: %s", visibleBits);
  }

  const char* textTail = received;
  if (messageLength > 16) {
    textTail = received + messageLength - 16;
  }

  lcd.setCursor(0, 0);
  printPadded(top);

  lcd.setCursor(0, 1);
  printPadded(textTail);

  lcdProgressDirty = false;
}

int readADC() {
  int sum = 0;

  for (uint8_t i = 0; i < 4; ++i) {
    sum += analogRead(PHOTO_PIN);
  }

  return sum / 4;
}

void fail(const char* reason) {
  Serial.print("[RX] ERROR: ");
  Serial.println(reason);

  display("RECEIVE ERROR", "Reset to retry");
  mode = Mode::Error;
}

void calibrateAmbient() {
  Serial.println("[RX] Keep laser OFF for 2.5 seconds...");
  display("OPTICAL RECEIVER", "Laser OFF now");

  uint32_t sum = 0;
  uint32_t samples = 0;
  const uint32_t start = millis();

  while (millis() - start < BASELINE_MS) {
    sum += readADC();
    ++samples;
    delay(10);
  }

  ambientADC = static_cast<int>(sum / samples);

  Serial.print("[RX] OFF ADC = ");
  Serial.println(ambientADC);

  Serial.println("[RX] Waiting for calibration beacon...");
  display("WAITING FOR", "CALIBRATION");
}

bool detectOpticalOn(int adc) {
  if (onRaisesADC) {
    if (!opticalOn && adc >= thresholdADC + HYSTERESIS_ADC) {
      opticalOn = true;
    } else if (opticalOn && adc <= thresholdADC - HYSTERESIS_ADC) {
      opticalOn = false;
    }
  } else {
    if (!opticalOn && adc <= thresholdADC - HYSTERESIS_ADC) {
      opticalOn = true;
    } else if (opticalOn && adc >= thresholdADC + HYSTERESIS_ADC) {
      opticalOn = false;
    }
  }

  return opticalOn;
}

void processBeacon(int adc, uint32_t now) {
  if (mode == Mode::WaitBeacon) {
    if (abs(adc - ambientADC) >= TRIGGER_DELTA) {
      if (beaconCandidateAt == 0) {
        beaconCandidateAt = now;
      }

      if (now - beaconCandidateAt >= BEACON_CONFIRM_MS) {
        beaconStartAt = beaconCandidateAt;
        beaconOffAt = 0;
        beaconSum = 0;
        beaconSamples = 0;
        mode = Mode::MeasureBeacon;
      }
    } else {
      beaconCandidateAt = 0;
    }

    return;
  }

  const uint32_t elapsed = now - beaconStartAt;

  if (elapsed >= 1000 && elapsed < 2500) {
    beaconSum += adc;
    ++beaconSamples;
  }

  const int averageOn = beaconSamples
    ? static_cast<int>(beaconSum / beaconSamples)
    : ambientADC;

  const int delta = abs(averageOn - ambientADC);
  const int halfSignal = delta / 2;

  const bool returnedOff =
    elapsed >= 2500 &&
    halfSignal >= MIN_SIGNAL_DELTA / 2 &&
    abs(adc - ambientADC) <= halfSignal;

  if (returnedOff) {
    if (beaconOffAt == 0) {
      beaconOffAt = now;
    }
  } else {
    beaconOffAt = 0;
  }

  if (beaconOffAt != 0 && now - beaconOffAt >= BEACON_CONFIRM_MS) {
    const uint32_t duration = beaconOffAt - beaconStartAt;

    if (
      duration < BEACON_MIN_MS ||
      duration > BEACON_MAX_MS ||
      delta < MIN_SIGNAL_DELTA
    ) {
      fail("Invalid beacon or weak signal");
      return;
    }

    onADC = averageOn;
    thresholdADC = (ambientADC + onADC) / 2;
    onRaisesADC = onADC > ambientADC;

    opticalOn = false;
    haveRun = false;
    frameState = FrameState::WaitStart;
    mode = Mode::Receive;

    Serial.println("[RX] Calibration OK. Receiving ranked messages.");
    display("LINK SYNCED", "Receiving...");
  } else if (elapsed > BEACON_MAX_MS + 1500) {
    fail("Beacon timeout");
  }
}

void completeMessage() {
  received[messageLength] = '\0';
  ++completedMessageCount;

  Serial.print("[RX] RANKED MESSAGE ");
  Serial.print(completedMessageCount);
  Serial.print(": ");
  Serial.println(received);

  char title[17];
  snprintf(
    title,
    sizeof(title),
    "MSG %u RECEIVED",
    static_cast<unsigned int>(completedMessageCount)
  );

  display(title, received);

  // The Uno now emits a marker pulse that flushes the last OFF run.
  waitingForFlushMarker = true;

  messageLength = 0;
  received[0] = '\0';

  // Preserve the completed-message view until the next message begins.
  lcdProgressDirty = false;
  showingAscii = false;
}

void completeByte() {
  Serial.print("[RX] Byte: ");

  if (currentByte >= 32 && currentByte <= 126) {
    Serial.write(currentByte);
  } else if (currentByte == '\n') {
    Serial.print("\\n");
  } else {
    Serial.print("[non-printable]");
  }

  Serial.print(" | ASCII: ");
  Serial.println(static_cast<unsigned int>(currentByte));

  if (currentByte == '\r') {
    return;
  }

  if (currentByte == '\n') {
    completeMessage();
    return;
  }

  if (messageLength >= MAX_MESSAGE_LENGTH - 1) {
    fail("Message exceeded receiver buffer");
    return;
  }

  received[messageLength++] =
    (currentByte >= 32 && currentByte <= 126)
      ? static_cast<char>(currentByte)
      : '?';

  received[messageLength] = '\0';

  lastAscii = currentByte;
  showingAscii = true;
  lcdProgressDirty = true;
}

void consumeBit(bool bit) {
  if (mode != Mode::Receive) {
    return;
  }

  switch (frameState) {
    case FrameState::WaitStart:
      if (bit) {
        currentByte = 0;
        bitIndex = 0;

        memcpy(visibleBits, "________", sizeof(visibleBits));

        showingAscii = false;
        lcdProgressDirty = true;
        frameState = FrameState::Data;
      }
      break;

    case FrameState::Data:
      if (bit) {
        currentByte |= (1u << bitIndex);
      }

      visibleBits[7 - bitIndex] = bit ? '1' : '0';
      showingAscii = false;
      lcdProgressDirty = true;

      ++bitIndex;

      if (bitIndex == 8) {
        frameState = FrameState::Stop;
      }
      break;

    case FrameState::Stop:
      if (bit) {
        fail("Stop bit must be OFF");
      } else {
        frameState = FrameState::WaitStart;
        completeByte();
      }
      break;
  }
}

void processRun(bool level, uint32_t durationMs) {
  const uint32_t bits = (durationMs + BIT_MS / 2) / BIT_MS;

  // Ignore the Uno's one-bit ON end-of-message marker.
  if (waitingForFlushMarker && level) {
    if (bits != 1) {
      fail("Invalid end marker");
      return;
    }

    waitingForFlushMarker = false;
    ignoringMarkerIdleOffRun = true;
    return;
  }

  // Ignore the idle OFF period after that marker.
  if (ignoringMarkerIdleOffRun && !level) {
    ignoringMarkerIdleOffRun = false;
    return;
  }

  if (bits == 0 || bits > MAX_RUN_BITS) {
    fail("Run too short or long");
    return;
  }

  for (uint32_t i = 0; i < bits && mode == Mode::Receive; ++i) {
    consumeBit(level);
  }
}

void processReceive(int adc, uint32_t now) {
  const bool level = detectOpticalOn(adc);

  if (!haveRun) {
    // Ignore the OFF gap after calibration.
    if (level) {
      haveRun = true;
      runWasOn = true;
      runStartedAt = now;

      Serial.println("[RX] First start bit detected");
      display("BIN: ________", "Receiving...");
    }

    return;
  }

  if (level != runWasOn) {
    const uint32_t duration = now - runStartedAt;
    const bool finishedRunLevel = runWasOn;

    runStartedAt = now;
    runWasOn = level;

    processRun(finishedRunLevel, duration);
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  delay(300);

  Serial.println();
  Serial.println("=== ESP32 RANKED LASER RECEIVER ===");
  Serial.println("USB serial: 115200 | Optical bit: 200 ms");

  pinMode(PHOTO_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(PHOTO_PIN, ADC_11db);

  Wire.begin(LCD_SDA, LCD_SCL);
  Wire.setClock(100000);

  lcd.init();
  lcd.backlight();

  calibrateAmbient();
  nextSampleAt = millis();
}

void loop() {
  if (mode == Mode::Error) {
    return;
  }

  const uint32_t now = millis();

  if ((int32_t)(now - nextSampleAt) < 0) {
    return;
  }

  nextSampleAt = now + SAMPLE_MS;

  const int adc = readADC();

  if (mode == Mode::Receive) {
    processReceive(adc, now);
    refreshProgressLCD();
  } else {
    processBeacon(adc, now);
  }
}