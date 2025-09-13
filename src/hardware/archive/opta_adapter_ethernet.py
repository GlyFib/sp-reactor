#!/usr/bin/env python3
"""
Opta Ethernet Hardware Adapter

Communicates with the Arduino sketch `integrated_opta_controller/integrated_opta_controller_ethernet.ino`
over TCP (default 192.168.0.100:502) using the integrated command protocol:

  - Global: STATUS, HELP
  - Relay:  REL_01:ON|OFF|TOGGLE
  - VICI:   VICI_01:GOTO:A|B|<n>, POSITION, TOGGLE, HOME, STATUS
  - Pump:   MFLEX_01:INIT, SPEED:<rpm>:+|-, START|GO, STOP|HALT, REV:<count>, STATUS, REMOTE, LOCAL

This adapter mirrors the high-level interface expected by code that previously used the
serial-based adapter, but transports commands via TCP sockets.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
import socket
import time


@dataclass
class OptaEthernetConfig:
    host: str = "192.168.0.100"
    port: int = 502
    timeout: float = 5.0  # socket read timeout in seconds
    connect_timeout: float = 5.0
    vici_id: str = "VICI_01"
    pump_id: str = "MFLEX_01"
    solenoid_relay_id: str = "REL_04"
    ml_per_rev: float = 0.8
    default_rpm_direction: str = "+"  # '+' forward / '-' reverse


class OptaEthernetHardwareAdapter:
    """Ethernet adapter for the integrated Opta controller."""

    is_opta_adapter = True

    def __init__(self, config: Optional[OptaEthernetConfig] = None):
        self.config = config or OptaEthernetConfig()
        self._sock: Optional[socket.socket] = None
        self._connected = False

    # -------------------------------
    # Connection management
    # -------------------------------
    def connect(self) -> bool:
        if self._connected:
            return True
        try:
            s = socket.create_connection((self.config.host, self.config.port), timeout=self.config.connect_timeout)
            s.settimeout(self.config.timeout)
            self._sock = s
            self._connected = True

            # Basic handshake: ask for status
            _ = self.get_status()
            return True
        except OSError:
            self._sock = None
            self._connected = False
            return False

    def disconnect(self):
        try:
            if self._sock:
                try:
                    # Best-effort to stop pump and turn off solenoid
                    self.pump_stop()
                    self.solenoid_off()
                except Exception:
                    pass
                self._sock.close()
        finally:
            self._sock = None
            self._connected = False

    # -------------------------------
    # Command transport
    # -------------------------------
    def _ensure_conn(self) -> bool:
        return self._connected or self.connect()

    def _readline(self) -> Optional[str]:
        if not self._sock:
            return None
        chunks = []
        try:
            while True:
                b = self._sock.recv(1)
                if not b:
                    break
                c = b.decode('utf-8', errors='ignore')
                if c in ['\n', '\r']:
                    if chunks:
                        return ''.join(chunks).strip()
                    else:
                        # skip empty line
                        continue
                chunks.append(c)
        except socket.timeout:
            return ''.join(chunks).strip() if chunks else None
        except OSError:
            return None
        return ''.join(chunks).strip() if chunks else None

    def _send_command(self, command: str) -> Optional[str]:
        if not self._ensure_conn():
            return None
        assert self._sock is not None
        try:
            data = (command.strip() + "\n").encode('utf-8')
            self._sock.sendall(data)
            return self._readline()
        except OSError:
            return None

    # -------------------------------
    # High-level operations
    # -------------------------------
    def get_status(self) -> Optional[str]:
        return self._send_command("STATUS")

    # Valve
    def move_valve(self, position: int) -> bool:
        resp = self._send_command(f"{self.config.vici_id}:GOTO:{position}")
        return self._ok(resp)

    # Solenoid
    def solenoid_on(self) -> bool:
        return self._ok(self._send_command(f"{self.config.solenoid_relay_id}:ON"))

    def solenoid_off(self) -> bool:
        return self._ok(self._send_command(f"{self.config.solenoid_relay_id}:OFF"))

    def solenoid_drain(self, seconds: float) -> bool:
        if not self.solenoid_on():
            return False
        time.sleep(max(0.0, float(seconds)))
        # Even if off fails, report True because drain happened
        _ = self.solenoid_off()
        return True

    # Pump
    def pump_init(self) -> bool:
        return self._ok(self._send_command(f"{self.config.pump_id}:INIT"))

    def pump_set_speed(self, rpm: float, direction: Optional[str] = None) -> bool:
        dir_sym = self._dir_symbol(direction)
        return self._ok(self._send_command(f"{self.config.pump_id}:SPEED:{float(rpm)}:{dir_sym}"))

    def pump_set_revolutions(self, revolutions: float) -> bool:
        return self._ok(self._send_command(f"{self.config.pump_id}:REV:{float(revolutions)}"))

    def pump_start(self) -> bool:
        return self._ok(self._send_command(f"{self.config.pump_id}:START"))

    def pump_stop(self) -> bool:
        return self._ok(self._send_command(f"{self.config.pump_id}:STOP"))

    def pump_dispense_ml(self, volume_ml: float, flow_rate_ml_min: float, direction: str = "+") -> bool:
        # Convert to revolutions and rpm using ml/rev
        ml_per_rev = max(1e-9, float(self.config.ml_per_rev))
        revolutions = max(0.0, float(volume_ml) / ml_per_rev)
        rpm = float(flow_rate_ml_min) / ml_per_rev

        if not self.pump_set_speed(rpm, direction):
            return False
        if not self.pump_set_revolutions(revolutions):
            return False
        if not self.pump_start():
            return False
        return True

    # Emergency
    def emergency_stop(self) -> bool:
        ok = True
        try:
            ok &= self.pump_stop()
        finally:
            ok &= self.solenoid_off()
        return bool(ok)

    # -------------------------------
    # Helpers
    # -------------------------------
    def _ok(self, resp: Optional[str]) -> bool:
        if not resp:
            return False
        r = resp.strip().upper()
        if r.startswith("OK:") or r.startswith("DATA:"):
            return True
        # Be tolerant for some pump responses
        for pat in ("ACK", "STARTED", "STOPPED"):
            if pat in r:
                return True
        return False

    def _dir_symbol(self, direction: Optional[str]) -> str:
        d = (direction or self.config.default_rpm_direction).strip()
        if not d:
            return self.config.default_rpm_direction
        dlow = d.lower()
        if dlow.startswith("-") or dlow.startswith("counter") or dlow.startswith("rev") or dlow == "ccw":
            return "-"
        if dlow.startswith("+") or dlow.startswith("clock") or dlow.startswith("forw") or dlow == "cw":
            return "+"
        return self.config.default_rpm_direction


# Convenience factory
def create_default_adapter(host: str = "192.168.0.100", port: int = 502) -> OptaEthernetHardwareAdapter:
    return OptaEthernetHardwareAdapter(OptaEthernetConfig(host=host, port=port))


if __name__ == "__main__":
    # Basic smoke test (no network calls in this environment)
    adapter = create_default_adapter()
    print("Adapter configured for", adapter.config.host, adapter.config.port)
