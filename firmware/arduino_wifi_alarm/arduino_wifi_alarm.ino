/*
 * OmniSense AI - Wireless Wi-Fi Alarm Node (ESP32 / ESP8266 / Arduino Uno R4 WiFi)
 * 
 * Functions:
 * 1. Connects to your Home/Mobile Wi-Fi network.
 * 2. Continuously monitors OmniSense AI backend over HTTP GET:
 *    http://192.168.90.190:8000/api/devices/alarm
 * 3. When Threat / Weapon is detected by the AI camera, or 'Test Alarm' is clicked:
 *    - Activates Red Threat Strobe LED (Pin 13 & Pin 8)
 * 4. Completely wireless! No USB cable needed for data.
 */

#if defined(ESP8266)
  #include <ESP8266WiFi.h>
  #include <ESP8266HTTPClient.h>
#elif defined(ESP32)
  #include <WiFi.h>
  #include <HTTPClient.h>
#else
  #include <WiFiS3.h> // Arduino Uno R4 WiFi
#endif

// ==========================================
// Wi-Fi Configuration (Enter your Wi-Fi details)
// ==========================================
const char* WIFI_SSID = "YOUR_WIFI_NAME";       // Aapke Wi-Fi / Hotspot ka naam
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"; // Wi-Fi ka password

// Laptop Server IP (OmniSense AI backend running on your laptop)
const char* ALARM_API_URL = "http://192.168.90.190:8000/api/devices/alarm";

const int RED_LED_PIN = 13;      // Built-in Board LED (Pin 13)
const int EXTERNAL_ALARM_PIN = 8; // External Red Alert LED / Buzzer (Pin 8)

bool alarmState = false;
unsigned long lastPollTime = 0;
const unsigned long POLL_INTERVAL_MS = 400; // Check every 400ms

void setup() {
  Serial.begin(115200);
  pinMode(RED_LED_PIN, OUTPUT);
  pinMode(EXTERNAL_ALARM_PIN, OUTPUT);
  digitalWrite(RED_LED_PIN, LOW);
  digitalWrite(EXTERNAL_ALARM_PIN, LOW);

  Serial.println("\n==================================");
  Serial.println("OmniSense AI - Wi-Fi Alarm Receiver");
  Serial.println("==================================");

  Serial.print("Connecting to Wi-Fi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    digitalWrite(RED_LED_PIN, !digitalRead(RED_LED_PIN)); // Blink while connecting
  }

  digitalWrite(RED_LED_PIN, LOW);
  Serial.println("\n✓ Wi-Fi Connected!");
  Serial.print("Arduino IP: ");
  Serial.println(WiFi.localIP());
  Serial.println("Listening for Threat Alarms from Laptop...");
}

void loop() {
  unsigned long now = millis();

  // Poll OmniSense Laptop API every 400ms
  if (now - lastPollTime >= POLL_INTERVAL_MS) {
    lastPollTime = now;

    if (WiFi.status() == WL_CONNECTED) {
      WiFiClient client;
      HTTPClient http;

      if (http.begin(client, ALARM_API_URL)) {
        int httpCode = http.GET();
        if (httpCode == HTTP_CODE_OK) {
          String payload = http.getString();
          // Check if alarm_active is true in JSON
          if (payload.indexOf("\"alarm_active\":true") >= 0) {
            alarmState = true;
          } else {
            alarmState = false;
          }
        }
        http.end();
      }
    }
  }

  // Handle Alarm Output (Rapid Strobe Blinking when threat is active)
  if (alarmState) {
    digitalWrite(RED_LED_PIN, HIGH);
    digitalWrite(EXTERNAL_ALARM_PIN, HIGH);
    delay(120);
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(EXTERNAL_ALARM_PIN, LOW);
    delay(120);
  } else {
    digitalWrite(RED_LED_PIN, LOW);
    digitalWrite(EXTERNAL_ALARM_PIN, LOW);
  }
}
