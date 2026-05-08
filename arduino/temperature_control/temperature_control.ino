/*
  Temperature Control System
  
  Multi-sensor temperature monitoring and control system with:
  - 6 DS18B20 temperature sensors
  - 2 SSR-controlled hot plates
  - 4 MOSFET-controlled DC fans
  - Serial communication with Raspberry Pi
  
  Hardware Requirements:
  - Arduino Mega 2560 (recommended)
  - DS18B20 sensors with 4.7kΩ pull-up resistor
  - SSR-40DA relays for hot plates
  - IRF540 MOSFETs for fan control
  - 24V DC fans
  
  Pin Assignments:
  - DS18B20 Data: Pin 2 (OneWire bus)
  - SSR Relays: Pins 8-9
  - MOSFET Fans: PWM Pins 3, 5, 6, 10
  - Air Flow Sensors: Analog Pins A0-A3
  - Status LED: Pin 13
  
  Created: 2025-02-25
*/

#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <SPI.h>
#include <DHT22.h>

// Pin Definitions
#define ONE_WIRE_BUS 2
#define FAN_1_PWM 3
#define FAN_2_PWM 4
#define FAN_3_PWM 5
#define FAN_4_PWM 6
#define SSR_RELAY_1 8
#define SSR_RELAY_2 9
#define FLOW_SENSOR_1 A0
#define FLOW_SENSOR_2 A1
#define FLOW_SENSOR_3 A2
#define FLOW_SENSOR_4 A3
#define STATUS_LED 13

// BME280 SPI Chip Select Pins
#define BMP280_CS_1 26  // Digital pin 22
#define BMP280_CS_2 28  // Digital pin 24
#define NUM_BMP280_SENSORS 2

// DHT Sensor Data Pins
#define DHT_PIN_1 22  // Digital pin 26
#define DHT_PIN_2 24  // Digital pin 28
#define NUM_DHT_SENSORS 2

// SPI pins for Arduino Mega (hardware SPI)
// MOSI: Pin 51
// MISO: Pin 50
// SCK: Pin 52
#define BMP_SCK 52
#define BMP_MISO 50
#define BMP_MOSI 51

// System Constants
#define NUM_SENSORS 12
#define NUM_FANS 4
#define NUM_HOT_PLATES 2
#define NUM_FLOW_SENSORS 4
#define MAX_TEMP 120.0
#define MIN_TEMP 0.0
#define UPDATE_INTERVAL 1000  // 1 seconds
#define DHT_UPDATE_INTERVAL 10000  // 10 seconds for DHT sensors

// Global Variables
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress tempDeviceAddresses[NUM_SENSORS];

// BME280 Sensors (SPI)
Adafruit_BMP280 bmp1(BMP280_CS_1), bmp2(BMP280_CS_2);  // Create 2 BME280 objects
bool bmpFound[NUM_BMP280_SENSORS] = {false, false};

// DHT Sensors (AM2302)
DHT22 dht1(DHT_PIN_1);
DHT22 dht2(DHT_PIN_2);
bool dhtFound[NUM_DHT_SENSORS] = {false, false};

// System State
float currentTemperatures[NUM_SENSORS];
float targetTemperatures[NUM_HOT_PLATES] = {35.0, 35.0};
int fanSpeeds[NUM_FANS] = {255, 255, 255, 255};
bool hotPlateStates[NUM_HOT_PLATES] = {false, false};

// BME280 Data arrays
float bmpTemperatures[NUM_BMP280_SENSORS];
float bmpPressure[NUM_BMP280_SENSORS];

// DHT Data arrays
float dhtTemperatures[NUM_DHT_SENSORS];
float dhtHumidity[NUM_DHT_SENSORS];

// Air Flow Sensor Data
float flowRatesData[NUM_FLOW_SENSORS];

// 6th Order Polynomial Coefficients for Flow Rate Conversion
// Placeholder values - replace with actual coefficients from sensor documentation
// Flow Rate = a0 + a1*V + a2*V^2 + a3*V^3 + a4*V^4 + a5*V^5 + a6*V^6
struct FlowSensorCoefficients {
  float a0, a1, a2, a3, a4, a5, a6;
};

FlowSensorCoefficients flowCoefficients[NUM_FLOW_SENSORS] = {
  {0.0, 0.0716, -0.9973, 5.4446, -14.4591, 20.0874, -10.1473},  // Flow Sensor 1
  {0.0, 0.0716, -0.9973, 5.4446, -14.4591, 20.0874, -10.1473},  // Flow Sensor 2
  {0.0, 0.0716, -0.9973, 5.4446, -14.4591, 20.0874, -10.1473},  // Flow Sensor 3
  {-2.62534, 20.87142, -68.14970, 117.16178, -111.95726, 58.03388, -12.00028}   // Flow Sensor 4
};

unsigned long lastUpdateTime = 0;
unsigned long lastDHTUpdateTime = 0;
bool systemReady = false;

// PID Variables (simplified)
float kp = 2.0, ki = 0.5, kd = 1.0;
float integral[NUM_HOT_PLATES] = {0, 0};
float previousError[NUM_HOT_PLATES] = {0, 0};

void setup() {
  Serial.begin(1000000);
  while (!Serial) delay(10);
  
  // Initialize pins
  pinMode(SSR_RELAY_1, OUTPUT);
  pinMode(SSR_RELAY_2, OUTPUT);
  pinMode(FAN_1_PWM, OUTPUT);
  pinMode(FAN_2_PWM, OUTPUT);
  pinMode(FAN_3_PWM, OUTPUT);
  pinMode(FAN_4_PWM, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);
  
  // Initialize outputs to safe state
  digitalWrite(SSR_RELAY_1, LOW);
  digitalWrite(SSR_RELAY_2, LOW);
  analogWrite(FAN_1_PWM, 255);
  analogWrite(FAN_2_PWM, 255);
  analogWrite(FAN_3_PWM, 255);
  analogWrite(FAN_4_PWM, 255);
  
  // Initialize temperature sensors
  sensors.begin();
  sensors.setWaitForConversion(true);
  
  // Set hardcoded sensor addresses
  // Sensor 1 address: 28616434892D9476
  // Sensor 5 address: 28616434C20D6890  
  // Sensor 3 address: 28616434C951B1A0
  // Sensor 2 address: 286164348927DEA9
  // Sensor 4 address: 28616434CDBEBB2D
  
  // Convert hex strings to DeviceAddress arrays
  // Sensor 1: 28616434892D9476
  tempDeviceAddresses[0][0] = 0x28; tempDeviceAddresses[0][1] = 0x61; tempDeviceAddresses[0][2] = 0x64; tempDeviceAddresses[0][3] = 0x34;
  tempDeviceAddresses[0][4] = 0x89; tempDeviceAddresses[0][5] = 0x2D; tempDeviceAddresses[0][6] = 0x94; tempDeviceAddresses[0][7] = 0x76;
  
  // Sensor 2: 286164348927DEA9  
  tempDeviceAddresses[1][0] = 0x28; tempDeviceAddresses[1][1] = 0x61; tempDeviceAddresses[1][2] = 0x64; tempDeviceAddresses[1][3] = 0x34;
  tempDeviceAddresses[1][4] = 0x89; tempDeviceAddresses[1][5] = 0x27; tempDeviceAddresses[1][6] = 0xDE; tempDeviceAddresses[1][7] = 0xA9;
  
  // Sensor 3: 28616434C951B1A0
  tempDeviceAddresses[2][0] = 0x28; tempDeviceAddresses[2][1] = 0x61; tempDeviceAddresses[2][2] = 0x64; tempDeviceAddresses[2][3] = 0x34;
  tempDeviceAddresses[2][4] = 0xC9; tempDeviceAddresses[2][5] = 0x51; tempDeviceAddresses[2][6] = 0xB1; tempDeviceAddresses[2][7] = 0xA0;
  
  // Sensor 4: 28616434CDBEBB2D
  tempDeviceAddresses[3][0] = 0x28; tempDeviceAddresses[3][1] = 0x61; tempDeviceAddresses[3][2] = 0x64; tempDeviceAddresses[3][3] = 0x34;
  tempDeviceAddresses[3][4] = 0xCD; tempDeviceAddresses[3][5] = 0xBE; tempDeviceAddresses[3][6] = 0xBB; tempDeviceAddresses[3][7] = 0x2D;
  
  // Sensor 5: 28616434C20D6890
  tempDeviceAddresses[4][0] = 0x28; tempDeviceAddresses[4][1] = 0x61; tempDeviceAddresses[4][2] = 0x64; tempDeviceAddresses[4][3] = 0x34;
  tempDeviceAddresses[4][4] = 0xC2; tempDeviceAddresses[4][5] = 0x0D; tempDeviceAddresses[4][6] = 0x68; tempDeviceAddresses[4][7] = 0x90;
  
  // Sensor 6: 28D47F4A000000FF
  tempDeviceAddresses[5][0] = 0x28; tempDeviceAddresses[5][1] = 0xD4; tempDeviceAddresses[5][2] = 0x7F; tempDeviceAddresses[5][3] = 0x4A;
  tempDeviceAddresses[5][4] = 0x00; tempDeviceAddresses[5][5] = 0x00; tempDeviceAddresses[5][6] = 0x00; tempDeviceAddresses[5][7] = 0xFF;

  // Sensor 7: 2874984A00000028
  tempDeviceAddresses[6][0] = 0x28; tempDeviceAddresses[6][1] = 0x74; tempDeviceAddresses[6][2] = 0x98; tempDeviceAddresses[6][3] = 0x4A;
  tempDeviceAddresses[6][4] = 0x00; tempDeviceAddresses[6][5] = 0x00; tempDeviceAddresses[6][6] = 0x00; tempDeviceAddresses[6][7] = 0x28;

  // Sensor 8: 283CD648000000B0
  tempDeviceAddresses[7][0] = 0x28; tempDeviceAddresses[7][1] = 0x3C; tempDeviceAddresses[7][2] = 0xD6; tempDeviceAddresses[7][3] = 0x48;
  tempDeviceAddresses[7][4] = 0x00; tempDeviceAddresses[7][5] = 0x00; tempDeviceAddresses[7][6] = 0x00; tempDeviceAddresses[7][7] = 0xB0;

  // Sensor 9: 28DA8A4A00000098
  tempDeviceAddresses[8][0] = 0x28; tempDeviceAddresses[8][1] = 0xDA; tempDeviceAddresses[8][2] = 0x8A; tempDeviceAddresses[8][3] = 0x4A;
  tempDeviceAddresses[8][4] = 0x00; tempDeviceAddresses[8][5] = 0x00; tempDeviceAddresses[8][6] = 0x00; tempDeviceAddresses[8][7] = 0x98;

  // Sensor 10: 2879F54800000098
  tempDeviceAddresses[9][0] = 0x28; tempDeviceAddresses[9][1] = 0x79; tempDeviceAddresses[9][2] = 0xF5; tempDeviceAddresses[9][3] = 0x48;
  tempDeviceAddresses[9][4] = 0x00; tempDeviceAddresses[9][5] = 0x00; tempDeviceAddresses[9][6] = 0x00; tempDeviceAddresses[9][7] = 0x98;

  // Sensor 11: 28F5874A000000E6
  tempDeviceAddresses[10][0] = 0x28; tempDeviceAddresses[10][1] = 0xF5; tempDeviceAddresses[10][2] = 0x87; tempDeviceAddresses[10][3] = 0x4A;
  tempDeviceAddresses[10][4] = 0x00; tempDeviceAddresses[10][5] = 0x00; tempDeviceAddresses[10][6] = 0x00; tempDeviceAddresses[10][7] = 0xE6;

  // Sensor 12: 28037F4A000000BE
  tempDeviceAddresses[11][0] = 0x28; tempDeviceAddresses[11][1] = 0x03; tempDeviceAddresses[11][2] = 0x7F; tempDeviceAddresses[11][3] = 0x4A;
  tempDeviceAddresses[11][4] = 0x00; tempDeviceAddresses[11][5] = 0x00; tempDeviceAddresses[11][6] = 0x00; tempDeviceAddresses[11][7] = 0xBE;


  // Print sensor addresses for verification
  Serial.println("Using hardcoded sensor addresses:");
  for (int i = 0; i < NUM_SENSORS; i++) {
    Serial.print("Sensor ");
    Serial.print(i + 1);
    Serial.print(" address: ");
    printAddress(tempDeviceAddresses[i]);
    Serial.println();
  }
  
  systemReady = true;

  // Set resolution to 10-bit for faster conversion (0.25°C resolution, 187.5ms)
  sensors.setResolution(10);

  // Initialize DHT update timer
  lastDHTUpdateTime = millis();
  
  // Initialize BME280 sensors using SPI
  initializeBME280Sensors();
  
  // Initialize DHT sensors
  initializeDHTSensors();
  
  Serial.println("Temperature Control System Ready");
  digitalWrite(STATUS_LED, HIGH);
}

void initializeBME280Sensors() {
  // Initialize SPI
  SPI.begin();
  
  // Initialize chip select pins and set them HIGH (inactive)
  pinMode(BMP280_CS_1, OUTPUT);
  pinMode(BMP280_CS_2, OUTPUT);
  digitalWrite(BMP280_CS_1, HIGH);
  digitalWrite(BMP280_CS_2, HIGH);
  
  // Initialize BME280 sensor 1
  digitalWrite(BMP280_CS_1, LOW);  // Select sensor 1
  delay(10);  // Small delay for CS to settle
  bmpFound[0] = bmp1.begin();
  digitalWrite(BMP280_CS_1, HIGH);  // Deselect sensor 1
  
  if (bmpFound[0]) {
    Serial.println("BME280 sensor 1 found (CS pin 26)");
  } else {
    Serial.println("BME280 sensor 1 not found (CS pin 26)");
    Serial.println("Could not find a valid BME280 sensor, check wiring, address, sensor ID!");
    Serial.print("SensorID was: 0x"); Serial.println(bmp1.sensorID(),16);
    Serial.print("        ID of 0xFF probably means a bad address, a BMP 180 or BMP 085\n");
    Serial.print("   ID of 0x56-0x58 represents a BMP 280,\n");
    Serial.print("        ID of 0x60 represents a BME 280.\n");
    Serial.print("        ID of 0x61 represents a BME 680.\n");
  }
  
  // Initialize BME280 sensor 2
  digitalWrite(BMP280_CS_2, LOW);  // Select sensor 2
  delay(10);  // Small delay for CS to settle
  bmpFound[1] = bmp2.begin();
  digitalWrite(BMP280_CS_2, HIGH);  // Deselect sensor 2
  
  if (bmpFound[1]) {
    Serial.println("BME280 sensor 2 found (CS pin 28)");
  } else {
    Serial.println("BME280 sensor 2 not found (CS pin 28)");
  }
  
  int foundCount = 0;
  for (int i = 0; i < NUM_BMP280_SENSORS; i++) {
    if (bmpFound[i]) foundCount++;
  }
  
  Serial.print("Found ");
  Serial.print(foundCount);
  Serial.println(" out of 2 BME280 sensors");
}

void initializeDHTSensors() {
  pinMode(DHT_PIN_1, OUTPUT);
  pinMode(DHT_PIN_2, OUTPUT);
  // Initialize DHT sensor 1
  // Try reading from sensor to check if it's working
  float temp1 = dht1.getTemperature();
  float hum1 = dht1.getHumidity();
  
  if (!isnan(temp1) && !isnan(hum1)) {
    dhtFound[0] = true;
    Serial.println("DHT22 sensor 1 found (Pin 22)");
  } else {
    dhtFound[0] = false;
    Serial.println("DHT22 sensor 1 not found (Pin 22)");
  }
  
  // Initialize DHT sensor 2
  // Try reading from sensor to check if it's working
  float temp2 = dht2.getTemperature();
  float hum2 = dht2.getHumidity();
  
  if (!isnan(temp2) && !isnan(hum2)) {
    dhtFound[1] = true;
    Serial.println("DHT22 sensor 2 found (Pin 24)");
  } else {
    dhtFound[1] = false;
    Serial.println("DHT22 sensor 2 not found (Pin 24)");
  }
  
  int foundCount = 0;
  for (int i = 0; i < NUM_DHT_SENSORS; i++) {
    if (dhtFound[i]) foundCount++;
  }
  
  Serial.print("Found ");
  Serial.print(foundCount);
  Serial.println(" out of 2 DHT22 sensors");
}

void loop() {
  unsigned long currentTime = millis();
  
  // Update sensors at specified interval
  if (currentTime - lastUpdateTime >= UPDATE_INTERVAL) {
    updateTemperatures();
    updateControl();
    lastUpdateTime = currentTime;
  }
  
  // Process serial commands
  processSerialCommands();
  
  // Watchdog reset
  if (systemReady) {
    digitalWrite(STATUS_LED, !digitalRead(STATUS_LED));
  }
}

void updateTemperatures() {
  sensors.requestTemperatures();

  for (int i = 0; i < NUM_SENSORS; i++) {
    float temp = sensors.getTempC(tempDeviceAddresses[i]);

    if (temp == DEVICE_DISCONNECTED_C) {
      Serial.print("Sensor ");
      Serial.print(i);
      Serial.println(" disconnected!");
      currentTemperatures[i] = 0.0; // Error value
    } else {
      currentTemperatures[i] = temp;
    }
  }

  // Update BME280 sensors
  updateBME280Sensors();

  // Update DHT sensors only every 10 seconds (ambient conditions change slowly)
  unsigned long currentTime = millis();
  if (currentTime - lastDHTUpdateTime >= DHT_UPDATE_INTERVAL) {
    updateDHTSensors();
    lastDHTUpdateTime = currentTime;
  }

  // Update Air Flow sensors
  updateFlowSensors();
}

void updateBME280Sensors() {
  // Array of sensor pointers and CS pins for easier iteration
  Adafruit_BMP280* bmpSensors[NUM_BMP280_SENSORS] = {&bmp1, &bmp2};
  int csPins[NUM_BMP280_SENSORS] = {BMP280_CS_1, BMP280_CS_2};
  
  for (int i = 0; i < NUM_BMP280_SENSORS; i++) {
    if (bmpFound[i]) {
      // Select the sensor by pulling CS LOW
      digitalWrite(csPins[i], LOW);
      delay(1);  // Small delay for CS to settle
      
      bmpTemperatures[i] = bmpSensors[i]->readTemperature();
      bmpPressure[i] = bmpSensors[i]->readPressure() / 100.0F; // Convert Pa to hPa
      
      // Deselect the sensor by pulling CS HIGH
      digitalWrite(csPins[i], HIGH);
      
      if (isnan(bmpTemperatures[i]) || isnan(bmpPressure[i])) {
        Serial.print("Failed to read from BME280 sensor ");
        Serial.println(i + 1);
        bmpTemperatures[i] = 0.0;
        bmpPressure[i] = 0.0;
      }
    } else {
      bmpTemperatures[i] = 0.0;
      bmpPressure[i] = 0.0;
    }
  }
}

void updateDHTSensors() {
  // Array of sensor pointers for easier iteration
  DHT22* dhtSensors[NUM_DHT_SENSORS] = {&dht1, &dht2};
  
  for (int i = 0; i < NUM_DHT_SENSORS; i++) {
    if (dhtFound[i]) {
      dhtTemperatures[i] = dhtSensors[i]->getTemperature();
      dhtHumidity[i] = dhtSensors[i]->getHumidity();
      if (isnan(dhtTemperatures[i]) || isnan(dhtHumidity[i])) {
        Serial.print("Failed to read from DHT22 sensor ");
        Serial.println(i + 1);
        dhtTemperatures[i] = 0.0;
        dhtHumidity[i] = 0.0;
      }
    } else {
      dhtTemperatures[i] = 0.0;
      dhtHumidity[i] = 0.0;
    }
  }
}

void updateFlowSensors() {
  // Array of analog pin assignments for flow sensors
  int flowPins[NUM_FLOW_SENSORS] = {FLOW_SENSOR_1, FLOW_SENSOR_2, FLOW_SENSOR_3, FLOW_SENSOR_4};
  
  for (int i = 0; i < NUM_FLOW_SENSORS; i++) {
    // Read analog voltage (0-1023)
    int rawValue = analogRead(flowPins[i]);
    
    // Convert to voltage (0-5V)
    float voltage = rawValue * (5.0 / 1023.0);
    
    // Calculate flow rate using 6th order polynomial
    flowRatesData[i] = calculateFlowRate(voltage, flowCoefficients[i]);
  }
}

float calculateFlowRate(float voltage, FlowSensorCoefficients coeffs) {
  // 6th order polynomial: flow = a0 + a1*V + a2*V^2 + a3*V^3 + a4*V^4 + a5*V^5 + a6*V^6
  float v = voltage;
  float v2 = v * v;
  float v3 = v2 * v;
  float v4 = v3 * v;
  float v5 = v4 * v;
  float v6 = v5 * v;
  
  return coeffs.a0 * v6 + coeffs.a1 * v5 + coeffs.a2 * v4 + coeffs.a3 * v3 + 
         coeffs.a4 * v2 + coeffs.a5 * v + coeffs.a6 ;
}

void updateControl() {
  // Simple PID control for hot plates
  // With 5 sensors, use sensor 0 for hot plate 0 and sensor 4 for hot plate 1

  for (int i = 0; i < NUM_HOT_PLATES; i++) {      
    int controlSensor = i == 0 ? 0 : 4;      
    float error = targetTemperatures[i] - currentTemperatures[controlSensor];
    // Apply safety limits
    if (currentTemperatures[controlSensor] > MAX_TEMP) {
      digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2, LOW);
      hotPlateStates[i] = false;
      Serial.print("SAFETY: Hot plate ");
      Serial.print(i + 1);
      Serial.println(" turned off due to over-temperature");
    } 
    else {
      // Simple on/off control based on PID output
      if (currentTemperatures[controlSensor] > targetTemperatures[i]) {
        digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2,  LOW );
        hotPlateStates[i] = false;
      }
      else{
        digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2,  HIGH );
        hotPlateStates[i] = true;
      }
    }
    previousError[i] = error;
  }
}

void processSerialCommands() {
  if (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    
    if (command.length() > 0) {
      processCommand(command);
    }
  }
}

void processCommand(String command) {
  // Increased JSON buffer size
  DynamicJsonDocument doc(512);
  DeserializationError error = deserializeJson(doc, command);
  
  if (error) {
    Serial.print("JSON parsing error: ");
    Serial.println(error.c_str());
    sendErrorResponse("Invalid JSON format");
    return;
  }
  
  String cmd = doc["cmd"] | "";
  
  if (cmd == "get_status") {
    sendStatusResponse();
  } else if (cmd == "ping") {
    // Simple ping response for connectivity test
    Serial.println("{\"status\":\"ok\",\"msg\":\"pong\"}");
  } else if (cmd == "set_temp") {
    int sensor = doc["sensor"] | -1;
    float temp = doc["target"] | -0.0;
    
    if (sensor >= 0 && sensor < NUM_HOT_PLATES && temp >= MIN_TEMP && temp <= MAX_TEMP) {
      targetTemperatures[sensor] = temp;
      sendStatusResponse();
    } else {
      sendErrorResponse("Invalid temperature parameters");
    }
  } else if (cmd == "set_fan") {
    int fan = doc["fan"] | -1;
    int speed = doc["speed"] | -1;
    
    if (fan >= 0 && fan < NUM_FANS && speed >= 0 && speed <= 255) {
      fanSpeeds[fan] = speed;
      setFanSpeed(fan, speed);
      sendStatusResponse();
    } else {
      sendErrorResponse("Invalid fan parameters");
    }
  } else if (cmd == "toggle_hotplate") {
    int plate = doc["plate"] | -1;
    bool state = doc["state"] | false;
    
    if (plate >= 0 && plate < NUM_HOT_PLATES) {
      hotPlateStates[plate] = state;
      sendStatusResponse();
    } else {
      sendErrorResponse("Invalid hot plate parameters");
    }
  } else {
    sendErrorResponse("Unknown command");
  }
}

void setFanSpeed(int fan, int speed) {
  switch (fan) {
    case 0: analogWrite(FAN_1_PWM, speed); break;
    case 1: analogWrite(FAN_2_PWM, speed); break;
    case 2: analogWrite(FAN_3_PWM, speed); break;
    case 3: analogWrite(FAN_4_PWM, speed); break;
  }
}

void sendStatusResponse() {
  DynamicJsonDocument doc(768);  // Increased buffer size for BME280 data
  
  doc["status"] = "ok";
  JsonObject data = doc.createNestedObject("data");
  
  JsonArray temps = data.createNestedArray("temperatures");
  for (int i = 0; i < NUM_SENSORS; i++) {
    temps.add(currentTemperatures[i]);
  }
  
  // Add BME280 temperature data
  JsonArray bmpTemps = data.createNestedArray("temperature_bmp");
  for (int i = 0; i < NUM_BMP280_SENSORS; i++) {
    bmpTemps.add(bmpTemperatures[i]);
  }
  
  // Add BME280 pressure data
  JsonArray bmpPress = data.createNestedArray("pressure");
  for (int i = 0; i < NUM_BMP280_SENSORS; i++) {
    bmpPress.add(bmpPressure[i]);
  }
  
  // Add DHT temperature data
  JsonArray dhtTemps = data.createNestedArray("temperature_dht");
  for (int i = 0; i < NUM_DHT_SENSORS; i++) {
    dhtTemps.add(dhtTemperatures[i]);
  }
  
  // Add DHT humidity data
  JsonArray dhtHumid = data.createNestedArray("humidity");
  for (int i = 0; i < NUM_DHT_SENSORS; i++) {
    dhtHumid.add(dhtHumidity[i]);
  }
  
  JsonArray targets = data.createNestedArray("target_temperatures");
  for (int i = 0; i < NUM_HOT_PLATES; i++) {
    targets.add(targetTemperatures[i]);
  }

  JsonArray fans = data.createNestedArray("fan_speeds");
  for (int i = 0; i < NUM_FANS; i++) {
    fans.add(fanSpeeds[i]);
  }
  
  JsonArray plates = data.createNestedArray("hot_plate_states");
  for (int i = 0; i < NUM_HOT_PLATES; i++) {
    plates.add(hotPlateStates[i]);
  }
  
  // Add flow rate data
  JsonArray flowRates = data.createNestedArray("flow_rates");
  for (int i = 0; i < NUM_FLOW_SENSORS; i++) {
    flowRates.add(flowRatesData[i]);
  }
  
  data["system_ready"] = systemReady;
  
  // Send JSON response
  serializeJson(doc, Serial);
  Serial.println();
}

void sendErrorResponse(String message) {
  DynamicJsonDocument doc(128);
  
  doc["status"] = "error";
  doc["msg"] = message;
  
  serializeJson(doc, Serial);
  Serial.println();
}

void printAddress(DeviceAddress deviceAddress) {
  for (uint8_t i = 0; i < 8; i++) {
    if (deviceAddress[i] < 16) Serial.print("0");
    Serial.print(deviceAddress[i], HEX);
  }
}

void blinkError(int count) {
  for (int i = 0; i < count; i++) {
    digitalWrite(STATUS_LED, HIGH);
    delay(200);
    digitalWrite(STATUS_LED, LOW);
    delay(200);
  }
  delay(1000);
}
