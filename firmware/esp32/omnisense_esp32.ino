/*
 * OmniSense AI - ESP32 Firmware
 * Multi-sensor station publishing over Wi-Fi and MQTT.
 * Sensors: DHT22 (Temp/Humidity), MQ-2 (Gas), PIR (Motion).
 *
 * Pin Table:
 * - DHT22: GPIO 4
 * - MQ-2 Analog: GPIO 34 (ADC1_CH6 - Input only, 3.3V ADC)
 * - PIR Motion: GPIO 27
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include "config.h"

#define DHTPIN 4
#define DHTTYPE DHT22
#define MQ2_PIN 34
#define PIR_PIN 27

DHT dht(DHTPIN, DHTTYPE);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastMsg = 0;

void setupWifi() {
  delay(10);
  Serial.printf("\nConnecting to Wi-Fi SSID: %s\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWi-Fi Connected!");
  Serial.printf("IP Address: %s\n", WiFi.localIP().toString().c_str());
}

void reconnectMqtt() {
  while (!mqttClient.connected()) {
    Serial.print("Connecting to MQTT broker...");
    String clientId = "ESP32Client-" + String(DEVICE_ID);

    bool connected;
    if (strlen(MQTT_USERNAME) > 0) {
      connected = mqttClient.connect(clientId.c_str(), MQTT_USERNAME, MQTT_PASSWORD);
    } else {
      connected = mqttClient.connect(clientId.c_str());
    }

    if (connected) {
      Serial.println(" Connected!");
      // Publish online status
      char statusTopic[128];
      snprintf(statusTopic, sizeof(statusTopic), "omnisense/devices/%s/status", DEVICE_ID);
      char statusPayload[256];
      snprintf(statusPayload, sizeof(statusPayload),
        "{\"device_id\":\"%s\",\"status\":\"online\",\"ip\":\"%s\"}",
        DEVICE_ID, WiFi.localIP().toString().c_str());
      mqttClient.publish(statusTopic, statusPayload, true);
    } else {
      Serial.printf(" Failed, rc=%d. Retrying in 5 seconds...\n", mqttClient.state());
      delay(5000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  dht.begin();

  setupWifi();
  mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
}

void loop() {
  if (!mqttClient.connected()) {
    reconnectMqtt();
  }
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastMsg > PUBLISH_INTERVAL_MS) {
    lastMsg = now;

    // Read sensors
    float h = dht.readHumidity();
    float t = dht.readTemperature();
    int rawGas = analogRead(MQ2_PIN);
    float gasPpm = (rawGas / 4095.0) * 1000.0; // ESP32 12-bit ADC
    bool motion = (digitalRead(PIR_PIN) == HIGH);

    if (isnan(h)) h = 0.0;
    if (isnan(t)) t = 0.0;

    // Format JSON
    char payload[256];
    snprintf(payload, sizeof(payload),
      "{\"device_id\":\"%s\",\"temperature\":%.1f,\"humidity\":%.1f,\"gas_level\":%.1f,\"motion\":%s}",
      DEVICE_ID, t, h, gasPpm, motion ? "true" : "false");

    char topic[128];
    snprintf(topic, sizeof(topic), "omnisense/devices/%s/telemetry", DEVICE_ID);

    mqttClient.publish(topic, payload);
    Serial.printf("Published -> %s: %s\n", topic, payload);
  }
}
