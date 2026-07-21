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
#include <PID_v1.h>
#include <DHT22.h>
#include <Adafruit_MAX31865.h>
#include <Vrekrer_scpi_parser.h>

// The value of the Rref resistor. Use 430.0 for PT100 and 4300.0 for PT1000
#define RREF      430.0
// 100.0 for PT100, 1000.0 for PT1000
#define RNOMINAL  100.0

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
#define BMP280_CS_1 12  // Digital pin 22
#define BMP280_CS_2 13  // Digital pin 24
#define NUM_BMP280_SENSORS 2

// DHT Sensor Data Pins
#define DHT_PIN_1 10  // Digital pin 26
#define DHT_PIN_2 11  // Digital pin 28
#define NUM_DHT_SENSORS 2

// SPI pins for Arduino Mega (hardware SPI)
// MOSI: Pin 51
// MISO: Pin 50
// SCK: Pin 52
#define BMP_SCK 52
#define BMP_MISO 50
#define BMP_MOSI 51

// System Constants
#define NUM_DS18B20_SENSORS 14  // Total physical DS18B20 sensors
#define NUM_SENSORS 12          // Number of sensors in temperatures array (excluding hotplate sensors)
#define NUM_FANS 4
#define NUM_HOT_PLATES 2
#define NUM_FLOW_SENSORS 4
#define MAX_TEMP 120.0
#define MIN_TEMP 0.0
unsigned long UPDATE_INTERVAL = 1000;  // 1 second (default, can be modified)
unsigned long DHT_UPDATE_INTERVAL = 10000;  // 10 seconds for DHT sensors (default, can be modified)

const unsigned long WindowSize = 3000;   // 3 seconds window for the PID control logic
unsigned long windowStartTime = millis();


// Global Variables
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);
DeviceAddress tempDeviceAddresses[NUM_DS18B20_SENSORS];

// BME280 Sensors (SPI)
Adafruit_BMP280 bmp1(BMP280_CS_1), bmp2(BMP280_CS_2);  // Create 2 BME280 objects
bool bmpFound[NUM_BMP280_SENSORS] = {false, false};

// DHT Sensors (AM2302)
DHT22 dht1(DHT_PIN_1);
DHT22 dht2(DHT_PIN_2);
bool dhtFound[NUM_DHT_SENSORS] = {false, false};

//PT100 Sensors
// use hardware SPI, just pass in the CS pin
Adafruit_MAX31865 hoptplate1_temp = Adafruit_MAX31865(22);
Adafruit_MAX31865 hoptplate2_temp = Adafruit_MAX31865(23);

// System State
float currentTemperatures[NUM_SENSORS];
double targetTemperatures[NUM_HOT_PLATES] = {85.0, 85.0};
int fanSpeeds[NUM_FANS] = {255, 255, 255, 255};
bool hotPlateStates[NUM_HOT_PLATES] = {false, false};
bool manualHotPlateControl[NUM_HOT_PLATES] = {false, false}; // Manual override flags
bool debugEnabled = false; // Debug mode flag for verbose logging
float safetyTemperature = 280.0; // Safety temperature limit (�C)

// Hotplate Surface Temperatures (separate variables)
float temp_hotplate1 = 0.0;  // Surface sensor 13 (index 12)
float temp_hotplate2 = 0.0;  // Surface sensor 14 (index 13)

// BME280 Data (separate variables for internal/external)
float bmpTemperature_internal = 0.0;
float bmpPressure_internal = 0.0;
float bmpTemperature_external = 0.0;
float bmpPressure_external = 0.0;

// DHT Data (separate variables for internal/external)
float dhtTemperature_internal = 0.0;
float dhtHumidity_internal = 0.0;
float dhtTemperature_external = 0.0;
float dhtHumidity_external = 0.0;

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

// PID Controller Variables
// PID tuning parameters for each hotplate
double kp0 = 8.0, ki0 = 0.08, kd0 = 80.0;
double kp1 = 8.0, ki1 = 0.08, kd1 = 80.0;

static double last_hotplate1Temp = 0;
static double last_hotplate2Temp = 0;

// PID input/output variables for hotplate 0
double pidInput0, pidOutput0;
PID pid0(&pidInput0, &pidOutput0, &targetTemperatures[0], kp0, ki0, kd0, DIRECT);

// PID input/output variables for hotplate 1
double pidInput1, pidOutput1;
PID pid1(&pidInput1, &pidOutput1, &targetTemperatures[1], kp1, ki1, kd1, DIRECT);

SCPI_Parser my_instrument;

void IDN_q(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) parameters;
  interface.println(F("{\"status\":\"ok\",\"msg\":\"Turbulence Chamber Controller\"}"));
}

void HELP_q(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) parameters;
  interface.println(F("{\"status\":\"ok\",\"msg\":\"*IDN? HELP? SYST:STAT? SYST:PING? SOUR:TEMP SOUR:FAN OUTP:HOTPL CONF:SAFE:TEMP CONF:PID CONF:FAN:START CONF:POLL CONF:AMBI:POLL CONF:DEBUG\"}"));
}

void PING_q(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) parameters;
  interface.println(F("{\"status\":\"ok\",\"msg\":\"pong\"}"));
}

void STAT_q(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) parameters;
  sendStatusResponse();
}

void SOUR_TEMP(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) interface;
  if (parameters.Size() < 2) { sendErrorResponse("missing parameters"); return; }
  int sensor = String(parameters[0]).toInt();
  float temp = String(parameters[1]).toFloat();
  if (sensor >= 0 && sensor < NUM_HOT_PLATES && temp >= MIN_TEMP && temp <= MAX_TEMP) {
    targetTemperatures[sensor] = temp;
    sendStatusResponse();
    return;
  }
  sendErrorResponse("invalid parameters");
}

void SOUR_FAN(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) interface;
  if (parameters.Size() < 2) { sendErrorResponse("missing parameters"); return; }
  int fan = String(parameters[0]).toInt();
  int speed = String(parameters[1]).toInt();
  if (fan >= 0 && fan < NUM_FANS && speed >= 0 && speed <= 255) {
    fanSpeeds[fan] = speed;
    setFanSpeed(fan, speed);
    sendStatusResponse();
    return;
  }
  sendErrorResponse("invalid parameters");
}

void OUTP_HOTPL(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  (void) interface;
  if (parameters.Size() < 2) { sendErrorResponse("missing parameters"); return; }
  int plate = String(parameters[0]).toInt();
  int state = String(parameters[1]).toInt();
  if (plate >= 0 && plate < NUM_HOT_PLATES) {
    manualHotPlateControl[plate] = true;
    hotPlateStates[plate] = (state != 0);
    sendStatusResponse();
    return;
  }
  sendErrorResponse("invalid parameters");
}

void CONF_SAFETY_TEMP(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 1) { sendErrorResponse("missing parameters"); return; }
  safetyTemperature = String(parameters[0]).toFloat();
  sendStatusResponse();
}

void CONF_PID(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 4) { sendErrorResponse("missing parameters"); return; }
  int plate = String(parameters[0]).toInt();
  float kp = String(parameters[1]).toFloat();
  float ki = String(parameters[2]).toFloat();
  float kd = String(parameters[3]).toFloat();
  if (plate == 0) {
    kp0 = kp; ki0 = ki; kd0 = kd;
    pid0.SetTunings(kp0, ki0, kd0);
    sendStatusResponse();
    return;
  }
  if (plate == 1) {
    kp1 = kp; ki1 = ki; kd1 = kd;
    pid1.SetTunings(kp1, ki1, kd1);
    sendStatusResponse();
    return;
  }
  sendErrorResponse("invalid plate");
}

void CONF_FAN_START(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 1) { sendErrorResponse("missing parameters"); return; }
  String behaviour = String(parameters[0]);
  if (behaviour == "off") {
    for (int i = 0; i < NUM_FANS; i++) { fanSpeeds[i] = 0; setFanSpeed(i, 0); }
  } else if (behaviour == "half_speed") {
    for (int i = 0; i < NUM_FANS; i++) { fanSpeeds[i] = 127; setFanSpeed(i, 127); }
  } else if (behaviour == "full_speed") {
    for (int i = 0; i < NUM_FANS; i++) { fanSpeeds[i] = 255; setFanSpeed(i, 255); }
  } else {
    sendErrorResponse("invalid fan behaviour");
    return;
  }
  sendStatusResponse();
}

void CONF_POLL(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 1) { sendErrorResponse("missing parameters"); return; }
  int seconds = String(parameters[0]).toInt();
  if (seconds < 1) { sendErrorResponse("invalid polling interval"); return; }
  UPDATE_INTERVAL = (unsigned long)seconds * 1000;
  sendStatusResponse();
}

void CONF_AMB_POLL(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 1) { sendErrorResponse("missing parameters"); return; }
  int seconds = String(parameters[0]).toInt();
  if (seconds < 1) { sendErrorResponse("invalid polling interval"); return; }
  DHT_UPDATE_INTERVAL = (unsigned long)seconds * 1000;
  sendStatusResponse();
}

void CONF_DEBUG(SCPI_C commands, SCPI_P parameters, Stream &interface) {
  (void) commands;
  if (parameters.Size() < 1) { sendErrorResponse("missing parameters"); return; }
  debugEnabled = String(parameters[0]).toInt() != 0;
  sendStatusResponse();
}

void registerCommands() {
  my_instrument.RegisterCommand(F("*IDN?"), &IDN_q);
  my_instrument.RegisterCommand(F("HELP?"), &HELP_q);
  my_instrument.RegisterCommand(F("SYSTem:CMDS?"), &HELP_q);
  my_instrument.RegisterCommand(F("SYSTem:PING?"), &PING_q);
  my_instrument.RegisterCommand(F("SYSTem:STATus?"), &STAT_q);
  my_instrument.RegisterCommand(F("SOURce:TEMPerature"), &SOUR_TEMP);
  my_instrument.RegisterCommand(F("SOURce:FAN"), &SOUR_FAN);
  my_instrument.RegisterCommand(F("OUTPut:HOTPLate"), &OUTP_HOTPL);
  my_instrument.RegisterCommand(F("CONFigure:SAFEty:TEMPerature"), &CONF_SAFETY_TEMP);
  my_instrument.RegisterCommand(F("CONFigure:PID"), &CONF_PID);
  my_instrument.RegisterCommand(F("CONFigure:FAN:START"), &CONF_FAN_START);
  my_instrument.RegisterCommand(F("CONFigure:POLLing"), &CONF_POLL);
  my_instrument.RegisterCommand(F("CONFigure:AMBIent:POLLing"), &CONF_AMB_POLL);
  my_instrument.RegisterCommand(F("CONFigure:DEBUg"), &CONF_DEBUG);
}



void setup() {
  Serial.begin(1000000);
  while (!Serial) delay(10);

  registerCommands();
  
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

  //Initialize PT100 Sensors
  hoptplate1_temp.begin(MAX31865_3WIRE);
  hoptplate2_temp.begin(MAX31865_3WIRE);
  hoptplate1_temp.enableBias(true);
  hoptplate1_temp.autoConvert(true);
  hoptplate2_temp.enableBias(true);
  hoptplate2_temp.autoConvert(true);
  
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
  
  // Sensor 2: 28DA8A4A00000098  4
  tempDeviceAddresses[4][0] = 0x28; tempDeviceAddresses[4][1] = 0xDA; tempDeviceAddresses[4][2] = 0x8A; tempDeviceAddresses[4][3] = 0x4A;
  tempDeviceAddresses[4][4] = 0x00; tempDeviceAddresses[4][5] = 0x00; tempDeviceAddresses[4][6] = 0x00; tempDeviceAddresses[4][7] = 0x98;
  
  // Sensor 3: 28616434C951B1A0  3
  tempDeviceAddresses[3][0] = 0x28; tempDeviceAddresses[3][1] = 0x61; tempDeviceAddresses[3][2] = 0x64; tempDeviceAddresses[3][3] = 0x34;
  tempDeviceAddresses[3][4] = 0xC2; tempDeviceAddresses[3][5] = 0x0D; tempDeviceAddresses[3][6] = 0x68; tempDeviceAddresses[3][7] = 0x90;
  
  // Sensor 9: 28D47F4A000000FF  11
  tempDeviceAddresses[11][0] = 0x28; tempDeviceAddresses[11][1] = 0xD4; tempDeviceAddresses[11][2] = 0x7F; tempDeviceAddresses[11][3] = 0x4A;
  tempDeviceAddresses[11][4] = 0x00; tempDeviceAddresses[11][5] = 0x00; tempDeviceAddresses[11][6] = 0x00; tempDeviceAddresses[11][7] = 0xFF;  
  
  // Sensor 5: 2874984A00000028  6
  tempDeviceAddresses[6][0] = 0x28; tempDeviceAddresses[6][1] = 0x74; tempDeviceAddresses[6][2] = 0x98; tempDeviceAddresses[6][3] = 0x4A;
  tempDeviceAddresses[6][4] = 0x00; tempDeviceAddresses[6][5] = 0x00; tempDeviceAddresses[6][6] = 0x00; tempDeviceAddresses[6][7] = 0x28;

  // Sensor 6: 283CD648000000B0
  tempDeviceAddresses[8][0] = 0x28; tempDeviceAddresses[8][1] = 0x3C; tempDeviceAddresses[8][2] = 0xD6; tempDeviceAddresses[8][3] = 0x48;
  tempDeviceAddresses[8][4] = 0x00; tempDeviceAddresses[8][5] = 0x00; tempDeviceAddresses[8][6] = 0x00; tempDeviceAddresses[8][7] = 0xB0;

  // Sensor 8: 2879F54800000098  10
  tempDeviceAddresses[10][0] = 0x28; tempDeviceAddresses[10][1] = 0x79; tempDeviceAddresses[10][2] = 0xF5; tempDeviceAddresses[10][3] = 0x48;
  tempDeviceAddresses[10][4] = 0x00; tempDeviceAddresses[10][5] = 0x00; tempDeviceAddresses[10][6] = 0x00; tempDeviceAddresses[10][7] = 0x98;

  // Sensor 7: 286164348927DEA9  -> 1
  tempDeviceAddresses[1][0] = 0x28; tempDeviceAddresses[1][1] = 0x61; tempDeviceAddresses[1][2] = 0x64; tempDeviceAddresses[1][3] = 0x34;
  tempDeviceAddresses[1][4] = 0x89; tempDeviceAddresses[1][5] = 0x27; tempDeviceAddresses[1][6] = 0xDE; tempDeviceAddresses[1][7] = 0xA9;

  // Sensor 4: 28F5874A000000E6   7
  tempDeviceAddresses[7][0] = 0x28; tempDeviceAddresses[7][1] = 0xF5; tempDeviceAddresses[7][2] = 0x87; tempDeviceAddresses[7][3] = 0x4A;
  tempDeviceAddresses[7][4] = 0x00; tempDeviceAddresses[7][5] = 0x00; tempDeviceAddresses[7][6] = 0x00; tempDeviceAddresses[7][7] = 0xE6;

  // Sensor 10: 28037F4A000000BE  9
  tempDeviceAddresses[9][0] = 0x28; tempDeviceAddresses[9][1] = 0x03; tempDeviceAddresses[9][2] = 0x7F; tempDeviceAddresses[9][3] = 0x4A;
  tempDeviceAddresses[9][4] = 0x00; tempDeviceAddresses[9][5] = 0x00; tempDeviceAddresses[9][6] = 0x00; tempDeviceAddresses[9][7] = 0xBE;

  // Sensor 11: 28616434C951B1A0
  tempDeviceAddresses[5][0] = 0x28; tempDeviceAddresses[5][1] = 0x61; tempDeviceAddresses[5][2] = 0x64; tempDeviceAddresses[5][3] = 0x34;
  tempDeviceAddresses[5][4] = 0xC9; tempDeviceAddresses[5][5] = 0x51; tempDeviceAddresses[5][6] = 0xB1; tempDeviceAddresses[5][7] = 0xA0;

  // Sensor 12: 28616434CDBEBB2D
  tempDeviceAddresses[2][0] = 0x28; tempDeviceAddresses[2][1] = 0x61; tempDeviceAddresses[2][2] = 0x64; tempDeviceAddresses[2][3] = 0x34;
  tempDeviceAddresses[2][4] = 0xCD; tempDeviceAddresses[2][5] = 0xBE; tempDeviceAddresses[2][6] = 0xBB; tempDeviceAddresses[2][7] = 0x2D;

  // Sensor 13: 2866dd4800000021
  tempDeviceAddresses[12][0] = 0x28; tempDeviceAddresses[12][1] = 0x66; tempDeviceAddresses[12][2] = 0xDD; tempDeviceAddresses[12][3] = 0x48;
  tempDeviceAddresses[12][4] = 0x00; tempDeviceAddresses[12][5] = 0x00; tempDeviceAddresses[12][6] = 0x00; tempDeviceAddresses[12][7] = 0x21;
  
  // Sensor 14: 28F9624800000094
  tempDeviceAddresses[13][0] = 0x28; tempDeviceAddresses[13][1] = 0xF9; tempDeviceAddresses[13][2] = 0x62; tempDeviceAddresses[13][3] = 0x48;
  tempDeviceAddresses[13][4] = 0x00; tempDeviceAddresses[13][5] = 0x00; tempDeviceAddresses[13][6] = 0x00; tempDeviceAddresses[13][7] = 0x94;



  // Print sensor addresses for verification
  Serial.println("{\"type\":\"info\",\"message\":\"Using hardcoded sensor addresses\"}");
  for (int i = 0; i < NUM_SENSORS; i++) {
    Serial.print("{\"type\":\"info\",\"sensor_type\":\"ds18b20\",\"sensor_id\":");
    Serial.print(i);
    Serial.print(",\"message\":\"address:");
    printAddress(tempDeviceAddresses[i]);
    Serial.println("\"}");
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
  
  // Initialize PID controllers
  pid0.SetMode(AUTOMATIC);
  pid0.SetOutputLimits(0, WindowSize);  // SSR control: 0 = OFF, 255 = ON (binary)
  pid0.SetSampleTime(200);  // 1 second sample time
  pid1.SetMode(AUTOMATIC);
  pid1.SetOutputLimits(0, WindowSize);  // SSR control: 0 = OFF, 255 = ON (binary)
  pid1.SetSampleTime(200);
  
  Serial.println("{\"type\":\"info\",\"message\":\"Temperature Control System Ready\"}");
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
    Serial.println("{\"type\":\"info\",\"sensor_type\":\"bme280\",\"sensor_id\":1,\"message\":\"found\",\"pin\":26}");
  } else {
      Serial.println("{\"type\":\"error\",\"sensor_type\":\"bme280\",\"sensor_id\":1,\"message\":\"not_found\",\"pin\":26}");
      Serial.print("{\"type\":\"error\",\"sensor_type\":\"bme280\",\"sensor_id\":1,\"message\":\"sensor_id\",\"value\":\"0x");
      Serial.print(bmp1.sensorID(),16);
      Serial.println("\"}");
  }
  
  // Initialize BME280 sensor 2
  digitalWrite(BMP280_CS_2, LOW);  // Select sensor 2
  delay(10);  // Small delay for CS to settle
  bmpFound[1] = bmp2.begin();
  digitalWrite(BMP280_CS_2, HIGH);  // Deselect sensor 2
  
  if (bmpFound[1]) {
    Serial.println("{\"type\":\"info\",\"sensor_type\":\"bme280\",\"sensor_id\":2,\"message\":\"found\",\"pin\":28}");
  } else {
      Serial.println("{\"type\":\"error\",\"sensor_type\":\"bme280\",\"sensor_id\":2,\"message\":\"not_found\",\"pin\":28}");
  }
  
  int foundCount = 0;
  for (int i = 0; i < NUM_BMP280_SENSORS; i++) {
    if (bmpFound[i]) foundCount++;
  }
  
  Serial.print("{\"type\":\"info\",\"sensor_type\":\"bme280\",\"message\":\"count\",\"found\":");
  Serial.print(foundCount);
  Serial.println(",\"total\":2}");
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
    Serial.println("{\"type\":\"info\",\"sensor_type\":\"dht22\",\"sensor_id\":1,\"message\":\"found\",\"pin\":22}");
  } else {
    dhtFound[0] = false;
      Serial.println("{\"type\":\"error\",\"sensor_type\":\"dht22\",\"sensor_id\":1,\"message\":\"not_found\",\"pin\":22}");
  }
  
  // Initialize DHT sensor 2
  // Try reading from sensor to check if it's working
  float temp2 = dht2.getTemperature();
  float hum2 = dht2.getHumidity();
  
  if (!isnan(temp2) && !isnan(hum2)) {
    dhtFound[1] = true;
    Serial.println("{\"type\":\"info\",\"sensor_type\":\"dht22\",\"sensor_id\":2,\"message\":\"found\",\"pin\":24}");
  } else {
    dhtFound[1] = false;
      Serial.println("{\"type\":\"error\",\"sensor_type\":\"dht22\",\"sensor_id\":2,\"message\":\"not_found\",\"pin\":24}");
  }
  
  int foundCount = 0;
  for (int i = 0; i < NUM_DHT_SENSORS; i++) {
    if (dhtFound[i]) foundCount++;
  }
  
  Serial.print("{\"type\":\"info\",\"sensor_type\":\"dht22\",\"message\":\"count\",\"found\":");
  Serial.print(foundCount);
  Serial.println(",\"total\":2}");
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
  //delay(250);  // Small delay for Conversion to settle... already handled in setWaitForConversion... need to try with different pull up resistor

  for (int i = 0; i < NUM_DS18B20_SENSORS; i++) {
    float temp = sensors.getTempC(tempDeviceAddresses[i]);

    if (temp == DEVICE_DISCONNECTED_C) {
      if (debugEnabled) {
        Serial.print("{\"type\":\"error\",\"sensor_type\":\"ds18b20\",\"sensor_id\":");
        Serial.print(i);
        Serial.println(",\"message\":\"disconnected\"}");
      }
      
      // Store in separate variables for hotplate sensors, array for others
      if (i < NUM_SENSORS) {
        currentTemperatures[i] = 0.0;
      }
    } else {
      if (i < NUM_SENSORS) {
        currentTemperatures[i] = temp;
      }
    }
  }

  //Update PT sesnors
  temp_hotplate1 = hoptplate1_temp.temperature(RNOMINAL, RREF);
  temp_hotplate2 = hoptplate2_temp.temperature(RNOMINAL, RREF);
  if(temp_hotplate1 <0 or temp_hotplate1 > 300)
  {
    temp_hotplate1 = 0.0;
  }
  if(temp_hotplate2 <0 or temp_hotplate2 > 300)
  {
    temp_hotplate2 = 0.0;
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
  // BME280 Sensor 1 (Internal)
  if (bmpFound[0]) {
    digitalWrite(BMP280_CS_1, LOW);
    delay(1);
    
    bmpTemperature_internal = bmp1.readTemperature();
    bmpPressure_internal = bmp1.readPressure() / 100.0F;
    
    digitalWrite(BMP280_CS_1, HIGH);
    
    if (isnan(bmpTemperature_internal) || isnan(bmpPressure_internal)) {
      if (debugEnabled) {
        Serial.print("{\"type\":\"error\",\"sensor_type\":\"bme280\",\"sensor_id\":1,\"message\":\"read_failure\"}");
      }
      bmpTemperature_internal = 0.0;
      bmpPressure_internal = 0.0;
    }
  } else {
    bmpTemperature_internal = 0.0;
    bmpPressure_internal = 0.0;
  }
  
  // BME280 Sensor 2 (External)
  if (bmpFound[1]) {
    digitalWrite(BMP280_CS_2, LOW);
    delay(1);
    
    bmpTemperature_external = bmp2.readTemperature();
    bmpPressure_external = bmp2.readPressure() / 100.0F;
    
    digitalWrite(BMP280_CS_2, HIGH);
    
    if (isnan(bmpTemperature_external) || isnan(bmpPressure_external)) {
      if (debugEnabled) {
        Serial.print("{\"type\":\"error\",\"sensor_type\":\"bme280\",\"sensor_id\":2,\"message\":\"read_failure\"}");
      }
      bmpTemperature_external = 0.0;
      bmpPressure_external = 0.0;
    }
  } else {
    bmpTemperature_external = 0.0;
    bmpPressure_external = 0.0;
  }
}

void updateDHTSensors() {
  // DHT22 Sensor 1 (Internal)
  if (dhtFound[0]) {
    dhtTemperature_internal = dht1.getTemperature();
    dhtHumidity_internal = dht1.getHumidity();
    if (isnan(dhtTemperature_internal) || isnan(dhtHumidity_internal)) {
      if (debugEnabled) {
        Serial.print("{\"type\":\"error\",\"sensor_type\":\"dht22\",\"sensor_id\":1,\"message\":\"read_failure\"}");
      }
      dhtTemperature_internal = 0.0;
      dhtHumidity_internal = 0.0;
    }
  } else {
    dhtTemperature_internal = 0.0;
    dhtHumidity_internal = 0.0;
  }
  
  // DHT22 Sensor 2 (External)
  if (dhtFound[1]) {
    dhtTemperature_external = dht2.getTemperature();
    dhtHumidity_external = dht2.getHumidity();
    if (isnan(dhtTemperature_external) || isnan(dhtHumidity_external)) {
      if (debugEnabled) {
        Serial.print("{\"type\":\"error\",\"sensor_type\":\"dht22\",\"sensor_id\":2,\"message\":\"read_failure\"}");
      }
      dhtTemperature_external = 0.0;
      dhtHumidity_external = 0.0;
    }
  } else {
    dhtTemperature_external = 0.0;
    dhtHumidity_external = 0.0;
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
  // PID control for hot plates using separate surface temperature variables
  // Hotplate 0: uses temp_hotplate1
  // Hotplate 1: uses temp_hotplate2
  
  // Hotplate 0 Control
  {    
    // Apply safety limits (always active, highest priority)
    if (temp_hotplate1 > MAX_TEMP) {
      digitalWrite(SSR_RELAY_1, LOW);
      hotPlateStates[0] = false;
      Serial.print("{\"type\":\"safety\",\"event\":\"over_temperature\",\"hotplate_id\":1,\"temperature\":");
      Serial.print(temp_hotplate1);
      Serial.println("}");
    }
    // Manual OFF state has highest priority (after safety)
    else if (manualHotPlateControl[0] && !hotPlateStates[0]) {
      digitalWrite(SSR_RELAY_1, LOW);
    }
    // Manual ON state
    else if (manualHotPlateControl[0] && hotPlateStates[0]) {
      digitalWrite(SSR_RELAY_1, HIGH);
    }
    // Automatic PID control mode
    else {
      pidInput0 = temp_hotplate1;
      
      if (temp_hotplate1 < targetTemperatures[0] - 15) {
          digitalWrite(SSR_RELAY_1, HIGH);
      }
      else {
        if (pidInput0 > (targetTemperatures[0] - 10)) {
            pid0.SetOutputLimits(0, WindowSize * 0.5);
        } else {
            pid0.SetOutputLimits(0, WindowSize);
        }
        
        if (pid0.Compute()) {
          if (pidOutput0 == WindowSize || pidOutput0 == 0) {
              // prevent integral accumulation
              pid0.SetTunings(kp1, 0, kd1);
          } 
          
          double rate = temp_hotplate1 - last_hotplate1Temp;
          last_hotplate1Temp = temp_hotplate1;

          // braking condition
          if (temp_hotplate1 > (targetTemperatures[0] - 5)) {
              if (rate > 0.15) {   // from your slope (~0.12–0.18)
                  pidOutput0 *= 0.25;
              }
          }

          unsigned long now = millis();
          // Start a new window if needed
          if (now - windowStartTime >= WindowSize) {
            windowStartTime += WindowSize;
          }

          // Time-proportional control
          if (pidOutput0 > (now - windowStartTime)) {
            digitalWrite(SSR_RELAY_1, HIGH);   // Heater ON
            hotPlateStates[0] = true;
          } else {
            digitalWrite(SSR_RELAY_1, LOW);    // Heater OFF
            hotPlateStates[0] = false;
          }
        }
      }
    }
  }
  
  // Hotplate 1 Control
  {  
    // Apply safety limits (always active, highest priority)
    if (temp_hotplate2 > MAX_TEMP) {
      digitalWrite(SSR_RELAY_2, LOW);
      hotPlateStates[1] = false;
      Serial.print("{\"type\":\"safety\",\"event\":\"over_temperature\",\"hotplate_id\":2,\"temperature\":");
      Serial.print(temp_hotplate2);
      Serial.println("}");
    }
    // Manual OFF state has highest priority (after safety)
    else if (manualHotPlateControl[1] && !hotPlateStates[1]) {
      digitalWrite(SSR_RELAY_2, LOW);
    }
    // Manual ON state
    else if (manualHotPlateControl[1] && hotPlateStates[1]) {
      digitalWrite(SSR_RELAY_2, HIGH);
    }
    // Automatic PID control mode
    else {
      pidInput1 = temp_hotplate2;
      if (temp_hotplate2 < targetTemperatures[1] - 15) {
          digitalWrite(SSR_RELAY_2, HIGH);
      }
      else {
        if (pidInput1 > (targetTemperatures[1] - 10)) {
            pid1.SetOutputLimits(0, WindowSize * 0.5);
        } else {
            pid1.SetOutputLimits(0, WindowSize);
        }

        if (pid1.Compute()) {
          
          if (pidOutput1 == WindowSize || pidOutput0 == 0) {
              // prevent integral accumulation
              pid0.SetTunings(kp1, 0, kd1);
          } 

          double rate = temp_hotplate2 - last_hotplate2Temp;
          last_hotplate2Temp = temp_hotplate2;

          // braking condition
          if (temp_hotplate2 > (targetTemperatures[1] - 5)) {
              if (rate > 0.15) {   // from your slope (~0.12–0.18)
                  pidOutput0 *= 0.25;
              }
          }

          unsigned long now = millis();
          // Start a new window if needed
          if (now - windowStartTime >= WindowSize) {
            windowStartTime += WindowSize;
          }

          // Time-proportional control
          if (pidOutput1 > (now - windowStartTime)) {
            digitalWrite(SSR_RELAY_2, HIGH);   // Heater ON
            hotPlateStates[1] = true;
          } else {
            digitalWrite(SSR_RELAY_2, LOW);    // Heater OFF
            hotPlateStates[1] = false;
          }
        }
      }
    }
  }
}

void processSerialCommands() {
  my_instrument.ProcessInput(Serial, "\n");
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
  
  // Add hotplate surface temperatures
  data["temp_hotplate1"] = temp_hotplate1;
  data["temp_hotplate2"] = temp_hotplate2;
  
  // Add BME280 temperature data (internal/external)
  data["bmpTemperature_internal"] = bmpTemperature_internal;
  data["bmpTemperature_external"] = bmpTemperature_external;
  
  // Add BME280 pressure data (internal/external)
  data["bmpPressure_internal"] = bmpPressure_internal;
  data["bmpPressure_external"] = bmpPressure_external;
  
  // Add DHT temperature data (internal/external)
  data["dhtTemperature_internal"] = dhtTemperature_internal;
  data["dhtTemperature_external"] = dhtTemperature_external;
  
  // Add DHT humidity data (internal/external)
  data["dhtHumidity_internal"] = dhtHumidity_internal;
  data["dhtHumidity_external"] = dhtHumidity_external;
  
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
