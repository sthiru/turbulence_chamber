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
  - Status LED: Pin 13
  
  Created: 2025-02-25
*/

#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_BMP280.h>
#include <SPI.h>

// Pin Definitions
#define ONE_WIRE_BUS 2
#define SSR_RELAY_1 8
#define SSR_RELAY_2 9
#define FAN_1_PWM 3
#define FAN_2_PWM 5
#define FAN_3_PWM 6
#define FAN_4_PWM 10
#define STATUS_LED 13

// BME280 SPI Chip Select Pins
#define BME280_CS_1 22  // Digital pin 22
#define BME280_CS_2 24  // Digital pin 24
#define BME280_CS_3 26  // Digital pin 26
#define BME280_CS_4 28  // Digital pin 28
#define NUM_BME280_SENSORS 4

// SPI pins for Arduino Mega (hardware SPI)
// MOSI: Pin 51
// MISO: Pin 50
// SCK: Pin 52
#define BME_SCK 52
#define BME_MISO 50
#define BME_MOSI 51

// System Constants
#define NUM_SENSORS 5
#define NUM_FANS 4
#define NUM_HOT_PLATES 2
#define MAX_TEMP 120.0
#define MIN_TEMP 0.0
#define UPDATE_INTERVAL 2000  // 2 seconds

// Global Variables
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress tempDeviceAddresses[NUM_SENSORS];

// BME280 Sensors (SPI)
Adafruit_BMP280 bme1(BME280_CS_1), bme2(BME280_CS_2), bme3(BME280_CS_3), bme4(BME280_CS_4);  // Create 4 BME280 objects
bool bmeFound[NUM_BME280_SENSORS] = {false, false, false, false};

// System State
float currentTemperatures[NUM_SENSORS];
float targetTemperatures[NUM_HOT_PLATES] = {35.0, 35.0};
int fanSpeeds[NUM_FANS] = {255, 255, 255, 255};
bool hotPlateStates[NUM_HOT_PLATES] = {false, false};

// BME280 Data arrays
float bmeTemperatures[NUM_BME280_SENSORS];
float bmeHumidity[NUM_BME280_SENSORS];
float bmePressure[NUM_BME280_SENSORS];

unsigned long lastUpdateTime = 0;
bool systemReady = false;

// PID Variables (simplified)
float kp = 2.0, ki = 0.5, kd = 1.0;
float integral[NUM_HOT_PLATES] = {0, 0};
float previousError[NUM_HOT_PLATES] = {0, 0};

void setup() {
  Serial.begin(115200);
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
  
  // Set resolution
  sensors.setResolution(12);
  
  // Initialize BME280 sensors using SPI
  initializeBME280Sensors();
  
  Serial.println("Temperature Control System Ready");
  digitalWrite(STATUS_LED, HIGH);
}

void initializeBME280Sensors() {
  // Initialize SPI
  SPI.begin();
  
  // Initialize chip select pins
  pinMode(BME280_CS_1, OUTPUT);
  pinMode(BME280_CS_2, OUTPUT);
  pinMode(BME280_CS_3, OUTPUT);
  pinMode(BME280_CS_4, OUTPUT);
  
  // Set all chip select pins high (inactive)
  //digitalWrite(BME280_CS_1, HIGH);
  //digitalWrite(BME280_CS_2, HIGH);
  //digitalWrite(BME280_CS_3, HIGH);
  //digitalWrite(BME280_CS_4, HIGH);

  // Initialize BME280 sensor 1
  bmeFound[0] = bme1.begin();
  if (bmeFound[0]) {
    Serial.println("BME280 sensor 1 found (CS pin 22)");
    
  } else {
    Serial.println("BME280 sensor 1 not found (CS pin 22)");
    Serial.println("Could not find a valid BME280 sensor, check wiring, address, sensor ID!");
    Serial.print("SensorID was: 0x"); Serial.println(bme1.sensorID(),16);
    Serial.print("        ID of 0xFF probably means a bad address, a BMP 180 or BMP 085\n");
    Serial.print("   ID of 0x56-0x58 represents a BMP 280,\n");
    Serial.print("        ID of 0x60 represents a BME 280.\n");
    Serial.print("        ID of 0x61 represents a BME 680.\n");
  }
  
  // Initialize BME280 sensor 2
  bmeFound[1] = bme2.begin();
  if (bmeFound[1]) {
    Serial.println("BME280 sensor 2 found (CS pin 24)");
    
  } else {
    Serial.println("BME280 sensor 2 not found (CS pin 24)");
  }
  
  // Initialize BME280 sensor 3
  bmeFound[2] = bme3.begin();
  if (bmeFound[2]) {
    Serial.println("BME280 sensor 3 found (CS pin 26)");
    
  } else {
    Serial.println("BME280 sensor 3 not found (CS pin 26)");
  }
  
  // Initialize BME280 sensor 4
  bmeFound[3] = bme4.begin();
  if (bmeFound[3]) {
    Serial.println("BME280 sensor 4 found (CS pin 28)");
   
  } else {
    Serial.println("BME280 sensor 4 not found (CS pin 28)");
  }
  
  int foundCount = 0;
  for (int i = 0; i < NUM_BME280_SENSORS; i++) {
    if (bmeFound[i]) foundCount++;
  }
  
  Serial.print("Found ");
  Serial.print(foundCount);
  Serial.println(" out of 4 BME280 sensors");
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
}

void updateBME280Sensors() {
  // Array of sensor pointers for easier iteration
  Adafruit_BMP280* bmeSensors[NUM_BME280_SENSORS] = {&bme1, &bme2, &bme3, &bme4};
  
  for (int i = 0; i < NUM_BME280_SENSORS; i++) {
    if (bmeFound[i]) {
      bmeTemperatures[i] = bmeSensors[i]->readTemperature();
      //bmeHumidity[i] = bmeSensors[i]->readHumidity();
      bmePressure[i] = bmeSensors[i]->readPressure() / 100.0F; // Convert Pa to hPa
      
      if (isnan(bmeTemperatures[i]) || isnan(bmeHumidity[i]) || isnan(bmePressure[i])) {
        Serial.print("Failed to read from BME280 sensor ");
        Serial.println(i + 1);
        bmeTemperatures[i] = 0.0;
        bmeHumidity[i] = 0.0;
        bmePressure[i] = 0.0;
      }
    } else {
      bmeTemperatures[i] = 0.0;
      bmeHumidity[i] = 0.0;
      bmePressure[i] = 0.0;
    }
  }
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
  JsonArray bmeTemps = data.createNestedArray("temperature_bme");
  for (int i = 0; i < NUM_BME280_SENSORS; i++) {
    bmeTemps.add(bmeTemperatures[i]);
  }
  
  // Add BME280 humidity data
  JsonArray bmeHumid = data.createNestedArray("humidity");
  for (int i = 0; i < NUM_BME280_SENSORS; i++) {
    bmeHumid.add(bmeHumidity[i]);
  }
  
  // Add BME280 pressure data
  JsonArray bmePress = data.createNestedArray("pressure");
  for (int i = 0; i < NUM_BME280_SENSORS; i++) {
    bmePress.add(bmePressure[i]);
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
