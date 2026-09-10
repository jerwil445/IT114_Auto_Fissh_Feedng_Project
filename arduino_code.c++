// Based on the Arduino IDE sketch supplied by you.
// Python sends LCD_IDLE:NEXT: MORNING|AT 08:00 AM for the scheduled time.
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Servo.h>

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

const float FULL_DISTANCE_CM = 3.0;

// The feed hopper is empty at 20 cm or greater.
const float EMPTY_DISTANCE_CM = 20.0;

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

void renderFeederLcd() {
  if (lcdTestActive && millis() - lcdTestStarted >= 1500UL) {
    lcdTestActive = false;
  }
  if ((feedingState == "COMPLETE" || feedingState == "FAILED") &&
      millis() - completionStarted >= 5000UL) feedingState = "";
  if (hopperEmpty) {
    writeLcdLines("FEED EMPTY", "PLEASE REFILL");
  } else if (currentDistanceCm < 0) {
    writeLcdLines("SENSOR ERROR", "CHECK SENSOR");
  } else if (feedingState.length() > 0) {
    writeLcdLines(feedingLabel + " FEED", feedingState);
  } else if (lcdTestActive) {
    writeLcdLines("HARDWARE TEST", "LCD WORKING");
  } else {
    writeLcdLines(idleLine1, idleLine2);
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

  // LCD
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
  lcd.print("FEEDER READY");

  lcd.setCursor(0, 1);
  lcd.print("WAITING FOR APP");

  Serial.println("ARDUINO_READY");
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

  if (Serial.available() > 0) {

    String command = Serial.readStringUntil('\n');
    command.trim();
    command.toUpperCase();

    processCommand(command);
  }
}


// ==================================================
// PROCESS WEB/PYTHON COMMANDS
// ==================================================

void processCommand(String command) {
  if (command.startsWith("LCD_IDLE:")) {
    int separator = command.indexOf('|', 9);
    if (separator < 0) { Serial.println("ERROR:LCD_FORMAT"); return; }
    idleLine1 = command.substring(9, separator);
    idleLine2 = command.substring(separator + 1);
    renderFeederLcd();
    Serial.println("LCD_OK");
    return;
  }
  if (command.startsWith("LCD_ACTIVE:") || command.startsWith("LCD_DONE:") ||
      command.startsWith("LCD_FAIL:")) {
    feedingLabel = command.substring(command.indexOf(':') + 1, command.length());
    feedingLabel = feedingLabel.substring(0, 10);
    feedingState = command.startsWith("LCD_ACTIVE:") ? "DISPENSING..." :
                   command.startsWith("LCD_DONE:") ? "COMPLETE" : "FAILED";
    completionStarted = millis();
    renderFeederLcd();
    Serial.println("LCD_OK");
    return;
  }
  if (hopperEmpty && (command == "RED_OFF" || command == "BUZZER_OFF" ||
      command == "ALL_LED_OFF" || command == "LCD_TEST")) {
    if (command == "ALL_LED_OFF") {
      digitalWrite(MORNING_LED, LOW);
      digitalWrite(AFTERNOON_LED, LOW);
      digitalWrite(NIGHT_LED, LOW);
    }
    Serial.println("ALARM_PROTECTED");
    return;
  }



  // ------------------------------------------------
  // MORNING / BLUE LED
  // ------------------------------------------------

  if (command == "MORNING_ON") {

    digitalWrite(MORNING_LED, HIGH);

    Serial.println("MORNING_LED_ON");
  }

  else if (command == "MORNING_OFF") {

    digitalWrite(MORNING_LED, LOW);

    Serial.println("MORNING_LED_OFF");
  }


  // ------------------------------------------------
  // AFTERNOON / GREEN LED
  // ------------------------------------------------

  else if (command == "AFTERNOON_ON") {

    digitalWrite(AFTERNOON_LED, HIGH);

    Serial.println("AFTERNOON_LED_ON");
  }

  else if (command == "AFTERNOON_OFF") {

    digitalWrite(AFTERNOON_LED, LOW);

    Serial.println("AFTERNOON_LED_OFF");
  }


  // ------------------------------------------------
  // NIGHT / YELLOW LED
  // ------------------------------------------------

  else if (command == "NIGHT_ON") {

    digitalWrite(NIGHT_LED, HIGH);

    Serial.println("NIGHT_LED_ON");
  }

  else if (command == "NIGHT_OFF") {

    digitalWrite(NIGHT_LED, LOW);

    Serial.println("NIGHT_LED_OFF");
  }


  // ------------------------------------------------
  // RED WARNING LED
  // ------------------------------------------------

  else if (command == "RED_ON") {

    digitalWrite(RED_WARNING_LED, HIGH);

    Serial.println("RED_LED_ON");
  }

  else if (command == "RED_OFF") {

    digitalWrite(RED_WARNING_LED, LOW);

    Serial.println("RED_LED_OFF");
  }


  // ------------------------------------------------
  // BUZZER
  // ------------------------------------------------

  else if (command == "BUZZER_ON") {

    tone(
      BUZZER_PIN,
      BUZZER_FREQUENCY
    );

    Serial.println("BUZZER_ON");
  }

  else if (command == "BUZZER_OFF") {

    noTone(BUZZER_PIN);

    Serial.println("BUZZER_OFF");
  }


  // ------------------------------------------------
  // SERVO
  // ------------------------------------------------

  else if (command == "SERVO_ROTATE") {

    feederServo.write(SERVO_ROTATE);

    Serial.println("SERVO_ROTATING");
  }

  else if (command == "SERVO_STOP") {

    feederServo.write(SERVO_STOP);

    Serial.println("SERVO_STOPPED");
  }

  else if (command == "SERVO_TEST") {

    Serial.println("SERVO_TEST_START");

    feederServo.write(SERVO_ROTATE);

    monitoredDelay(3000);

    feederServo.write(SERVO_STOP);

    Serial.println("SERVO_TEST_COMPLETE");
  }


  // ------------------------------------------------
  // ULTRASONIC
  // ------------------------------------------------

  else if (command == "DISTANCE") {

    float distance = measureDistance();

    Serial.print("DISTANCE:");

    Serial.println(distance);
  }


  // ------------------------------------------------
  // LCD TEST
  // ------------------------------------------------

  else if (command == "LCD_TEST") {
    // Temporary screen: the normal display resumes without another command.
    lcdTestActive = true;
    lcdTestStarted = millis();
    renderFeederLcd();
    Serial.println("LCD_TEST_OK");
  }

  // ------------------------------------------------
  // ALL LEDs
  // ------------------------------------------------

  else if (command == "ALL_LED_ON") {

    digitalWrite(MORNING_LED, HIGH);
    digitalWrite(AFTERNOON_LED, HIGH);
    digitalWrite(NIGHT_LED, HIGH);
    digitalWrite(RED_WARNING_LED, HIGH);

    Serial.println("ALL_LED_ON");
  }

  else if (command == "ALL_LED_OFF") {

    turnOffAllLEDs();

    Serial.println("ALL_LED_OFF");
  }


  // ------------------------------------------------
  // SYSTEM STATUS
  // ------------------------------------------------

  else if (command == "PING") {

    Serial.println("ARDUINO_CONNECTED");
  }


  // ------------------------------------------------
  // UNKNOWN COMMAND
  // ------------------------------------------------

  else {

    Serial.print("UNKNOWN_COMMAND:");

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
    Serial.println("DISTANCE:ERROR");
    Serial.println("SENSOR_ERROR");
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
  Serial.print("DISTANCE:"); Serial.print(currentDistanceCm, 1); Serial.println("CM");
  Serial.print("FEED_LEVEL:"); Serial.print(currentFeedPercentage, 0); Serial.println("%");
  Serial.println(hopperEmpty ? "FEED_STATUS:EMPTY" : "FEED_STATUS:AVAILABLE");
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