/*
 * Integrated Arduino Opta Controller (Ethernet)
 * Location: integrated_opta_controller_ethernet/
 * Universal device controller for Relay, VICI Valve, and Masterflex Pump
 * over a simple TCP text protocol.
 *
 * Command Protocol: DEVICE_ID:COMMAND[:PARAM1[:PARAM2]] or global STATUS/HELP
 *
 * Device Types:
 * - REL_nn: Relay control (D0-D3 with LED_D0-LED_D3)
 * - VICI_nn: VICI valve via RS485 (9600 8N1)
 * - MFLEX_nn: Masterflex pump via RS485 (4800 7O1)
 */

#include <ArduinoRS485.h>
#include <Ethernet.h>

// =============================
// Ethernet configuration
// =============================
byte mac[]     = { 0xDE, 0xAD, 0xBE, 0xEF, 0xFE, 0xED };
IPAddress ip(192, 168, 0, 100);
IPAddress gateway(192, 168, 0, 1);
IPAddress subnet(255, 255, 255, 0);

const uint16_t SERVER_PORT = 502; // TCP port
EthernetServer server(SERVER_PORT);

// =============================
// Serial configuration
// =============================
static const uint32_t SERIAL_BAUD = 115200;

// =============================
// Limits
// =============================
static const uint8_t MAX_DEVICES = 16;

// =============================
// Device base
// =============================
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
  char id[12];
  DeviceType type;
  bool enabled;

  Device() : type(DEVICE_RELAY), enabled(false) { id[0] = '\0'; }
  virtual ~Device() {}
  virtual bool initialize() = 0;
  virtual CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) = 0;
  virtual bool getStatus(char* status, size_t statusSize) = 0;
};

// =============================
// Relay device
// =============================
class RelayDevice : public Device {
private:
  uint8_t pin;
  uint8_t ledPin;
  bool state;

public:
  RelayDevice(const char* deviceId, uint8_t relayNum) : pin(D0), ledPin(LED_D0), state(false) {
    strncpy(id, deviceId, sizeof(id) - 1); id[sizeof(id) - 1] = '\0';
    type = DEVICE_RELAY;
    switch (relayNum) {
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

  CommandResult processCommand(const char* command, const char* /*param1*/, const char* /*param2*/, char* response, size_t responseSize) override {
    if (strcasecmp(command, "ON") == 0) {
      state = true; digitalWrite(pin, HIGH); digitalWrite(ledPin, HIGH);
      snprintf(response, responseSize, "Relay %s ON", id);
      return CMD_OK;
    }
    if (strcasecmp(command, "OFF") == 0) {
      state = false; digitalWrite(pin, LOW); digitalWrite(ledPin, LOW);
      snprintf(response, responseSize, "Relay %s OFF", id);
      return CMD_OK;
    }
    if (strcasecmp(command, "TOGGLE") == 0) {
      state = !state; digitalWrite(pin, state); digitalWrite(ledPin, state);
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

// =============================
// VICI valve device (RS485 9600 8N1)
// =============================
class ViciDevice : public Device {
private:
  char viciId;

  void setupViciRS485() {
    RS485.end();
    RS485.begin(9600); // 8N1 default
    RS485.receive();
    delay(30);
  }

  void drainRx() { while (RS485.available()) (void)RS485.read(); }

  void sendFrame(const char* core) {
    char frame[64];
    size_t n = snprintf(frame, sizeof(frame), "/%c%s\r", viciId, core);
    RS485.noReceive();
    RS485.beginTransmission();
    RS485.write((const uint8_t*)frame, n);
    RS485.flush();
    delayMicroseconds(1200);
    RS485.endTransmission();
    RS485.receive();
  }

  bool readLine(char* out, size_t max, uint16_t totalTO = 600, uint16_t gapTO = 80) {
    uint32_t t0 = millis(), tLast = t0; size_t i = 0; if (max) out[0] = 0;
    while (millis() - t0 < totalTO) {
      while (RS485.available()) {
        int b = RS485.read(); if (b < 0) break; tLast = millis();
        char c = (char)b; if (c == '\r') { if (i < max) out[i] = 0; return i > 0; }
        if (c == '\n') continue; if (i + 1 < max) out[i++] = c;
      }
      if (i > 0 && (millis() - tLast > gapTO)) { if (i < max) out[i] = 0; return true; }
    }
    if (i < max) out[i] = 0; return i > 0;
  }

  bool sendCommand(const char* core, char* resp = nullptr, size_t respMax = 0) {
    setupViciRS485(); drainRx(); sendFrame(core);
    if (!resp || respMax == 0) return true; return readLine(resp, respMax);
  }

public:
  ViciDevice(const char* deviceId, char valveId) : viciId(valveId) {
    strncpy(id, deviceId, sizeof(id) - 1); id[sizeof(id) - 1] = '\0';
    type = DEVICE_VICI;
  }

  bool initialize() override { enabled = true; return true; }

  CommandResult processCommand(const char* command, const char* param1, const char* /*param2*/, char* response, size_t responseSize) override {
    char viciResp[128];
    if (strcasecmp(command, "GOTO") == 0 && param1) {
      char gotoCmd[16]; snprintf(gotoCmd, sizeof(gotoCmd), "GO%s", param1);
      if (sendCommand(gotoCmd)) { snprintf(response, responseSize, "VICI %s moved to %s", id, param1); return CMD_OK; }
    } else if (strcasecmp(command, "TOGGLE") == 0) {
      if (sendCommand("TO")) { snprintf(response, responseSize, "VICI %s toggled", id); return CMD_OK; }
    } else if (strcasecmp(command, "HOME") == 0) {
      if (sendCommand("HM")) { snprintf(response, responseSize, "VICI %s homed", id); return CMD_OK; }
    } else if (strcasecmp(command, "POSITION") == 0) {
      if (sendCommand("CP", viciResp, sizeof(viciResp))) { snprintf(response, responseSize, "VICI %s position: %s", id, viciResp); return CMD_DATA; }
    } else if (strcasecmp(command, "STATUS") == 0) {
      if (sendCommand("STAT", viciResp, sizeof(viciResp))) { snprintf(response, responseSize, "VICI %s status: %s", id, viciResp); return CMD_DATA; }
    } else if (strcasecmp(command, "CW") == 0) {
      if (sendCommand("CW")) { snprintf(response, responseSize, "VICI %s moved CW", id); return CMD_OK; }
    } else if (strcasecmp(command, "CCW") == 0) {
      if (sendCommand("CC")) { snprintf(response, responseSize, "VICI %s moved CCW", id); return CMD_OK; }
    }
    snprintf(response, responseSize, "VICI command failed or unknown: %s", command); return CMD_ERROR;
  }

  bool getStatus(char* status, size_t statusSize) override {
    char pos[32]; if (sendCommand("CP", pos, sizeof(pos))) snprintf(status, statusSize, "%s:POS_%s", id, pos); else snprintf(status, statusSize, "%s:UNKNOWN", id); return true;
  }
};

// =============================
// Masterflex pump device (RS485 4800 7O1)
// =============================
class MasterflexDevice : public Device {
private:
  char pumpId[4];
  bool initialized;

  enum ResponseType { RESP_NONE, RESP_LINE, RESP_ACK, RESP_NAK };

  void setupMasterflexRS485() {
    RS485.end();
    RS485.begin(4800, SERIAL_7O1);
    RS485.receive();
    delay(30);
  }

  void drainRS485() { while (RS485.available()) (void)RS485.read(); }

  void sendMasterflexFrame(const char* command) {
    char frame[64];
    int n = snprintf(frame, sizeof(frame), "\x02P%s%s\r", pumpId, command);
    drainRS485(); RS485.noReceive(); RS485.beginTransmission();
    RS485.write((uint8_t*)frame, n); RS485.flush(); delayMicroseconds(2000);
    RS485.endTransmission(); RS485.receive();
  }

  ResponseType readMasterflexResponse(char* buffer, size_t maxLen, uint16_t timeout = 800) {
    uint32_t start = millis(); size_t idx = 0; if (maxLen) buffer[0] = 0;
    while (millis() - start < timeout) {
      while (RS485.available()) {
        int b = RS485.read(); if (b < 0) break; char c = (char)b;
        if (c == '\x06') { if (maxLen) buffer[0] = 0; return RESP_ACK; }
        if (c == '\x15') { if (maxLen) buffer[0] = 0; return RESP_NAK; }
        if (c == '\r') { if (idx < maxLen) buffer[idx] = 0; return idx ? RESP_LINE : RESP_NONE; }
        if (c == '\n') continue; if (idx + 1 < maxLen) buffer[idx++] = c;
      }
    }
    return RESP_NONE;
  }

public:
  MasterflexDevice(const char* deviceId, const char* mfId) : initialized(false) {
    strncpy(id, deviceId, sizeof(id) - 1); id[sizeof(id) - 1] = '\0';
    strncpy(pumpId, mfId, sizeof(pumpId) - 1); pumpId[sizeof(pumpId) - 1] = '\0';
    type = DEVICE_MASTERFLEX;
  }

  bool initialize() override { enabled = true; initialized = false; return true; }

  CommandResult processCommand(const char* command, const char* param1, const char* param2, char* response, size_t responseSize) override {
    setupMasterflexRS485(); char mfResp[128]; ResponseType r = RESP_NONE;

    if (strcasecmp(command, "INIT") == 0) {
      // ENQ handshake
      RS485.noReceive(); RS485.beginTransmission(); RS485.write((uint8_t)0x05); RS485.flush(); delayMicroseconds(1200); RS485.endTransmission(); RS485.receive();
      r = readMasterflexResponse(mfResp, sizeof(mfResp), 1500);
      if (r == RESP_LINE && strncmp(mfResp, "P?", 2) == 0) {
        // Assign ID
        char idFrame[8]; snprintf(idFrame, sizeof(idFrame), "I%s", pumpId);
        sendMasterflexFrame(idFrame);
        r = readMasterflexResponse(mfResp, sizeof(mfResp));
        if (r == RESP_ACK) { initialized = true; snprintf(response, responseSize, "Masterflex %s initialized", id); return CMD_OK; }
      }
      snprintf(response, responseSize, "Masterflex %s init failed", id); return CMD_ERROR;
    }
    else if (strcasecmp(command, "SPEED") == 0 && param1) {
      float rpm = atof(param1); char dir = '+'; if (param2 && param2[0]) dir = param2[0];
      char speedCmd[32]; if (abs(rpm) >= 1000) snprintf(speedCmd, sizeof(speedCmd), "S%c%04d", dir, (int)rpm); else snprintf(speedCmd, sizeof(speedCmd), "S%c%06.1f", dir, rpm);
      sendMasterflexFrame(speedCmd); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s speed set to %c%.1f RPM", id, dir, rpm); return CMD_OK; }
    }
    else if (strcasecmp(command, "START") == 0 || strcasecmp(command, "GO") == 0) {
      sendMasterflexFrame("G"); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s started", id); return CMD_OK; }
    }
    else if (strcasecmp(command, "STOP") == 0 || strcasecmp(command, "HALT") == 0) {
      sendMasterflexFrame("H"); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s stopped", id); return CMD_OK; }
    }
    else if (strcasecmp(command, "REV") == 0 && param1) {
      float rev = atof(param1); char revCmd[32]; snprintf(revCmd, sizeof(revCmd), "V%08.2f", rev);
      sendMasterflexFrame(revCmd); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s revolutions set to %.2f", id, rev); return CMD_OK; }
    }
    else if (strcasecmp(command, "STATUS") == 0) {
      sendMasterflexFrame("I"); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_LINE) { snprintf(response, responseSize, "Masterflex %s status: %s", id, mfResp); return CMD_DATA; }
    }
    else if (strcasecmp(command, "REMOTE") == 0) {
      sendMasterflexFrame("R"); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s remote mode enabled", id); return CMD_OK; }
    }
    else if (strcasecmp(command, "LOCAL") == 0) {
      sendMasterflexFrame("L"); r = readMasterflexResponse(mfResp, sizeof(mfResp)); if (r == RESP_ACK) { snprintf(response, responseSize, "Masterflex %s local mode enabled", id); return CMD_OK; }
    }

    snprintf(response, responseSize, "Masterflex command failed or unknown: %s", command);
    return CMD_ERROR;
  }

  bool getStatus(char* status, size_t statusSize) override {
    if (!initialized) { snprintf(status, statusSize, "%s:NOT_INIT", id); return true; }
    setupMasterflexRS485(); sendMasterflexFrame("I"); char mfResp[64]; ResponseType r = readMasterflexResponse(mfResp, sizeof(mfResp));
    if (r == RESP_LINE) snprintf(status, statusSize, "%s:ACTIVE", id); else snprintf(status, statusSize, "%s:UNKNOWN", id);
    return true;
  }
};

// =============================
// Device manager and command parsing
// =============================
class DeviceManager {
private:
  Device* devices[MAX_DEVICES];
  uint8_t count;
public:
  DeviceManager() : count(0) { for (uint8_t i=0;i<MAX_DEVICES;i++) devices[i]=nullptr; }
  bool addDevice(Device* d){ if (count>=MAX_DEVICES) return false; devices[count++]=d; return d->initialize(); }
  Device* find(const char* deviceId){ for(uint8_t i=0;i<count;i++){ if(devices[i] && strcasecmp(devices[i]->id, deviceId)==0) return devices[i]; } return nullptr; }
  uint8_t size() const { return count; }
  void allStatus(char* out, size_t max){ if (max) out[0]=0; char buf[96]; for(uint8_t i=0;i<count;i++){ if(!devices[i]) continue; if(i>0) strlcat(out, ", ", max); devices[i]->getStatus(buf, sizeof(buf)); strlcat(out, buf, max);} }
};

DeviceManager deviceManager;

static String serialBuffer;

void parseCommand(const char* input, char* deviceId, char* command, char* param1, char* param2) {
  deviceId[0] = command[0] = param1[0] = param2[0] = 0;
  char* copy = strdup(input); if (!copy) return;
  for (char* p = copy; *p; ++p) if (*p=='\r' || *p=='\n') *p=0;
  char* t = strtok(copy, ":"); if (t) strncpy(deviceId, t, 15);
  t = strtok(nullptr, ":"); if (t) strncpy(command, t, 15);
  t = strtok(nullptr, ":"); if (t) strncpy(param1, t, 31);
  t = strtok(nullptr, ":"); if (t) strncpy(param2, t, 31);
  free(copy);
}

String handleCommandString(const String& commandStr) {
  String cmd = commandStr; cmd.trim();
  if (cmd.equalsIgnoreCase("STATUS")) {
    char all[512]; deviceManager.allStatus(all, sizeof(all));
    String resp = "DATA: "; resp += all; return resp;
  }
  if (cmd.equalsIgnoreCase("HELP")) {
    return String("OK: Commands -> STATUS; DEVICE_ID:COMMAND[:PARAM1[:PARAM2]] e.g. REL_01:ON, VICI_01:GOTO:A, MFLEX_01:SPEED:100.0:+");
  }
  char deviceId[16], command[16], p1[32], p2[32];
  parseCommand(cmd.c_str(), deviceId, command, p1, p2);
  if (!deviceId[0] || !command[0]) return String("ERROR: Invalid command format. Use DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]");
  Device* dev = deviceManager.find(deviceId);
  if (!dev) { String r = "ERROR: Device not found: "; r += deviceId; return r; }
  char response[256];
  CommandResult res = dev->processCommand(command, p1, p2, response, sizeof(response));
  String prefix = (res==CMD_OK?"OK: ":(res==CMD_DATA?"DATA: ":"ERROR: "));
  String out = prefix; out += response; return out;
}

void handleEthernetClient(EthernetClient& client) {
  String cmd = "";
  while (client.connected()) {
    while (client.available()) {
      char c = client.read();
      if (c == '\n' || c == '\r') {
        if (cmd.length() > 0) {
          String resp = handleCommandString(cmd);
          client.println(resp);
          cmd = "";
        }
      } else {
        cmd += c;
      }
    }
  }
  client.stop();
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  // CRITICAL FIX: Do not wait for Serial connection - this was preventing headless ethernet operation
  // The ethernet interface must initialize independently of USB serial connection
  // Previous problematic code: while (!Serial && (millis() - _t0) < 1000) { ... }
  
  // Initialize devices immediately (no serial dependency)
  for (uint8_t i=1;i<=4;i++){ char id[8]; snprintf(id, sizeof(id), "REL_%02d", i); deviceManager.addDevice(new RelayDevice(id, i)); }
  deviceManager.addDevice(new ViciDevice("VICI_01", '3'));
  deviceManager.addDevice(new MasterflexDevice("MFLEX_01", "01"));

  // Start Ethernet immediately (no serial dependency)
  Ethernet.begin(mac, ip, gateway, subnet);
  server.begin();
  
  // Only log to serial if connection is available (non-blocking)
  if (Serial) {
    Serial.println("\n=== Integrated Opta Controller (Ethernet) ===");
    Serial.println("Devices: Relays, VICI, Masterflex over TCP");
    Serial.print("Devices initialized: "); Serial.println(deviceManager.size());
    
    if (Ethernet.hardwareStatus() == EthernetNoHardware) {
      Serial.println("ERROR: Ethernet hardware not found");
    }
    if (Ethernet.linkStatus() == LinkOFF) {
      Serial.println("WARNING: Ethernet cable is not connected");
    }
    Serial.print("Listening on "); Serial.print(Ethernet.localIP()); Serial.print(":"); Serial.println(SERVER_PORT);
    Serial.println("Type HELP over TCP or serial for commands.");
  }
}

void loop() {
  // Handle Ethernet (primary interface)
  EthernetClient client = server.available();
  if (client) { handleEthernetClient(client); }
  Ethernet.maintain();

  // Handle serial (debug/secondary interface) - only if connection exists
  if (Serial && Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialBuffer.length() > 0) {
        String resp = handleCommandString(serialBuffer);
        Serial.println(resp);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
    }
  }

  // Keep RS485 in receive between commands
  RS485.receive();
}
