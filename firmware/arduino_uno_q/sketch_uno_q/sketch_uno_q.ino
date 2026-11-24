#include <DHT.h>

/*
 * OmniSense AI - Arduino Uno Q (MCU Sketch)
 * Reads DHT22, MQ-2 (Analog), and PIR motion sensor.
 * Sends structured JSON to Linux side over Serial / Bridge.
 *
 * -------------------------------------------------------------
 * HARDWARE PIN TABLE:
 * -------------------------------------------------------------
 * Sensor  | Pin Name | Microcontroller Pin | Voltage / Logic Level
 * --------+----------+---------------------+----------------------
 * DHT22   | DATA     | Digital Pin 4 (D4)  | 3.3V (with 10k pull-up)
 * DHT22   | VCC/GND  | 3.3V / GND          | 3.3V Power
 * MQ-2    | AOUT     | Analog Pin 0 (A0)   | 0-3.3V via VOLTAGE DIVIDER!
 * MQ-2    | VCC/GND  | 5.0V / GND          | 5.0V (Heater requires 5V)
 * PIR     | OUT      | Digital Pin 2 (D2)  | 3.3V Digital Output
 * PIR     | VCC/GND  | 5.0V / GND          | 5.0V Power (3.3V out)
 *
 * -------------------------------------------------------------
 * [SAFETY CRITICAL]: 3.3V-SAFE VOLTAGE DIVIDER FOR MQ-2
 * -------------------------------------------------------------
 * MQ-2 heater requires 5V. Its analog output can reach 5.0V under high gas concentrations.
 * If connecting to a 3.3V ADC pin, DO NOT connect directly or the pin will be DAMAGED!
 * Wire a 2-resistor voltage divider:
 *
 *   MQ-2 AOUT ----[ 10k Ohm (R1) ]----+----> To Arduino A0
 *                                      |
 *                                [ 20k Ohm (R2) ]
 *                                      |
 *                                     GND
 *   Formula: Vout = Vin * (R2 / (R1 + R2)) = 5V * (20k / 30k) = 3.33V (Safe!)
 * -------------------------------------------------------------
 *
 * [VERIFICATION REQUIRED]:
 * Verify the Arduino Uno Q Bridge API implementation and Serial device node
 * against official Arduino documentation for your specific Linux distro image.
 * Depending on the board revision, communications use Serial (e.g. Serial or Serial1)
 * or the Arduino Bridge library (Bridge / Process).
 */

#define DHTPIN 4
#define DHTTYPE DHT22
#define MQ2_ANALOG_PIN A0
#define PIR_PIN 2

DHT dht(DHTPIN, DHTTYPE);

const char* DEVICE_ID = "uno-q-env-01";
unsigned long lastPublish = 0;
const unsigned long PUBLISH_INTERVAL = 2000; // 2 seconds

void setup() {
  // Serial interface connected to the Linux processor on Uno Q
  Serial.begin(115200);
  pinMode(PIR_PIN, INPUT);
  pinMode(MQ2_ANALOG_PIN, INPUT);
  dht.begin();

  delay(2000); // Warm up sensors
}

void loop() {
  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_INTERVAL) {
    lastPublish = now;

    // Read DHT22
    float humidity = dht.readHumidity();
    float temperature = dht.readTemperature();

    // Read MQ-2 (Scaled 0-1023 to estimated ppm baseline)
    int rawGas = analogRead(MQ2_ANALOG_PIN);
    // MQ-2 analog reading scaled to approximate ppm range (0 - 1000 ppm)
    float gasLevel = (rawGas / 1023.0) * 1000.0;

    // Read PIR
    bool motion = (digitalRead(PIR_PIN) == HIGH);

    // Validate sensor readings
    if (isnan(humidity)) humidity = 0.0;
    if (isnan(temperature)) temperature = 0.0;

    // Transmit JSON line to Linux side
    Serial.print("{\"device_id\":\"");
    Serial.print(DEVICE_ID);
    Serial.print("\",\"temperature\":");
    Serial.print(temperature, 1);
    Serial.print(",\"humidity\":");
    Serial.print(humidity, 1);
    Serial.print(",\"gas_level\":");
    Serial.print(gasLevel, 1);
    Serial.print(",\"motion\":");
    Serial.print(motion ? "true" : "false");
    Serial.print(",\"timestamp\":");
    Serial.print(now / 1000);
    Serial.println("}");
  }
}
