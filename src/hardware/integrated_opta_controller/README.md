# Integrated Arduino Opta Controller

Universal device controller for Relay, VICI Valve, and Masterflex Pump using a single Arduino Opta with RS485 communication.

## Overview

This integrated controller unifies control of three different device types through a single serial command interface:
- **Relays**: Direct digital pin control (pins A0-A3)
- **VICI Valves**: RS485 communication (9600 baud, 8N1)  
- **Masterflex Pumps**: RS485 communication (4800 baud, 7O1)

## Hardware Setup

- **Arduino Opta** with RS485 capability
- **Relays**: Connected to pins A0-A3 with corresponding LEDs on LED_D0-LED_D3
- **VICI Valve**: RS485 connection (ID '3' by default)
- **Masterflex Pump**: RS485 connection (ID "01" by default)

## Device Configuration

The controller initializes with these default devices:
- `REL_01` to `REL_04`: Relay devices on pins A0-A3
- `VICI_01`: VICI valve with RS485 ID '3'
- `MFLEX_01`: Masterflex pump with RS485 ID "01"

## Command Protocol

### Format
```
DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]
```

### Global Commands
- `STATUS` - Get all device statuses
- `HELP` - Show command list and examples

### Relay Commands
- `REL_01:ON` - Turn relay on
- `REL_01:OFF` - Turn relay off
- `REL_01:TOGGLE` - Toggle relay state

### VICI Valve Commands
- `VICI_01:GOTO:A` - Move to position A
- `VICI_01:GOTO:B` - Move to position B
- `VICI_01:GOTO:1` - Move to position 1 (multiposition valves)
- `VICI_01:TOGGLE` - Toggle between positions
- `VICI_01:HOME` - Home the valve
- `VICI_01:CW` - Move clockwise
- `VICI_01:CCW` - Move counterclockwise
- `VICI_01:POSITION` - Get current position
- `VICI_01:STATUS` - Get valve status

### Masterflex Pump Commands
- `MFLEX_01:INIT` - Initialize pump (required first)
- `MFLEX_01:SPEED:100.0:+` - Set speed to +100.0 RPM
- `MFLEX_01:SPEED:50.0:-` - Set speed to -50.0 RPM (reverse)
- `MFLEX_01:START` or `MFLEX_01:GO` - Start pump
- `MFLEX_01:STOP` or `MFLEX_01:HALT` - Stop pump
- `MFLEX_01:REV:10.0` - Set revolution count
- `MFLEX_01:STATUS` - Get pump status
- `MFLEX_01:REMOTE` - Enable remote mode
- `MFLEX_01:LOCAL` - Enable local mode

## Response Formats

- `OK: <message>` - Successful command execution
- `DATA: <data>` - Response with data (STATUS, POSITION, etc.)
- `ERROR: <message>` - Command failed or unknown

## RS485 Communication

The controller automatically switches RS485 protocols for different devices:
- **VICI**: 9600 baud, 8 data bits, no parity, 1 stop bit
- **Masterflex**: 4800 baud, 7 data bits, odd parity, 1 stop bit

Each device reconfigures the RS485 interface before communication to ensure proper protocol compliance.

## Initialization Sequence

1. **Relays**: Auto-initialize on startup
2. **VICI Valve**: Auto-initialize on startup  
3. **Masterflex Pump**: Requires manual initialization with `MFLEX_01:INIT`

### Masterflex Initialization
The Masterflex pump requires a specific initialization sequence:
1. Send ENQ (0x05) to pump
2. Pump responds with "P?" requesting ID assignment
3. Controller sends satellite ID assignment
4. Pump acknowledges with ACK (0x06)
5. Pump is ready for commands

## Serial Configuration

- **Baud Rate**: 115200
- **Termination**: Carriage return (`\r`) or newline (`\n`)
- **Timeout**: 2000ms for commands, 800ms for responses

## Example Usage

```
STATUS
DATA: REL_01:OFF, REL_02:OFF, REL_03:OFF, REL_04:OFF, VICI_01:POS_A, MFLEX_01:NOT_INIT

MFLEX_01:INIT
OK: Masterflex MFLEX_01 initialized successfully

REL_01:ON
OK: Relay REL_01 ON

VICI_01:GOTO:B
OK: VICI VICI_01 moved to B

MFLEX_01:SPEED:100.0:+
OK: Masterflex MFLEX_01 speed set to +100.0 RPM

MFLEX_01:START
OK: Masterflex MFLEX_01 started
```

## Troubleshooting

### Common Issues

1. **Device not found**: Check device ID spelling and case sensitivity
2. **VICI no response**: Verify RS485 wiring and device ID setting
3. **Masterflex not initializing**: Ensure pump is powered and in correct mode
4. **RS485 conflicts**: Controller handles protocol switching automatically

### Debug Output

The controller provides detailed debug output for Masterflex initialization:
```
Initializing Masterflex pump MFLEX_01...
Init response type: 1, content: P?0
Pump requesting ID assignment for ID 01
ACK response type: 2  
Pump MFLEX_01 ID assigned successfully
```

## Device Limits

- Maximum devices: 16 total
- Maximum relays: 4 (REL_01 to REL_04)
- Maximum VICI valves: 8
- Maximum Masterflex pumps: 8

## Files

- `integrated_opta_controller.ino` - Main Arduino sketch (754 lines)
- Device classes: RelayDevice, ViciDevice, MasterflexDevice
- Communication protocols: RS485 switching, timeout handling
- Command parser: Case-insensitive with parameter support