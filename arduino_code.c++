// Based on the Arduino IDE sketch supplied by you.
// Python sends LCD_IDLE:NEXT: MORNING|AT 08:00 AM for the scheduled time.
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Servo.h>
#include <stdlib.h>
#include <avr/pgmspace.h>
#include <math.h>  

// ==================================================
// COMPONENTS
// ==================================================

LiquidCrystal_I2C lcd(0x27, 16, 2);
Servo feederServo;

// ==================================================
// PIN ASSIGNMENTS
// ==================================================

const byte SERVO_PIN = 5;
const byte BUZZER_PIN = 3;

const byte RED_WARNING_LED = 9;
const byte MORNING_LED = 6;       // Blue
const byte AFTERNOON_LED = 7;     // Green
const byte NIGHT_LED = 8;         // Yellow

const byte ECHO_PIN = 13;
const byte TRIG_PIN = 12;

// ==================================================
// SERVO SETTINGS
// ==================================================

const int SERVO_STOP = 90;
const int SERVO_ROTATE = 60;

// ==================================================
// BUZZER
// ==================================================

const int BUZZER_FREQUENCY = 1000;


// ==================================================
// SETUP
// ==================================================

float FULL_DISTANCE_CM = 3.0;

// Default until Python sends the saved full and empty distances.
float EMPTY_DISTANCE_CM = 20.0;

// Read the ultrasonic sensor every 500 milliseconds.
const unsigned long SENSOR_INTERVAL = 500;

unsigned long previousSensorMillis = 0;

// Store the latest readings.
float currentDistanceCm = -1.0;
float currentFeedPercentage = 0.0;
bool hopperEmpty = false;
String idleLine1 = "FEEDER READY";
String idleLine2 = "WAITING FOR APP";
String feedingLabel = "";
String feedingState = "";
unsigned long completionStarted = 0;
bool lcdTestActive = false;
unsigned long lcdTestStarted = 0;
String lastLine1 = "";
String lastLine2 = "";

// Three-page rotation after a confirmed feeding: Complete -> Next -> distance.
// Python remains responsible for actual feeding times and daily scheduling.
String lastCompletedFeed = "";
String nextFeedTitle = "Next: Morning";
String nextFeedTime = "06:00 AM";
const unsigned long LCD_SCREEN_MS = 3000UL;
const unsigned long EMPTY_BLINK_MS = 500UL;
byte idleScreen = 0;
bool idleSequenceStarted = false;
unsigned long idlePhaseStarted = 0;
bool emptyDisplayActive = false;
unsigned long emptyDisplayStarted = 0;
bool displayBacklightOn = true;

void setDisplayBacklight(bool enabled) {
  if (enabled == displayBacklightOn) return;
  displayBacklightOn = enabled;
  if (enabled) lcd.backlight();
  else lcd.noBacklight();
}

void writeLcdLines(String first, String second) {
  first = first.substring(0, 16);
  second = second.substring(0, 16);
  if (first == lastLine1 && second == lastLine2) return;
  lastLine1 = first;
  lastLine2 = second;
  while (first.length() < 16) first += " ";
  while (second.length() < 16) second += " ";
  lcd.setCursor(0, 0); lcd.print(first);
  lcd.setCursor(0, 1); lcd.print(second);
}

void drawIdleScreen() {
  if (idleScreen == 0) {
    if (lastCompletedFeed.length() > 0) {
      writeLcdLines(lastCompletedFeed + " Feed", "Complete");
    } else {
      writeLcdLines("Feeder Ready", "Awaiting feed");
    }
  } else if (idleScreen == 1) {
    writeLcdLines(nextFeedTitle, nextFeedTime);
  } else {
    writeLcdLines("Container Level:", currentDistanceCm < 0
      ? String("No sensor echo") : String(currentDistanceCm, 1) + " cm");
  }
}

void renderIdleSequence() {
  static unsigned long lastDraw = 0;
  unsigned long now = millis();
  bool changed = false;
  if (!idleSequenceStarted) {
    idleSequenceStarted = true;
    idleScreen = 0;
    idlePhaseStarted = now;
    changed = true;
  }
  if (now - idlePhaseStarted >= LCD_SCREEN_MS) {
    idleScreen = (idleScreen + 1) % 3;
    idlePhaseStarted = now;
    changed = true;
  }
  if (changed || now - lastDraw >= SENSOR_INTERVAL) {
    drawIdleScreen();
    lastDraw = now;
  }
}

void renderFeederLcd() {
  unsigned long now = millis();
  if (lcdTestActive && now - lcdTestStarted >= 1500UL) lcdTestActive = false;
  if ((feedingState == "COMPLETE" || feedingState == "FAILED") &&
      now - completionStarted >= 5000UL) feedingState = "";

  // Empty warning interrupts every screen, including feeding and diagnostics.
  if (hopperEmpty) {
    idleSequenceStarted = false;
    if (!emptyDisplayActive) {
      emptyDisplayActive = true;
      emptyDisplayStarted = now;
    }
    unsigned long elapsed = now - emptyDisplayStarted;
    setDisplayBacklight((elapsed / EMPTY_BLINK_MS) % 2 == 0);
    // A 16x2 cannot fit the two-line warning and distance simultaneously.
    // Alternate the refill instruction and distance, always keeping Feed Empty.
    if ((elapsed / LCD_SCREEN_MS) % 2 == 0) {
      writeLcdLines("Feed Empty", "Please Refill!");
    } else {
      writeLcdLines("Feed Empty", currentDistanceCm < 0
        ? String("No sensor echo") : String(currentDistanceCm, 1) + " cm");
    }
    return;
  }
  emptyDisplayActive = false;
  setDisplayBacklight(true);
  if (currentDistanceCm < 0) {
    idleSequenceStarted = false;
    writeLcdLines("SENSOR ERROR", "CHECK SENSOR");
  } else if (feedingState == "DISPENSING..." || feedingState == "FAILED") {
    idleSequenceStarted = false;
    writeLcdLines(feedingLabel + " FEED", feedingState);
  } else if (lcdTestActive) {
    idleSequenceStarted = false;
    writeLcdLines("HARDWARE TEST", "LCD WORKING");
  } else {
    renderIdleSequence();
  }
}

void monitoredDelay(unsigned long duration) {
  unsigned long started = millis();
  while (millis() - started < duration) {
    if (millis() - previousSensorMillis >= SENSOR_INTERVAL) {
      previousSensorMillis = millis();
      updateFeedHopper();
    }
    renderFeederLcd();
    delay(1);
  }
}

// ==================================================
// SETUP
// ==================================================


void setup() {

  Serial.begin(9600);
  Serial.setTimeout(100);
  // Bound heap allocations for the existing display state.
  idleLine1.reserve(16); idleLine2.reserve(16);
  feedingLabel.reserve(10); feedingState.reserve(16);
  lastLine1.reserve(16); lastLine2.reserve(16);
  lastCompletedFeed.reserve(10); nextFeedTitle.reserve(16); nextFeedTime.reserve(16);

  // LCD
  Wire.begin();
#if defined(WIRE_HAS_TIMEOUT)
  Wire.setWireTimeout(25000UL, true); // A faulty LCD/I2C bus must not hang serial.
#endif
  lcd.init();
  lcd.backlight();
  lcd.clear();

  // Servo
  feederServo.attach(SERVO_PIN);
  feederServo.write(SERVO_STOP);

  // LEDs + buzzer
  pinMode(BUZZER_PIN, OUTPUT);

  pinMode(RED_WARNING_LED, OUTPUT);
  pinMode(MORNING_LED, OUTPUT);
  pinMode(AFTERNOON_LED, OUTPUT);
  pinMode(NIGHT_LED, OUTPUT);

  // Ultrasonic
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  digitalWrite(TRIG_PIN, LOW);

  turnOffAllLEDs();
  noTone(BUZZER_PIN);

  lcd.setCursor(0, 0);
  lcd.print(F("FEEDER READY"));

  lcd.setCursor(0, 1);
  lcd.print(F("WAITING FOR APP"));

  Serial.println(F("ARDUINO_READY"));
}


// ==================================================
// MAIN LOOP
// ==================================================

void loop() {
  if (millis() - previousSensorMillis >= SENSOR_INTERVAL) {
    previousSensorMillis = millis();
    updateFeedHopper();
  }
  renderFeederLcd();

  // Read without waiting for a timeout or allocating an unbounded String.
  static char received[64];
  static byte receivedLength = 0;
  static bool overflow = false;
  while (Serial.available() > 0) {
    char ch = Serial.read();
    if (ch == '\r' || ch == '\n') {
      if (overflow) Serial.println(F("ERROR:COMMAND_TOO_LONG"));
      else if (receivedLength > 0) {
        received[receivedLength] = '\0';
        String command(received);
        command.trim();
        command.toUpperCase();
        processCommand(command);
      }
      receivedLength = 0;
      overflow = false;
    } else if (!overflow) {
      if (receivedLength < sizeof(received) - 1) received[receivedLength++] = ch;
      else overflow = true;
    }
  }
}


// ==================================================
// PROCESS WEB/PYTHON COMMANDS
// ==================================================

void processCommand(String command) {
  if ((strncmp_P(command.c_str(), PSTR("CALIBRATE:"), sizeof("CALIBRATE:") - 1) == 0)) {
    String values = command.substring(10);
    const char *start = values.c_str();
    char *end;
    float full = strtod(start, &end);
    if (end == start || *end != ',') { Serial.println(F("ERROR:CALIBRATION")); return; }
    start = end + 1;
    float empty = strtod(start, &end);
    if (end == start || *end != '\0' || !isfinite(full) || !isfinite(empty) ||
        full < 0 || empty < 0.1 || empty <= full || empty > 500) {
      Serial.println(F("ERROR:CALIBRATION")); return;
    }
    FULL_DISTANCE_CM = full;
    EMPTY_DISTANCE_CM = empty;
    updateFeedHopper();
    Serial.println(F("CALIBRATION_OK"));
    return;
  }
  if ((strncmp_P(command.c_str(), PSTR("LCD_IDLE:"), sizeof("LCD_IDLE:") - 1) == 0)) {
    int separator = command.indexOf('|', 9);
    if (separator < 0) { Serial.println(F("ERROR:LCD_FORMAT")); return; }
    idleLine1 = command.substring(9, separator).substring(0, 16);
    idleLine2 = command.substring(separator + 1).substring(0, 16);
    // Use the actual next feeding supplied by the saved dashboard schedule.
    nextFeedTitle = idleLine1;
    nextFeedTime = idleLine2.startsWith("AT ") ? idleLine2.substring(3) : idleLine2;
    if (idleLine1 == "ALL FEEDS DONE" && idleLine2.startsWith("NEXT: TOM ")) {
      nextFeedTitle = "Next: Morning";
      nextFeedTime = "Tom: " + idleLine2.substring(10);
    } else if (nextFeedTime.startsWith("TOM ")) {
      nextFeedTime = "Tom: " + nextFeedTime.substring(4);
    }
    if (lastCompletedFeed.length() > 0 && !idleLine2.startsWith("TOM ") && !idleLine2.startsWith("NEXT: TOM ")) {
      String upperLine1 = idleLine1;
      upperLine1.toUpperCase();
      String upperLast = lastCompletedFeed;
      upperLast.toUpperCase();
      if (upperLine1.indexOf(upperLast) >= 0) {
        lastCompletedFeed = "";
      }
    }
    renderFeederLcd();
    Serial.println(F("LCD_OK"));
    return;
  }
  if ((strncmp_P(command.c_str(), PSTR("LCD_ACTIVE:"), sizeof("LCD_ACTIVE:") - 1) == 0) || (strncmp_P(command.c_str(), PSTR("LCD_DONE:"), sizeof("LCD_DONE:") - 1) == 0) ||
      (strncmp_P(command.c_str(), PSTR("LCD_FAIL:"), sizeof("LCD_FAIL:") - 1) == 0)) {
    feedingLabel = command.substring(command.indexOf(':') + 1, command.length());
    feedingLabel = feedingLabel.substring(0, 10);
    feedingState = (strncmp_P(command.c_str(), PSTR("LCD_ACTIVE:"), sizeof("LCD_ACTIVE:") - 1) == 0) ? "DISPENSING..." :
                   (strncmp_P(command.c_str(), PSTR("LCD_DONE:"), sizeof("LCD_DONE:") - 1) == 0) ? "COMPLETE" : "FAILED";
    if ((strncmp_P(command.c_str(), PSTR("LCD_DONE:"), sizeof("LCD_DONE:") - 1) == 0)) {
      // Completion comes from the feeder, never from a display timer.
      if (feedingLabel.indexOf("MORNING") >= 0) {
        lastCompletedFeed = "Morning";
        nextFeedTitle = "Next: Afternoon";
        nextFeedTime = "12:00 PM";
      } else if (feedingLabel.indexOf("AFTERNOON") >= 0) {
        lastCompletedFeed = "Afternoon";
        nextFeedTitle = "Next: Evening";
        nextFeedTime = "06:00 PM";
      } else if (feedingLabel.indexOf("EVENING") >= 0 || feedingLabel.indexOf("NIGHT") >= 0) {
        lastCompletedFeed = "Evening";
        nextFeedTitle = "Next: Morning";
        nextFeedTime = "Tom: 06:00 AM";
      } else {
        lastCompletedFeed = feedingLabel;
      }
      idleSequenceStarted = false;
    }
    completionStarted = millis();
    renderFeederLcd();
    Serial.println(F("LCD_OK"));
    return;
  }
  if (hopperEmpty && ((strcmp_P(command.c_str(), PSTR("RED_OFF")) == 0) || (strcmp_P(command.c_str(), PSTR("BUZZER_OFF")) == 0) ||
      (strcmp_P(command.c_str(), PSTR("ALL_LED_OFF")) == 0) || (strcmp_P(command.c_str(), PSTR("LCD_TEST")) == 0))) {
    if ((strcmp_P(command.c_str(), PSTR("ALL_LED_OFF")) == 0)) {
      digitalWrite(MORNING_LED, LOW);
      digitalWrite(AFTERNOON_LED, LOW);
      digitalWrite(NIGHT_LED, LOW);
    }
    Serial.println(F("ALARM_PROTECTED"));
    return;
  }



  // ------------------------------------------------
  // MORNING / BLUE LED
  // ------------------------------------------------

  if ((strcmp_P(command.c_str(), PSTR("MORNING_ON")) == 0)) {

    digitalWrite(MORNING_LED, HIGH);

    Serial.println(F("MORNING_LED_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("MORNING_OFF")) == 0)) {

    digitalWrite(MORNING_LED, LOW);

    Serial.println(F("MORNING_LED_OFF"));
  }


  // ------------------------------------------------
  // AFTERNOON / GREEN LED
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("AFTERNOON_ON")) == 0)) {

    digitalWrite(AFTERNOON_LED, HIGH);

    Serial.println(F("AFTERNOON_LED_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("AFTERNOON_OFF")) == 0)) {

    digitalWrite(AFTERNOON_LED, LOW);

    Serial.println(F("AFTERNOON_LED_OFF"));
  }


  // ------------------------------------------------
  // NIGHT / YELLOW LED
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("NIGHT_ON")) == 0)) {

    digitalWrite(NIGHT_LED, HIGH);

    Serial.println(F("NIGHT_LED_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("NIGHT_OFF")) == 0)) {

    digitalWrite(NIGHT_LED, LOW);

    Serial.println(F("NIGHT_LED_OFF"));
  }


  // ------------------------------------------------
  // RED WARNING LED
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("RED_ON")) == 0)) {

    digitalWrite(RED_WARNING_LED, HIGH);

    Serial.println(F("RED_LED_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("RED_OFF")) == 0)) {

    digitalWrite(RED_WARNING_LED, LOW);

    Serial.println(F("RED_LED_OFF"));
  }


  // ------------------------------------------------
  // BUZZER
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("BUZZER_ON")) == 0)) {

    tone(
      BUZZER_PIN,
      BUZZER_FREQUENCY
    );

    Serial.println(F("BUZZER_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("BUZZER_OFF")) == 0)) {

    noTone(BUZZER_PIN);

    Serial.println(F("BUZZER_OFF"));
  }


  // ------------------------------------------------
  // SERVO
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("SERVO_ROTATE")) == 0)) {

    feederServo.write(SERVO_ROTATE);

    Serial.println(F("SERVO_ROTATING"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("SERVO_STOP")) == 0)) {

    feederServo.write(SERVO_STOP);

    Serial.println(F("SERVO_STOPPED"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("SERVO_TEST")) == 0)) {

    Serial.println(F("SERVO_TEST_START"));

    feederServo.write(SERVO_ROTATE);

    monitoredDelay(3000);

    feederServo.write(SERVO_STOP);

    Serial.println(F("SERVO_TEST_COMPLETE"));
  }


  // ------------------------------------------------
  // ULTRASONIC
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("DISTANCE")) == 0)) {

    float distance = measureDistance();

    Serial.print(F("DISTANCE:"));

    if (distance < 0) Serial.println(F("ERROR"));
    else { Serial.print(distance, 1); Serial.println(F("CM")); }
  }


  // ------------------------------------------------
  // LCD TEST
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("LCD_TEST")) == 0)) {
    // Temporary screen: the normal display resumes without another command.
    lcdTestActive = true;
    lcdTestStarted = millis();
    renderFeederLcd();
    Serial.println(F("LCD_TEST_OK"));
  }

  // ------------------------------------------------
  // ALL LEDs
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("ALL_LED_ON")) == 0)) {

    digitalWrite(MORNING_LED, HIGH);
    digitalWrite(AFTERNOON_LED, HIGH);
    digitalWrite(NIGHT_LED, HIGH);
    digitalWrite(RED_WARNING_LED, HIGH);

    Serial.println(F("ALL_LED_ON"));
  }

  else if ((strcmp_P(command.c_str(), PSTR("ALL_LED_OFF")) == 0)) {

    turnOffAllLEDs();

    Serial.println(F("ALL_LED_OFF"));
  }


  // ------------------------------------------------
  // SYSTEM STATUS
  // ------------------------------------------------

  else if ((strcmp_P(command.c_str(), PSTR("PING")) == 0)) {

    Serial.println(F("ARDUINO_CONNECTED"));
  }


  // ------------------------------------------------
  // UNKNOWN COMMAND
  // ------------------------------------------------

  else {

    Serial.print(F("UNKNOWN_COMMAND:"));

    Serial.println(command);
  }
}


// ==================================================
// ULTRASONIC DISTANCE
// ==================================================

void updateFeedHopper() {
  currentDistanceCm = measureDistance();
  if (currentDistanceCm < 0) {
    // A missing echo does not clear an existing empty alarm.
    renderFeederLcd();
    Serial.println(F("DISTANCE:ERROR"));
    Serial.println(F("SENSOR_ERROR"));
    return;
  }
  hopperEmpty = currentDistanceCm >= EMPTY_DISTANCE_CM;
  currentFeedPercentage = constrain(
    (EMPTY_DISTANCE_CM - currentDistanceCm) /
    (EMPTY_DISTANCE_CM - FULL_DISTANCE_CM) * 100.0, 0.0, 100.0);
  if (hopperEmpty) {
    currentFeedPercentage = 0;
    tone(BUZZER_PIN, BUZZER_FREQUENCY);
    digitalWrite(RED_WARNING_LED, HIGH);
  } else {
    noTone(BUZZER_PIN);
    digitalWrite(RED_WARNING_LED, LOW);
  }
  renderFeederLcd();
  Serial.print(F("DISTANCE:")); Serial.print(currentDistanceCm, 1); Serial.println(F("CM"));
  Serial.print(F("FEED_LEVEL:")); Serial.print(currentFeedPercentage, 0); Serial.println(F("%"));
  Serial.println(hopperEmpty ? F("FEED_STATUS:EMPTY") : F("FEED_STATUS:AVAILABLE"));
}


float measureDistance() {

  digitalWrite(TRIG_PIN, LOW);

  delayMicroseconds(2);

  digitalWrite(TRIG_PIN, HIGH);

  delayMicroseconds(10);

  digitalWrite(TRIG_PIN, LOW);


  unsigned long echoDuration =
    pulseIn(
      ECHO_PIN,
      HIGH,
      30000UL
    );


  if (echoDuration == 0) {

    return -1;
  }


  float distance =
    echoDuration * 0.0343 / 2.0;

  return distance;
}


// ==================================================
// TURN OFF LEDs
// ==================================================

void turnOffAllLEDs() {

  digitalWrite(
    MORNING_LED,
    LOW
  );

  digitalWrite(
    AFTERNOON_LED,
    LOW
  );

  digitalWrite(
    NIGHT_LED,
    LOW
  );

  digitalWrite(
    RED_WARNING_LED,
    LOW
  );
}