// WSU-SEN 309 Embedded Software and Data Systems Lab
// Practical 1  |  Timed acquisition and structured serial output (STARTER: complete the TODOs)
// (c) 2026 Wellspring University, Faculty of Computing. For registered WSU-SEN 309 students.
//
// Runs on an Arduino Uno or in the Wokwi simulator (diagram.json in this folder).
// Wiring: NTC temperature module OUT -> A0, photoresistor module AO -> A1, alarm LED on D13.
// Serial: 115200 baud. Every line is <body>*<CK>, where CK is the XOR of the body bytes in hex.
// Commands (end with a newline): START, STOP, STATUS, HELLO, RATE <ms>, REPLAY <seq>.

#include <EEPROM.h>
#include <math.h>

// ---------------------------------------------------------------- settings
const char DEVICE_ID[] = "SN01";        // change to your own device id (SN + two digits)
const char FW_VERSION[] = "1.0";
const bool AUTOSTART = true;            // start sampling at power-up, without a START command

const uint8_t PIN_TEMP = A0;
const uint8_t PIN_LIGHT = A1;
const uint8_t PIN_ALARM_LED = 13;

const float BETA = 3950.0;              // NTC beta coefficient (Wokwi module)
const int16_t ALARM_ON_10 = 350;        // alarm at 35.0 C or more ...
const int16_t ALARM_OFF_10 = 330;       // ... and back to normal at 33.0 C or less (hysteresis)
const uint32_t PERIOD_MIN = 200;
const uint32_t PERIOD_MAX = 60000;

// ---------------------------------------------------------------- state
enum State : uint8_t { IDLE, RUN, ALARM };
State state = IDLE;

uint32_t periodMs = 1000;
uint32_t nextDue = 0;                   // millis() value at which the next sample is due
uint32_t seq = 0;                       // sequence number of the next reading
uint32_t sentCount = 0;                 // readings sent since the last START
uint16_t bootId = 0;

struct Sample {                         // one reading, kept for REPLAY
  uint32_t seq;
  uint32_t t;
  int16_t temp10;
  uint16_t light;
  uint8_t alarm;
};
const uint8_t RING_SIZE = 32;
Sample ring[RING_SIZE];
uint8_t ringNext = 0;                   // index the next sample is written to
uint8_t ringCount = 0;

char body[64];                          // the line being built
char cmd[25];                           // the command being received
uint8_t cmdLen = 0;
bool cmdOverflow = false;

// ---------------------------------------------------------------- framing
uint8_t checksum(const char *s) {
  uint8_t c = 0;
  // TODO 1 (Part A): XOR every character of s into c, up to the terminating '\0'.
  //   Check: checksum("H,SN01,1,1.0,1000") must be 0x4B.
  (void)s;
  return c;
}

void sendLine(const char *b) {
  char ck[3];
  snprintf(ck, sizeof ck, "%02X", checksum(b));
  Serial.print(b);
  Serial.print('*');
  Serial.println(ck);
}

// Write a value held in tenths as text: 246 -> "24.6", -5 -> "-0.5".
void tenths(char *out, size_t n, int16_t v10) {
  const char *sign = v10 < 0 ? "-" : "";
  int16_t a = v10 < 0 ? -v10 : v10;
  snprintf(out, n, "%s%d.%d", sign, a / 10, a % 10);
}

const char *stateName() {
  if (state == RUN) return "RUN";
  if (state == ALARM) return "ALM";
  return "IDLE";
}

void sendHello() {
  snprintf(body, sizeof body, "H,%s,%u,%s,%lu", DEVICE_ID, bootId, FW_VERSION, (unsigned long)periodMs);
  sendLine(body);
}

void sendAck(const char *what, const char *detail) {
  snprintf(body, sizeof body, "A,%s,%u,%s,%s", DEVICE_ID, bootId, what, detail);
  sendLine(body);
}

void sendError(const char *code, const char *detail) {
  snprintf(body, sizeof body, "X,%s,%u,%s,%s", DEVICE_ID, bootId, code, detail);
  sendLine(body);
}

void sendReading(const Sample &s) {
  char t[8];
  tenths(t, sizeof t, s.temp10);
  // TODO 2 (Part A): the reading has eight fields: R,<device>,<boot>,<seq>,<t_ms>,<temp_c>,<light>,<state>
  //   Only the first four are written so far. Add t_ms (s.t), the temperature text (t), the light
  //   value (s.light) and the state ("ALM" if s.alarm, otherwise "RUN").
  snprintf(body, sizeof body, "R,%s,%u,%lu", DEVICE_ID, bootId, (unsigned long)s.seq);
  (void)t;
  sendLine(body);
}

// ---------------------------------------------------------------- acquisition
// Returns false if the sensor reading is impossible (open or shorted sensor).
bool readTemp10(int16_t &out) {
  int a = analogRead(PIN_TEMP);
  if (a <= 0 || a >= 1023) return false;
  float c = 1.0 / (log(1.0 / (1023.0 / a - 1.0)) / BETA + 1.0 / 298.15) - 273.15;
  out = (int16_t)lround(c * 10.0);
  return true;
}

void takeSample(uint32_t now) {
  int16_t t10;
  if (!readTemp10(t10)) {
    sendError("SENSOR", "A0");          // no reading this period; seq is not used up
    return;
  }
  // TODO 4 (Part B): the embedded state machine. Go from RUN to ALARM when t10 >= ALARM_ON_10,
  //   and back from ALARM to RUN only when t10 <= ALARM_OFF_10 (hysteresis). Drive the LED.
  digitalWrite(PIN_ALARM_LED, state == ALARM ? HIGH : LOW);

  Sample s;
  s.seq = seq++;
  s.t = now;
  s.temp10 = t10;
  s.light = (uint16_t)analogRead(PIN_LIGHT);
  s.alarm = state == ALARM;
  ring[ringNext] = s;
  ringNext = (ringNext + 1) % RING_SIZE;
  if (ringCount < RING_SIZE) ringCount++;
  sentCount++;
  sendReading(s);
}

// ---------------------------------------------------------------- commands
void startRun() {
  state = RUN;
  sentCount = 0;
  nextDue = millis();
}

void stopRun() {
  long last = sentCount ? (long)(seq - 1) : -1L;
  snprintf(body, sizeof body, "E,%s,%u,%lu,%ld", DEVICE_ID, bootId, (unsigned long)sentCount, last);
  sendLine(body);
  state = IDLE;
  digitalWrite(PIN_ALARM_LED, LOW);
}

void replayFrom(uint32_t from) {
  uint8_t oldest = (ringNext + RING_SIZE - ringCount) % RING_SIZE;
  if (ringCount && from < ring[oldest].seq) {
    char d[12];
    snprintf(d, sizeof d, "%lu", (unsigned long)ring[oldest].seq);
    sendError("GONE", d);                // older readings are no longer held
  }
  uint8_t n = 0;
  for (uint8_t k = 0; k < ringCount; k++) {
    const Sample &s = ring[(oldest + k) % RING_SIZE];
    if (s.seq >= from) {
      sendReading(s);
      n++;
    }
  }
  char d[6];
  snprintf(d, sizeof d, "%u", n);
  sendAck("REPLAY", d);
}

// Parse an unsigned number; false if the text is empty or not all digits.
bool toNumber(const char *s, uint32_t &out) {
  if (!*s) return false;
  uint32_t v = 0;
  for (; *s; s++) {
    if (*s < '0' || *s > '9' || v > 400000000UL) return false;
    v = v * 10 + (uint32_t)(*s - '0');
  }
  out = v;
  return true;
}

void handleCommand(const char *c) {
  uint32_t n;
  if (strcmp(c, "START") == 0) {
    if (state == IDLE) startRun();
    sendAck("START", "-");
  } else if (strcmp(c, "STOP") == 0) {
    if (state == IDLE) sendError("NOT_RUNNING", "-");
    else stopRun();
  } else if (strcmp(c, "HELLO") == 0) {
    sendHello();
  // TODO 5 (Part B): add STATUS  -> S,<device>,<boot>,<IDLE|RUN|ALM>,<next seq>,<period_ms>
  //   and RATE <ms> -> if toNumber() succeeds and PERIOD_MIN <= ms <= PERIOD_MAX: set periodMs,
  //   set nextDue = millis() + periodMs and sendAck("RATE", c + 5); otherwise sendError("BAD_RATE", "-").
  } else if (strncmp(c, "REPLAY ", 7) == 0) {
    if (toNumber(c + 7, n)) replayFrom(n);
    else sendError("BAD_SEQ", "-");
  } else {
    sendError("UNKNOWN", "-");
  }
}

void readCommands() {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      cmd[cmdLen] = '\0';
      if (cmdOverflow) sendError("TOO_LONG", "-");
      else if (cmdLen > 0) handleCommand(cmd);
      cmdLen = 0;
      cmdOverflow = false;
    } else if (cmdLen < sizeof cmd - 1) {
      cmd[cmdLen++] = ch;
    } else {
      cmdOverflow = true;
    }
  }
}

// ---------------------------------------------------------------- setup and loop
void setup() {
  pinMode(PIN_ALARM_LED, OUTPUT);
  Serial.begin(115200);
  // boot counter in EEPROM: a new number after every reset, so the host can tell runs apart
  EEPROM.get(0, bootId);
  if (bootId == 0xFFFF) bootId = 0;       // a blank EEPROM reads as 0xFFFF
  bootId++;
  EEPROM.put(0, bootId);
  sendHello();
  if (AUTOSTART) startRun();
}

void loop() {
  readCommands();
  // TODO 3 (Part A): this version waits with delay(). It drifts (every reading takes a little
  //   longer than periodMs) and it cannot hear commands while it waits. Replace it with a
  //   non-blocking schedule: if state is not IDLE and millis() has reached nextDue, add periodMs
  //   to nextDue and call takeSample(now). Never call delay() in this sketch.
  if (state != IDLE) {
    takeSample(millis());
    delay(periodMs);
  }
}
