/*
 * VAAS Arduino Nano barrier firmware
 * --------------------------------------
 * Reads commands of the form  "OPEN:GATE_A\n" or "CLOSE:GATE_B\n"
 * over USB serial @ 9600 baud and drives one servo per gate.
 *
 * Wiring (testbed):
 *   GATE_A servo signal -> D9
 *   GATE_B servo signal -> D10
 *   Servos VCC -> 5V (or external 5V supply, common GND with Nano)
 *
 * Open angle: 90 degrees, Close angle: 0 degrees.
 * Auto-close after AUTO_CLOSE_MS milliseconds if no further command.
 */

#include <Servo.h>

const uint8_t  PIN_GATE_A    = 9;
const uint8_t  PIN_GATE_B    = 10;
const uint16_t OPEN_ANGLE    = 90;
const uint16_t CLOSE_ANGLE   = 0;
const uint32_t AUTO_CLOSE_MS = 5000UL;

Servo servoA, servoB;
uint32_t openAtA = 0, openAtB = 0;
String inbuf;

void closeGate(char which) {
  if (which == 'A') { servoA.write(CLOSE_ANGLE); openAtA = 0; }
  else              { servoB.write(CLOSE_ANGLE); openAtB = 0; }
}

void openGate(char which) {
  uint32_t now = millis();
  if (which == 'A') { servoA.write(OPEN_ANGLE); openAtA = now; }
  else              { servoB.write(OPEN_ANGLE); openAtB = now; }
}

void handleLine(const String& line) {
  // Expect "OPEN:GATE_A" or "CLOSE:GATE_B"
  int colon = line.indexOf(':');
  if (colon < 0) return;
  String cmd  = line.substring(0, colon);
  String gate = line.substring(colon + 1);
  char which = 'A';
  if      (gate == "GATE_A") which = 'A';
  else if (gate == "GATE_B") which = 'B';
  else return;

  if (cmd == "OPEN") {
    openGate(which);
    Serial.print("ACK:OPEN:"); Serial.println(gate);
  } else if (cmd == "CLOSE") {
    closeGate(which);
    Serial.print("ACK:CLOSE:"); Serial.println(gate);
  }
}

void setup() {
  Serial.begin(9600);
  servoA.attach(PIN_GATE_A);
  servoB.attach(PIN_GATE_B);
  closeGate('A');
  closeGate('B');
  Serial.println("VAAS_BARRIER_READY");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (inbuf.length() > 0) {
        handleLine(inbuf);
        inbuf = "";
      }
    } else if (inbuf.length() < 64) {
      inbuf += c;
    }
  }
  uint32_t now = millis();
  if (openAtA && now - openAtA > AUTO_CLOSE_MS) closeGate('A');
  if (openAtB && now - openAtB > AUTO_CLOSE_MS) closeGate('B');
}
