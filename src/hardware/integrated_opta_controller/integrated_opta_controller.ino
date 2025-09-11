/*
 * Integrated Arduino Opta Controller
 * Universal device controller for Relay, VICI Valve, and Masterflex Pump
 * 
 * Command Protocol: DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]
 * 
 * Device Types:
 * - REL_nn: Relay control (pins A0-A3)
 * - VICI_nn: VICI valve via RS485
 * - MFLEX_nn: Masterflex pump via RS485
 * 
 * Examples:
 * - REL_01:ON
 * - VICI_01:GOTO:A  
 * - MFLEX_01:SPEED:100.0:+
 * - STATUS (get all device statuses)
 * 
 * Author: Integrated Controller System
 * Version: 1.0
 */

#include <ArduinoRS485.h>
#include <ctype.h>

// ============================================================================
// CONFIGURATION
// ============================================================================

static const uint32_t SERIAL_BAUD = 115200;
static const uint16_t COMMAND_TIMEOUT = 2000;
static const uint16_t RESPONSE_TIMEOUT = 800;
static const uint16_t TX_GUARD_US = 2000;

// Device limits
static const uint8_t MAX_DEVICES = 16;
static const uint8_t MAX_RELAYS = 4;
static const uint8_t MAX_VICI = 8;
static const uint8_t MAX_MASTERFLEX = 8;

// ============================================================================
// DEVICE BASE CLASS AND TYPES
// ============================================================================

enum DeviceType {
  DEVICE_RELAY,
  DEVICE_VICI,
  DEVICE_MASTERFLEX
};

enum CommandResult {
  CMD_OK,
  CMD_ERROR,
  CMD_DATA
};

class Device {
public:
  char id[12];  // Increased size to handle longer device IDs
  DeviceType type;
  bool enabled;
  
  Device() : enabled(false) {
    id[0] = '\0';
  }
  
  virtual ~Device() {}
  virtual bool initialize() = 0;
  virtual CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) = 0;
  virtual bool getStatus(char* status, size_t statusSize) = 0;
};

// ============================================================================
// RELAY DEVICE CLASS
// ============================================================================

class RelayDevice : public Device {
private:
  uint8_t pin;
  uint8_t ledPin;
  bool state;

public:
  RelayDevice(const char* deviceId, uint8_t relayNum) {
    strncpy(id, deviceId, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    type = DEVICE_RELAY;
    state = false;
    
    // Map relay number to pins (1-4 -> A0-A3, LED_D0-LED_D3)
    switch(relayNum) {
      case 1: pin = D0; ledPin = LED_D0; break;
      case 2: pin = D1; ledPin = LED_D1; break;
      case 3: pin = D2; ledPin = LED_D2; break;
      case 4: pin = D3; ledPin = LED_D3; break;
      default: pin = D0; ledPin = LED_D0; break;
    }
  }
  
  bool initialize() override {
    pinMode(pin, OUTPUT);
    pinMode(ledPin, OUTPUT);
    digitalWrite(pin, LOW);
    digitalWrite(ledPin, LOW);
    state = false;
    enabled = true;
    return true;
  }
  
  CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) override {
    if (strcasecmp(command, "ON") == 0) {
      digitalWrite(pin, HIGH);
      digitalWrite(ledPin, HIGH);
      state = true;
      snprintf(response, responseSize, "Relay %s ON", id);
      return CMD_OK;
    }
    else if (strcasecmp(command, "OFF") == 0) {
      digitalWrite(pin, LOW);
      digitalWrite(ledPin, LOW);
      state = false;
      snprintf(response, responseSize, "Relay %s OFF", id);
      return CMD_OK;
    }
    else if (strcasecmp(command, "TOGGLE") == 0) {
      state = !state;
      digitalWrite(pin, state);
      digitalWrite(ledPin, state);
      snprintf(response, responseSize, "Relay %s %s", id, state ? "ON" : "OFF");
      return CMD_OK;
    }
    
    snprintf(response, responseSize, "Unknown relay command: %s", command);
    return CMD_ERROR;
  }
  
  bool getStatus(char* status, size_t statusSize) override {
    snprintf(status, statusSize, "%s:%s", id, state ? "ON" : "OFF");
    return true;
  }
};

// ============================================================================
// VICI VALVE DEVICE CLASS  
// ============================================================================

class ViciDevice : public Device {
private:
  char viciId;
  
  void setupViciRS485() {
    RS485.end();  // End current RS485 session
    RS485.begin(9600);  // 9600 baud, 8N1 (default)
    RS485.receive();
    delay(50);  // Allow RS485 to stabilize
  }
  
  void drainRx() {
    while (RS485.available()) (void)RS485.read();
  }
  
  void sendFrame(const char* core) {
    char frame[64];
    size_t n = snprintf(frame, sizeof(frame), "/%c%s\r", viciId, core);
    
    RS485.noReceive();
    RS485.beginTransmission();
    RS485.write((const uint8_t*)frame, n);
    RS485.flush();
    delayMicroseconds(1200);  // Use VICI-specific guard time
    RS485.endTransmission();
    RS485.receive();
  }
  
  bool readLine(char* out, size_t max, uint16_t totalTO = 600, uint16_t gapTO = 80) {
    uint32_t t0 = millis(), tLast = t0;
    size_t i = 0;
    if (max) out[0] = 0;

    while (millis() - t0 < totalTO) {
      while (RS485.available()) {
        int b = RS485.read();
        if (b < 0) break;
        tLast = millis();

        char c = (char)b;
        if (c == '\r') { if (i < max) out[i] = 0; return i > 0; }
        if (c == '\n') continue;
        if (i + 1 < max) out[i++] = c;
      }
      if (i > 0 && (millis() - tLast > gapTO)) { if (i < max) out[i] = 0; return true; }
    }
    if (i < max) out[i] = 0;
    return i > 0;
  }
  
  bool sendCommand(const char* core, char* resp = nullptr, size_t respMax = 0) {
    setupViciRS485();  // Configure RS485 for VICI protocol
    drainRx();
    sendFrame(core);
    if (!resp || respMax == 0) return true;
    return readLine(resp, respMax);
  }

public:
  ViciDevice(const char* deviceId, char valveId) {
    strncpy(id, deviceId, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    type = DEVICE_VICI;
    viciId = valveId;
  }
  
  bool initialize() override {
    // VICI initialization - RS485 will be configured per-command
    enabled = true;
    return true;
  }
  
  CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) override {
    char viciResponse[128];
    
    if (strcasecmp(command, "GOTO") == 0 && param1) {
      char gotoCmd[16];
      snprintf(gotoCmd, sizeof(gotoCmd), "GO%s", param1);
      if (sendCommand(gotoCmd)) {
        snprintf(response, responseSize, "VICI %s moved to %s", id, param1);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "TOGGLE") == 0) {
      if (sendCommand("TO")) {
        snprintf(response, responseSize, "VICI %s toggled", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "HOME") == 0) {
      if (sendCommand("HM")) {
        snprintf(response, responseSize, "VICI %s homed", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "POSITION") == 0) {
      if (sendCommand("CP", viciResponse, sizeof(viciResponse))) {
        snprintf(response, responseSize, "VICI %s position: %s", id, viciResponse);
        return CMD_DATA;
      }
    }
    else if (strcasecmp(command, "STATUS") == 0) {
      if (sendCommand("STAT", viciResponse, sizeof(viciResponse))) {
        snprintf(response, responseSize, "VICI %s status: %s", id, viciResponse);
        return CMD_DATA;
      }
    }
    else if (strcasecmp(command, "CW") == 0) {
      if (sendCommand("CW")) {
        snprintf(response, responseSize, "VICI %s moved CW", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "CCW") == 0) {
      if (sendCommand("CC")) {
        snprintf(response, responseSize, "VICI %s moved CCW", id);
        return CMD_OK;
      }
    }
    
    snprintf(response, responseSize, "VICI command failed or unknown: %s", command);
    return CMD_ERROR;
  }
  
  bool getStatus(char* status, size_t statusSize) override {
    char pos[32];
    if (sendCommand("CP", pos, sizeof(pos))) {
      snprintf(status, statusSize, "%s:POS_%s", id, pos);
    } else {
      snprintf(status, statusSize, "%s:UNKNOWN", id);
    }
    return true;
  }
};

// ============================================================================
// MASTERFLEX PUMP DEVICE CLASS
// ============================================================================

class MasterflexDevice : public Device {
private:
  char pumpId[4];
  bool initialized;
  
  enum ResponseType { RESP_NONE, RESP_LINE, RESP_ACK, RESP_NAK };
  
  void setupMasterflexRS485() {
    RS485.end();  // End current RS485 session
    RS485.begin(4800, SERIAL_7O1);  // 4800 baud, 7 data bits, odd parity, 1 stop bit
    RS485.receive();
    delay(50);  // Allow RS485 to stabilize
  }
  
  void drainRS485() {
    while (RS485.available()) (void)RS485.read();
  }
  
  void sendMasterflexFrame(const char* command) {
    char frame[64];
    int n = snprintf(frame, sizeof(frame), "\x02P%s%s\r", pumpId, command);
    
    drainRS485();
    RS485.noReceive();
    RS485.beginTransmission();
    RS485.write((uint8_t*)frame, n);
    RS485.flush();
    delayMicroseconds(2000);  // Use Masterflex-specific guard time
    RS485.endTransmission();
    RS485.receive();
  }
  
  ResponseType readMasterflexResponse(char* buffer, size_t maxLen, uint16_t timeout = 800) {
    uint32_t startTime = millis();
    size_t index = 0;
    
    if (maxLen > 0) buffer[0] = '\0';
    
    while (millis() - startTime < timeout) {
      while (RS485.available()) {
        int byte = RS485.read();
        if (byte < 0) break;
        
        if (byte == 0x06) return RESP_ACK;
        if (byte == 0x15) return RESP_NAK;
        
        if (byte == '\r') {
          if (index < maxLen) buffer[index] = '\0';
          return index > 0 ? RESP_LINE : RESP_NONE;
        }
        
        if (index + 1 < maxLen) {
          buffer[index++] = (char)byte;
        }
      }
    }
    
    if (index < maxLen) buffer[index] = '\0';
    return index > 0 ? RESP_LINE : RESP_NONE;
  }

public:
  MasterflexDevice(const char* deviceId, const char* masterflexId) {
    strncpy(id, deviceId, sizeof(id) - 1);
    id[sizeof(id) - 1] = '\0';
    type = DEVICE_MASTERFLEX;
    strncpy(pumpId, masterflexId, sizeof(pumpId) - 1);
    pumpId[sizeof(pumpId) - 1] = '\0';
    initialized = false;
  }
  
  bool initialize() override {
    // Masterflex initialization - RS485 will be configured per-command
    enabled = true;
    return true;
  }
  
  bool initializePump() {
    Serial.print("Initializing Masterflex pump ");
    Serial.print(id);
    Serial.println("...");
    
    setupMasterflexRS485();  // Configure RS485 for Masterflex protocol
    drainRS485();
    RS485.noReceive();
    RS485.beginTransmission();
    RS485.write((uint8_t)0x05);  // ENQ
    RS485.flush();
    delayMicroseconds(2000);  // Use Masterflex guard time
    RS485.endTransmission();
    RS485.receive();
    
    char response[96];
    ResponseType respType = readMasterflexResponse(response, sizeof(response), 1200);
    
    Serial.print("Init response type: ");
    Serial.print((int)respType);
    if (respType == RESP_LINE) {
      Serial.print(", content: ");
      Serial.println(response);
      
      // Check if we received pump identification (P?x format)
      if (strstr(response, "P?")) {
        Serial.print("Pump requesting ID assignment for ID ");
        Serial.println(pumpId);
        
        // Send satellite number assignment: <STX>P[nn]<CR>
        char assignFrame[16];
        int n = snprintf(assignFrame, sizeof(assignFrame), "\x02P%s\r", pumpId);
        
        drainRS485();
        RS485.noReceive();
        RS485.beginTransmission();
        RS485.write((uint8_t*)assignFrame, n);
        RS485.flush();
        delayMicroseconds(2000);  // Use Masterflex guard time
        RS485.endTransmission();
        RS485.receive();
        
        ResponseType ackType = readMasterflexResponse(response, sizeof(response), 800);
        Serial.print("ACK response type: ");
        Serial.println((int)ackType);
        
        if (ackType == RESP_ACK) {
          initialized = true;
          Serial.print("Pump ");
          Serial.print(id);
          Serial.println(" ID assigned successfully");
          return true;
        } else {
          Serial.print("Failed to assign pump ID (no ACK), got type: ");
          Serial.println((int)ackType);
        }
      } else {
        Serial.print("Expected P? response, got: ");
        Serial.println(response);
      }
    } else {
      Serial.println("No response to ENQ");
    }
    
    return false;
  }
  
  CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) override {
    if (strcasecmp(command, "INIT") == 0) {
      if (initializePump()) {
        snprintf(response, responseSize, "Masterflex %s initialized successfully", id);
        return CMD_OK;
      } else {
        snprintf(response, responseSize, "Failed to initialize Masterflex %s - check serial output for details", id);
        return CMD_ERROR;
      }
    }
    
    if (!initialized) {
      snprintf(response, responseSize, "Masterflex %s not initialized", id);
      return CMD_ERROR;
    }
    
    // Configure RS485 for Masterflex before all operations
    setupMasterflexRS485();
    
    char mfResponse[128];
    ResponseType respType;
    
    if (strcasecmp(command, "SPEED") == 0 && param1) {
      float rpm = atof(param1);
      char direction = (param2 && param2[0] == '-') ? '-' : '+';
      
      char speedCmd[32];
      if (abs(rpm) >= 1000) {
        snprintf(speedCmd, sizeof(speedCmd), "S%c%04d", direction, (int)rpm);
      } else {
        snprintf(speedCmd, sizeof(speedCmd), "S%c%06.1f", direction, rpm);
      }
      
      sendMasterflexFrame(speedCmd);
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s speed set to %c%.1f RPM", id, direction, rpm);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "START") == 0 || strcasecmp(command, "GO") == 0) {
      sendMasterflexFrame("G");
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s started", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "STOP") == 0 || strcasecmp(command, "HALT") == 0) {
      sendMasterflexFrame("H");
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s stopped", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "REV") == 0 && param1) {
      float revolutions = atof(param1);
      char revCmd[32];
      snprintf(revCmd, sizeof(revCmd), "V%08.2f", revolutions);
      
      sendMasterflexFrame(revCmd);
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s revolutions set to %.2f", id, revolutions);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "STATUS") == 0) {
      sendMasterflexFrame("I");
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_LINE) {
        snprintf(response, responseSize, "Masterflex %s status: %s", id, mfResponse);
        return CMD_DATA;
      }
    }
    else if (strcasecmp(command, "REMOTE") == 0) {
      sendMasterflexFrame("R");
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s remote mode enabled", id);
        return CMD_OK;
      }
    }
    else if (strcasecmp(command, "LOCAL") == 0) {
      sendMasterflexFrame("L");
      respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
      
      if (respType == RESP_ACK) {
        snprintf(response, responseSize, "Masterflex %s local mode enabled", id);
        return CMD_OK;
      }
    }
    
    snprintf(response, responseSize, "Masterflex command failed or unknown: %s", command);
    return CMD_ERROR;
  }
  
  bool getStatus(char* status, size_t statusSize) override {
    if (!initialized) {
      snprintf(status, statusSize, "%s:NOT_INIT", id);
      return true;
    }
    
    setupMasterflexRS485();  // Configure RS485 for Masterflex
    sendMasterflexFrame("I");
    char mfResponse[128];
    ResponseType respType = readMasterflexResponse(mfResponse, sizeof(mfResponse));
    
    if (respType == RESP_LINE) {
      snprintf(status, statusSize, "%s:ACTIVE", id);
    } else {
      snprintf(status, statusSize, "%s:UNKNOWN", id);
    }
    return true;
  }
};

// ============================================================================
// DEVICE MANAGER
// ============================================================================

class DeviceManager {
private:
  Device* devices[MAX_DEVICES];
  uint8_t deviceCount;

public:
  DeviceManager() : deviceCount(0) {
    for (uint8_t i = 0; i < MAX_DEVICES; i++) {
      devices[i] = nullptr;
    }
  }
  
  bool addDevice(Device* device) {
    if (deviceCount >= MAX_DEVICES) return false;
    
    devices[deviceCount] = device;
    deviceCount++;
    return device->initialize();
  }
  
  Device* findDevice(const char* deviceId) {
    for (uint8_t i = 0; i < deviceCount; i++) {
      if (devices[i] && strcasecmp(devices[i]->id, deviceId) == 0) {
        return devices[i];
      }
    }
    return nullptr;
  }
  
  void getAllStatus(char* statusBuffer, size_t bufferSize) {
    statusBuffer[0] = '\0';
    char deviceStatus[64];
    
    for (uint8_t i = 0; i < deviceCount; i++) {
      if (devices[i] && devices[i]->enabled) {
        if (devices[i]->getStatus(deviceStatus, sizeof(deviceStatus))) {
          if (strlen(statusBuffer) > 0) {
            strncat(statusBuffer, ", ", bufferSize - strlen(statusBuffer) - 1);
          }
          strncat(statusBuffer, deviceStatus, bufferSize - strlen(statusBuffer) - 1);
        }
      }
    }
  }
  
  uint8_t getDeviceCount() const { return deviceCount; }
};

// ============================================================================
// GLOBAL OBJECTS AND VARIABLES
// ============================================================================

DeviceManager deviceManager;
String serialBuffer = "";

// ============================================================================
// COMMAND PROCESSING
// ============================================================================

void parseCommand(const char* input, char* deviceId, char* command, char* param1, char* param2) {
  deviceId[0] = '\0';
  command[0] = '\0';
  param1[0] = '\0';
  param2[0] = '\0';
  
  char* inputCopy = strdup(input);
  if (!inputCopy) return;
  
  char* token = strtok(inputCopy, ":");
  if (token) strncpy(deviceId, token, 15);
  
  token = strtok(nullptr, ":");
  if (token) strncpy(command, token, 15);
  
  token = strtok(nullptr, ":");
  if (token) strncpy(param1, token, 31);
  
  token = strtok(nullptr, ":");
  if (token) strncpy(param2, token, 31);
  
  free(inputCopy);
}

void processSerialCommand(String commandStr) {
  commandStr.trim();
  
  if (commandStr.equalsIgnoreCase("STATUS")) {
    char allStatus[512];
    deviceManager.getAllStatus(allStatus, sizeof(allStatus));
    Serial.print("DATA: ");
    Serial.println(allStatus);
    return;
  }
  
  if (commandStr.equalsIgnoreCase("HELP")) {
    Serial.println("OK: Available commands:");
    Serial.println("  STATUS - Get all device statuses");
    Serial.println("  DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]");
    Serial.println("  Examples:");
    Serial.println("    REL_01:ON");
    Serial.println("    VICI_01:GOTO:A");
    Serial.println("    MFLEX_01:SPEED:100.0:+");
    return;
  }
  
  char deviceId[16], command[16], param1[32], param2[32];
  parseCommand(commandStr.c_str(), deviceId, command, param1, param2);
  
  if (strlen(deviceId) == 0 || strlen(command) == 0) {
    Serial.println("ERROR: Invalid command format. Use DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]");
    return;
  }
  
  Device* device = deviceManager.findDevice(deviceId);
  if (!device) {
    Serial.print("ERROR: Device not found: ");
    Serial.println(deviceId);
    return;
  }
  
  char response[256];
  CommandResult result = device->processCommand(command, param1, param2, response, sizeof(response));
  
  switch (result) {
    case CMD_OK:
      Serial.print("OK: ");
      Serial.println(response);
      break;
    case CMD_DATA:
      Serial.print("DATA: ");
      Serial.println(response);
      break;
    case CMD_ERROR:
      Serial.print("ERROR: ");
      Serial.println(response);
      break;
  }
}

// ============================================================================
// SETUP AND LOOP
// ============================================================================

void setup() {
  Serial.begin(SERIAL_BAUD);
  while (!Serial) { delay(10); }
  
  Serial.println("\n=== Integrated Arduino Opta Controller ===");
  Serial.println("Universal Device Controller v1.0");
  Serial.println("Supported: Relay, VICI Valve, Masterflex Pump");
  Serial.println("==========================================");
  
  // Initialize default devices
  // Relay devices (REL_01 to REL_04)
  for (uint8_t i = 1; i <= 4; i++) {
    char relayId[8];
    snprintf(relayId, sizeof(relayId), "REL_%02d", i);
    RelayDevice* relay = new RelayDevice(relayId, i);
    if (deviceManager.addDevice(relay)) {
      Serial.print("Initialized: ");
      Serial.println(relayId);
    }
  }
  
  // VICI valve device (VICI_01)
  ViciDevice* vici = new ViciDevice("VICI_01", '3');
  if (deviceManager.addDevice(vici)) {
    Serial.println("Initialized: VICI_01");
  }
  
  // Masterflex pump device (MFLEX_01) 
  MasterflexDevice* pump = new MasterflexDevice("MFLEX_01", "01");
  if (deviceManager.addDevice(pump)) {
    Serial.println("Initialized: MFLEX_01");
  }
  
  Serial.print("Total devices initialized: ");
  Serial.println(deviceManager.getDeviceCount());
  Serial.println("\nSend HELP for command list");
  Serial.println("Ready for commands...");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        processSerialCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
    }
  }
  
  // Keep RS485 in receive mode during idle
  RS485.receive();
}