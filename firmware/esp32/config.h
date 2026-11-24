#ifndef CONFIG_H
#define CONFIG_H

// Wi-Fi Access Point Credentials
#define WIFI_SSID "Your_WiFi_SSID"
#define WIFI_PASSWORD "Your_WiFi_Password"

// OmniSense Mosquitto MQTT Broker Configuration
#define MQTT_BROKER_HOST "192.168.1.100"
#define MQTT_BROKER_PORT 1883
#define MQTT_USERNAME "omnisense_user"
#define MQTT_PASSWORD "omnisense_pass"

// Device Identity
#define DEVICE_ID "esp32-env-01"

// Telemetry Timing
#define PUBLISH_INTERVAL_MS 2000

#endif // CONFIG_H
