# Arduino Uno Q Firmware & Hardware Documentation

## Hardware Pinout Table

| Sensor Component | Sensor Pin | Arduino Pin | Voltage Requirement | Protection Needed |
| :--- | :--- | :--- | :--- | :--- |
| **DHT22** | VCC | 3.3V | 3.3V | None |
| **DHT22** | DATA | D4 | 3.3V Logic | 10k $\Omega$ pull-up to 3.3V |
| **DHT22** | GND | GND | 0V | Ground |
| **MQ-2 Gas** | VCC | 5.0V | 5.0V (Heater) | Connect to 5V rail |
| **MQ-2 Gas** | AOUT | A0 | 0-3.3V Max | **2-Resistor Voltage Divider (Mandatory)** |
| **MQ-2 Gas** | GND | GND | 0V | Common Ground |
| **PIR Motion** | VCC | 5.0V / 3.3V | 3.3V - 5V | None |
| **PIR Motion** | OUT | D2 | 3.3V Logic | None (PIR output is 3.3V logic) |
| **PIR Motion** | GND | GND | 0V | Common Ground |

---

## 3.3V ADC Safety Notice for MQ-2

> [!CAUTION]
> The MQ-2 internal heater requires **5.0V**. Under high concentrations of gas or smoke, the analog output voltage ($V_{out}$) can exceed 4.5V. If you feed this directly to a 3.3V microcontroller ADC, **it will permanently fry the MCU input pin**.

### Voltage Divider Wiring
Use a 10k $\Omega$ ($R_1$) and 20k $\Omega$ ($R_2$) resistor pair:
```
MQ-2 AOUT pin ─────── [ 10k Ohm (R1) ] ───────┬───────> To Arduino Pin A0
                                              │
                                       [ 20k Ohm (R2) ]
                                              │
                                             GND
```
$$\text{Max Voltage to A0} = 5.0\text{V} \times \left(\frac{20\text{k}\Omega}{10\text{k}\Omega + 20\text{k}\Omega}\right) = 3.33\text{V}$$

---

## Arduino Uno Q Architecture Verification Callout

> [!IMPORTANT]
> **VERIFICATION REQUIRED**:
> The Arduino Uno Q features a dual-core architecture (MCU + embedded Linux processor). Communication between the MCU and Linux environment depends on the installed Linux image (e.g. `/dev/ttyATH0`, `/dev/ttyS0`, or the `Bridge` library API).
> - Refer to the official [Arduino Uno Documentation](https://docs.arduino.cc/) for your specific revision to confirm the exact UART serial node.
