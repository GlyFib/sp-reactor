#!/usr/bin/env python3
"""
Opta Ethernet Hardware Adapter

Communicates with the Arduino sketch `integrated_opta_controller/integrated_opta_controller_ethernet.ino`
over TCP (default 192.168.0.100:502) using the integrated command protocol.

This adapter provides the same interface as the original serial adapter but uses ethernet communication.
Simply change the configuration to use host/port instead of serial_port.
"""

from dataclasses import dataclass
from typing import Optional
import socket
import time
import logging


@dataclass
class OptaConfig:
    """
    Configuration for the Opta ethernet adapter.
    Note: Uses host/port for ethernet instead of serial_port for serial communication.
    Supports both serial_port (for backward compatibility) and host parameters.
    """
    # Ethernet connection (replaces serial_port)
    host: str = "192.168.0.100"
    port: int = 502
    timeout: float = 5.0  # socket read timeout in seconds
    connect_timeout: float = 5.0
    
    # Device configuration (same as serial version)
    vici_id: str = "VICI_01"
    pump_id: str = "MFLEX_01"
    solenoid_relay_id: str = "REL_04"
    ml_per_rev: float = 0.8
    default_rpm_direction: str = "+"
    
    # Compatibility fields for code that might check these
    inter_device_delay: float = 0.5  # Reduced for ethernet
    command_retry_count: int = 3
    command_timeout: float = 5.0
    connection_warmup_delay: float = 1.0  # Reduced for ethernet
    pump_settling_delay: float = 0.5  # Reduced for ethernet
    
    # Backward compatibility: accept serial_port as alias for host
    serial_port: Optional[str] = None
    
    def __post_init__(self):
        # If serial_port is provided and looks like an IP address, use it as host
        if self.serial_port and ('.' in str(self.serial_port) or str(self.serial_port).replace('.', '').isdigit()):
            self.host = str(self.serial_port)


class OptaHardwareAdapter:
    """Ethernet adapter for the integrated Opta controller with same interface as serial version."""

    is_opta_adapter = True

    def __init__(self, config: Optional[OptaConfig] = None):
        self.config = config or OptaConfig()
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._logger = logging.getLogger(__name__)
        self._last_device_used = None  # For compatibility

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
            status = self.get_status()
            if status:
                self._logger.info(f"🔗 Connected to Opta at {self.config.host}:{self.config.port}")
                # Initialize pump
                self.pump_init()
                return True
            else:
                self._logger.error("Failed handshake with Opta")
                self.disconnect()
                return False
        except OSError as e:
            self._logger.error(f"Failed to connect to {self.config.host}:{self.config.port} - {e}")
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
            self._connected = False  # Mark as disconnected on socket error
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
            self._connected = False  # Mark as disconnected on socket error
            return None

    # -------------------------------
    # Device operations (same interface as serial version)
    # -------------------------------
    def get_status(self) -> Optional[str]:
        return self._send_command("STATUS")

    # Valve operations
    def move_valve(self, position: int) -> bool:
        """Move VICI valve to a numeric position (1..N)."""
        self._apply_inter_device_delay("valve")
        resp = self._send_command(f"{self.config.vici_id}:GOTO:{position}")
        return self._ok(resp)

    # Pump operations
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

    def pump_dispense_ml(self, volume_ml: float, flow_rate_ml_min: float, direction: str = "clockwise") -> bool:
        """Enhanced pump control with proper timing and stop functionality."""
        if not self._ensure_conn():
            return False
        
        self._apply_inter_device_delay("pump")
        
        # Convert to revolutions and rpm using ml/rev
        ml_per_rev = max(1e-9, float(self.config.ml_per_rev))
        revolutions = max(0.0, float(volume_ml) / ml_per_rev)
        rpm = float(flow_rate_ml_min) / ml_per_rev
        dir_sym = self._dir_symbol(direction)

        # Set speed
        if not self.pump_set_speed(rpm, direction):
            return False
        
        # Set revolutions
        if not self.pump_set_revolutions(revolutions):
            return False
        
        # Start pump
        if not self.pump_start():
            return False
        
        # Wait for completion
        expected_minutes = revolutions / (rpm if rpm > 0 else 1)
        expected_seconds = expected_minutes * 60.0
        time.sleep(max(1.0, expected_seconds))
        
        # Stop pump
        self.pump_stop()
        time.sleep(self.config.pump_settling_delay)
        
        return True

    def pump_run_time(self, duration_seconds: float, flow_rate_ml_min: float, direction: str = "clockwise") -> bool:
        """Enhanced time-based pump control with proper stop handling."""
        if not self._ensure_conn():
            return False
        
        self._apply_inter_device_delay("pump")
        
        # Calculate and set speed
        ml_per_rev = max(1e-6, float(self.config.ml_per_rev))
        rpm = flow_rate_ml_min / ml_per_rev
        
        if not self.pump_set_speed(rpm, direction):
            return False
        
        if not self.pump_start():
            return False
            
        # Run for specified duration
        time.sleep(max(0.0, float(duration_seconds)))
        
        # Stop pump
        self.pump_stop()
        time.sleep(self.config.pump_settling_delay)
        
        return True

    # Solenoid operations
    def solenoid_on(self) -> bool:
        self._apply_inter_device_delay("solenoid")
        return self._ok(self._send_command(f"{self.config.solenoid_relay_id}:ON"))

    def solenoid_off(self) -> bool:
        self._apply_inter_device_delay("solenoid")
        return self._ok(self._send_command(f"{self.config.solenoid_relay_id}:OFF"))

    def solenoid_drain(self, seconds: float) -> bool:
        self._apply_inter_device_delay("solenoid")
        if not self.solenoid_on():
            return False
        time.sleep(max(0.0, float(seconds)))
        # Even if off fails, report True because drain happened
        self.solenoid_off()
        return True

    # Emergency operations
    def emergency_stop(self) -> bool:
        """Emergency stop all devices."""
        ok = True
        try:
            ok &= self.pump_stop()
        finally:
            ok &= self.solenoid_off()
        return bool(ok)

    # -------------------------------
    # Compatibility methods (same interface as serial version)
    # -------------------------------
    def _apply_inter_device_delay(self, device_type: str):
        """Apply minimal delay between device operations for ethernet."""
        if self._last_device_used is not None and self._last_device_used != device_type:
            time.sleep(self.config.inter_device_delay)
        self._last_device_used = device_type

    def get_communication_stats(self) -> dict:
        """Get communication statistics for debugging."""
        return {
            "connected": self._connected,
            "last_device_used": self._last_device_used,
            "host": self.config.host,
            "port": self.config.port,
            "config": {
                "inter_device_delay": self.config.inter_device_delay,
                "command_retry_count": self.config.command_retry_count,
                "command_timeout": self.config.command_timeout,
                "connection_warmup_delay": self.config.connection_warmup_delay,
                "pump_settling_delay": self.config.pump_settling_delay,
            },
        }

    # -------------------------------
    # Helper methods
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


# Convenience factory (for backward compatibility)
def create_default_adapter(host: str = "192.168.0.100", port: int = 502) -> OptaHardwareAdapter:
    return OptaHardwareAdapter(OptaConfig(host=host, port=port))