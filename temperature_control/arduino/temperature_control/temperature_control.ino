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

// Pin Definitions
#define ONE_WIRE_BUS 2
#define SSR_RELAY_1 8
#define SSR_RELAY_2 9
#define FAN_1_PWM 3
#define FAN_2_PWM 5
#define FAN_3_PWM 6
#define FAN_4_PWM 10
#define STATUS_LED 13

// System Constants
#define NUM_SENSORS 6
#define NUM_FANS 4
#define NUM_HOT_PLATES 2
#define MAX_TEMP 80.0
#define MIN_TEMP 0.0
#define UPDATE_INTERVAL 2000  // 2 seconds

// Global Variables
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress tempDeviceAddresses[NUM_SENSORS];

// System State
float currentTemperatures[NUM_SENSORS];
float targetTemperatures[NUM_HOT_PLATES] = {25.0, 25.0};
int fanSpeeds[NUM_FANS] = {0, 0, 0, 0};
bool hotPlateStates[NUM_HOT_PLATES] = {false, false};
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
  analogWrite(FAN_1_PWM, 0);
  analogWrite(FAN_2_PWM, 0);
  analogWrite(FAN_3_PWM, 0);
  analogWrite(FAN_4_PWM, 0);
  
  // Initialize temperature sensors
  sensors.begin();
  
  // Discover and address sensors
  int deviceCount = sensors.getDeviceCount();
  Serial.print("Found ");
  Serial.print(deviceCount);
  Serial.println(" temperature devices");
  
  if (deviceCount >= NUM_SENSORS) {
    for (int i = 0; i < NUM_SENSORS; i++) {
      if (sensors.getAddress(tempDeviceAddresses[i], i)) {
        Serial.print("Sensor ");
        Serial.print(i);
        Serial.print(" address: ");
        printAddress(tempDeviceAddresses[i]);
        Serial.println();
      } else {
        Serial.print("Unable to find address for sensor ");
        Serial.println(i);
      }
    }
    systemReady = true;
  } else {
    Serial.println("Not enough sensors found!");
    blinkError(5);
  }
  
  // Set resolution
  sensors.setResolution(12);
  
  Serial.println("Temperature Control System Ready");
  digitalWrite(STATUS_LED, HIGH);
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
      currentTemperatures[i] = -999.0; // Error value
    } else {
      currentTemperatures[i] = temp;
    }
  }
}

void updateControl() {
  // Simple PID control for hot plates
  for (int i = 0; i < NUM_HOT_PLATES; i++) {
    if (hotPlateStates[i]) {
      // Use sensor i*3 as control sensor for hot plate i
      int controlSensor = i * 3;
      if (controlSensor < NUM_SENSORS && currentTemperatures[controlSensor] > -100) {
        
        float error = targetTemperatures[i] - currentTemperatures[controlSensor];
        integral[i] += error * (UPDATE_INTERVAL / 1000.0);
        float derivative = (error - previousError[i]) / (UPDATE_INTERVAL / 1000.0);
        
        // PID calculation
        float output = kp * error + ki * integral[i] + kd * derivative;
        
        // Apply safety limits
        if (currentTemperatures[controlSensor] > MAX_TEMP) {
          digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2, LOW);
          Serial.print("SAFETY: Hot plate ");
          Serial.print(i + 1);
          Serial.println(" turned off due to over-temperature");
        } else {
          // Simple on/off control based on PID output
          digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2, output > 0 ? HIGH : LOW);
        }
        
        previousError[i] = error;
      }
    } else {
      digitalWrite(i == 0 ? SSR_RELAY_1 : SSR_RELAY_2, LOW);
      integral[i] = 0; // Reset integral when off
    }
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
  DynamicJsonDocument doc(256);
  DeserializationError error = deserializeJson(doc, command);
  
  if (error) {
    sendErrorResponse("Invalid JSON format");
    return;
  }
  
  String cmd = doc["cmd"] | "";
  
  if (cmd == "get_status") {
    sendStatusResponse();
  } else if (cmd == "set_temp") {
    int sensor = doc["sensor"] | -1;
    float temp = doc["target"] | -999.0;
    
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
  DynamicJsonDocument doc(512);
  
  doc["status"] = "ok";
  JsonObject data = doc.createNestedObject("data");
  
  JsonArray temps = data.createNestedArray("temperatures");
  for (int i = 0; i < NUM_SENSORS; i++) {
    temps.add(currentTemperatures[i]);
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
