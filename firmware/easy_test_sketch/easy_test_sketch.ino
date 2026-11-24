/*
 * OmniSense AI - Arduino Firmware with Bi-Directional Threat Alarm
 * 
 * Hardware Output:
 * - Pin 13: Built-in Board LED (Strobes rapidly when Threat Alarm is active)
 * - Pin 8: External Red Alert LED or Piezo Buzzer
 * 
 * Capabilities:
 * - Sends simulated / real sensor telemetry (Temp, Gas, Motion) every 2s
 * - Listens for incoming Serial commands:
 *     "ALARM:ON"  -> Activates flashing Red Threat LED and Alarm
 *     "ALARM:OFF" -> Returns to normal standby mode
 */

const int BUILTIN_LED_PIN = 13;
const int EXTERNAL_ALARM_PIN = 8;

bool alarmActive = false;
unsigned long lastTelemetryTime = 0;
unsigned long lastStrobeTime = 0;
bool strobeState = false;

void setup() {
  Serial.begin(9600);
  pinMode(BUILTIN_LED_PIN, OUTPUT);
  pinMode(EXTERNAL_ALARM_PIN, OUTPUT);
  digitalWrite(BUILTIN_LED_PIN, LOW);
  digitalWrite(EXTERNAL_ALARM_PIN, LOW);
}

void loop() {
  unsigned long now = millis();

  // 1. Check for incoming commands from OmniSense Python Bridge
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.indexOf("ALARM:ON") >= 0 || cmd.indexOf("\"alarm\":true") >= 0 || cmd.indexOf("\"state\":\"ON\"") >= 0) {
      alarmActive = true;
    } else if (cmd.indexOf("ALARM:OFF") >= 0 || cmd.indexOf("\"alarm\":false") >= 0 || cmd.indexOf("\"state\":\"OFF\"") >= 0) {
      alarmActive = false;
      digitalWrite(BUILTIN_LED_PIN, LOW);
      digitalWrite(EXTERNAL_ALARM_PIN, LOW);
    }
  }

  // 2. Handle Alarm Strobe (150ms rapid blinking)
  if (alarmActive) {
    if (now - lastStrobeTime >= 150) {
      lastStrobeTime = now;
      strobeState = !strobeState;
      digitalWrite(BUILTIN_LED_PIN, strobeState ? HIGH : LOW);
      digitalWrite(EXTERNAL_ALARM_PIN, strobeState ? HIGH : LOW);
    }
  } else {
    digitalWrite(BUILTIN_LED_PIN, LOW);
    digitalWrite(EXTERNAL_ALARM_PIN, LOW);
  }

  // 3. Send Telemetry every 2 seconds
  if (now - lastTelemetryTime >= 2000) {
    lastTelemetryTime = now;
    
    // Replace with real DHT22 or MQ-2 readings when wired
    float temp = 25.0 + (random(0, 40) / 10.0);
    float hum = 50.0 + (random(0, 80) / 10.0);
    int gas = 120 + random(0, 40);
    int motion = random(0, 2);

    Serial.print("{\"temperature\":");
    Serial.print(temp, 1);
    Serial.print(",\"humidity\":");
    Serial.print(hum, 1);
    Serial.print(",\"gas_level\":");
    Serial.print(gas);
    Serial.print(",\"motion\":");
    Serial.print(motion ? "true" : "false");
    Serial.print(",\"alarm\":");
    Serial.print(alarmActive ? "true" : "false");
    Serial.println("}");
  }
}
