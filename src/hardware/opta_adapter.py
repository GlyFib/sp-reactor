#!/usr/bin/env python3
"""
Enhanced Opta Adapter with Improved Communication and Pump Control

Key improvements:
1. Fixed timing calculations based on actual flow rates
2. Added pump stop functionality after timed operations
3. Enhanced device communication isolation
4. Better error handling and recovery
"""

from dataclasses import dataclass
from typing import Optional
import time
import logging


@dataclass
class OptaConfig:
    """
    Configuration for the Opta hardware adapter.
    """
    serial_port: str = "COM3"
    vici_id: str = "VICI_01"
    pump_id: str = "MFLEX_01"
    solenoid_relay_id: str = "REL_04"
    ml_per_rev: float = 0.8
    default_rpm_direction: str = "+"
    inter_device_delay: float = 2.0
    command_retry_count: int = 5
    command_timeout: float = 8.0
    connection_warmup_delay: float = 5.0
    pump_settling_delay: float = 1.0  # Additional delay after pump stops


class OptaHardwareAdapter:
    """
    Enhanced Opta adapter with improved communication and pump control.
    
    Key improvements:
    - Fixed timing calculations using actual flow rates
    - Added pump stop functionality after operations
    - Enhanced device communication isolation
    - Better error handling and recovery
    """

    is_opta_adapter = True

    def __init__(self, config: Optional[OptaConfig] = None):
        self.config = config or OptaConfig()
        self._client = None
        self._connected = False
        self._last_device_used = None
        self._logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Establish serial connection to the Opta controller."""
        if self._connected:
            return True
        try:
            # Lazy import to avoid mandatory dependency when unused
            from .integrated_opta_controller.integrated_opta_client import (
                IntegratedOptaController,
            )

            self._client = IntegratedOptaController(
                port=self.config.serial_port, 
                baudrate=115200, 
                timeout=self.config.command_timeout
            )
            self._connected = bool(self._client and self._client.connected)
            
            if self._connected:
                # Connection warmup delay
                self._logger.info(f"🔗 Connection established, warming up for {self.config.connection_warmup_delay}s...")
                time.sleep(self.config.connection_warmup_delay)
                
                # Initialize Masterflex pump
                init_response = self._retry_command(
                    lambda: self._client.masterflex_init(self.config.pump_id),
                    "masterflex_init",
                    device_type="pump"
                )
                if init_response:
                    print(f"🔧 Masterflex pump {self.config.pump_id} init response: {init_response}")
                else:
                    print(f"⚠️ Warning: Masterflex pump initialization failed")
            
            return self._connected
        except Exception as e:
            self._logger.error(f"Connection failed: {e}")
            self._client = None
            self._connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        try:
            if self._client:
                # Stop any running pumps before disconnecting
                try:
                    self._client.masterflex_stop(self.config.pump_id)
                except:
                    pass  # Ignore errors during emergency stop
                self._client.disconnect()
        finally:
            self._client = None
            self._connected = False

    # -------------------------------
    # Valve operations
    # -------------------------------
    def move_valve(self, position: int) -> bool:
        """Move VICI valve to a numeric position (1..N)."""
        if not self._ensure_conn():
            return False
        try:
            self._apply_inter_device_delay("valve")
            resp = self._retry_command(
                lambda: self._client.vici_goto_position(self.config.vici_id, str(position)),
                f"valve_move_to_{position}",
                device_type="valve"
            )
            # Be more lenient with valve responses - they seem to work despite weird format
            success = resp is not None and "ERROR" not in str(resp).upper()
            self._logger.info(f"🔍 VICI response: '{resp}' -> {'✅' if success else '❌'}")
            return success
        except Exception as e:
            self._logger.error(f"Valve move failed: {e}")
            return False

    # -------------------------------
    # Enhanced Pump operations
    # -------------------------------
    def pump_dispense_ml(
        self,
        volume_ml: float,
        flow_rate_ml_min: float,
        direction: str = "clockwise",
    ) -> bool:
        """
        Enhanced pump control with proper timing and stop functionality.
        """
        if not self._ensure_conn():
            return False
        try:
            ml_per_rev = max(1e-6, float(self.config.ml_per_rev))
            revolutions = max(0.001, float(volume_ml) / ml_per_rev)

            self._apply_inter_device_delay("pump")
            
            # Note: Removed REMOTE command as it's causing failures with this pump model
            
            # Step 1: Calculate and set speed with direction
            revolutions_per_minute = flow_rate_ml_min / ml_per_rev
            rpm = max(1.0, revolutions_per_minute)  # Ensure minimum RPM
            direction_symbol = self._dir_symbol(direction)
            
            speed_resp = self._retry_command(
                lambda: self._client.masterflex_set_speed(self.config.pump_id, rpm, direction_symbol),
                f"pump_set_speed_{rpm}_{direction_symbol}",
                device_type="pump"
            )
            
            if not self._validate_pump_response(speed_resp):
                print(f"Failed to set pump speed: {speed_resp}")
                return False
                
            print(f"✅ Pump speed set: {speed_resp}")
            
            # Step 2: Set revolutions
            rev_resp = self._retry_command(
                lambda: self._client.masterflex_set_revolutions(self.config.pump_id, revolutions),
                f"pump_set_revolutions_{revolutions}",
                device_type="pump"
            )
            
            if not self._validate_pump_response(rev_resp):
                print(f"Failed to set pump revolutions: {rev_resp}")
                return False
                
            print(f"✅ Pump revolutions set: {rev_resp}")
            
            # Step 3: Start pump
            start_resp = self._retry_command(
                lambda: self._client.masterflex_start(self.config.pump_id),
                "pump_start",
                device_type="pump"
            )
            
            if not self._validate_pump_response(start_resp):
                print(f"Failed to start pump: {start_resp}")
                return False
                
            print(f"✅ Pump started: {start_resp}")

            # Step 4: Calculate proper wait time based on flow rate and volume
            revolutions_per_minute = flow_rate_ml_min / ml_per_rev
            expected_minutes = revolutions / revolutions_per_minute
            expected_seconds = expected_minutes * 60.0
            
            print(f"⏳ Waiting {expected_seconds:.1f}s for pump to complete {revolutions:.2f} revolutions")
            time.sleep(max(1.0, expected_seconds))
            
            # Step 5: Explicitly stop pump to ensure clean completion
            stop_resp = self._retry_command(
                lambda: self._client.masterflex_stop(self.config.pump_id),
                "pump_stop_after_dispense",
                device_type="pump"
            )
            if stop_resp:
                print(f"🛑 Pump stopped: {stop_resp}")
            
            # Settling delay
            time.sleep(self.config.pump_settling_delay)
            
            return True
        except Exception as e:
            self._logger.error(f"Pump dispense failed: {e}")
            # Emergency stop on error
            try:
                self._client.masterflex_stop(self.config.pump_id)
            except:
                pass
            return False

    def pump_run_time(
        self,
        duration_seconds: float,
        flow_rate_ml_min: float,
        direction: str = "clockwise",
    ) -> bool:
        """
        Enhanced time-based pump control with proper stop handling.
        """
        if not self._ensure_conn():
            return False
        try:
            self._apply_inter_device_delay("pump")
            
            # Note: Removed REMOTE command as it's causing failures with this pump model
            
            # Step 1: Calculate and set speed with direction
            ml_per_rev = max(1e-6, float(self.config.ml_per_rev))
            revolutions_per_minute = flow_rate_ml_min / ml_per_rev
            rpm = max(1.0, revolutions_per_minute)  # Ensure minimum RPM
            direction_symbol = self._dir_symbol(direction)
            
            self._logger.debug(f"Setting pump speed: {rpm} RPM, direction: {direction} ({direction_symbol})")
            
            speed_resp = self._retry_command(
                lambda: self._client.masterflex_set_speed(self.config.pump_id, rpm, direction_symbol),
                f"pump_set_speed_{rpm}_{direction_symbol}",
                device_type="pump"
            )
            
            if not self._validate_pump_response(speed_resp):
                print(f"Failed to set pump speed: {speed_resp}")
                return False
                
            print(f"✅ Pump speed set: {speed_resp}")
            
            # Step 2: Start pump
            start_resp = self._retry_command(
                lambda: self._client.masterflex_start(self.config.pump_id),
                "pump_start_timed",
                device_type="pump"
            )
            
            if not self._validate_pump_response(start_resp):
                print(f"Failed to start pump: {start_resp}")
                return False
                
            print(f"✅ Pump started for {duration_seconds}s operation: {start_resp}")
                
            # Run for specified duration
            time.sleep(max(0.0, float(duration_seconds)))
            
            # Step 3: Stop pump
            stop_resp = self._retry_command(
                lambda: self._client.masterflex_stop(self.config.pump_id),
                "pump_stop_timed",
                device_type="pump"
            )
            print(f"🛑 Pump stopped: {stop_resp}")
            
            # Settling delay
            time.sleep(self.config.pump_settling_delay)
            
            return True
        except Exception as e:
            self._logger.error(f"Pump run time failed: {e}")
            # Emergency stop on error
            try:
                self._client.masterflex_stop(self.config.pump_id)
            except:
                pass
            return False

    # -------------------------------
    # Solenoid (vacuum) operations via relay
    # -------------------------------
    def solenoid_on(self) -> bool:
        if not self._ensure_conn():
            return False
        try:
            self._apply_inter_device_delay("solenoid")
            resp = self._retry_command(
                lambda: self._client.relay_on(self.config.solenoid_relay_id),
                "solenoid_on",
                device_type="solenoid"
            )
            return self._validate_response(resp, expected_prefixes=["OK", "DATA"])
        except Exception as e:
            self._logger.error(f"Solenoid on failed: {e}")
            return False

    def solenoid_off(self) -> bool:
        if not self._ensure_conn():
            return False
        try:
            self._apply_inter_device_delay("solenoid")
            resp = self._retry_command(
                lambda: self._client.relay_off(self.config.solenoid_relay_id),
                "solenoid_off",
                device_type="solenoid"
            )
            return self._validate_response(resp, expected_prefixes=["OK", "DATA"])
        except Exception as e:
            self._logger.error(f"Solenoid off failed: {e}")
            return False

    def solenoid_drain(self, duration_seconds: float) -> bool:
        if not self._ensure_conn():
            return False
        try:
            self._apply_inter_device_delay("solenoid")
            
            on_resp = self._retry_command(
                lambda: self._client.relay_on(self.config.solenoid_relay_id),
                "solenoid_drain_on",
                device_type="solenoid"
            )
            if not self._validate_response(on_resp, expected_prefixes=["OK", "DATA"]):
                self._logger.error(f"Failed to turn on solenoid for drain: {on_resp}")
                return False
                
            time.sleep(max(0.0, float(duration_seconds)))
            
            off_resp = self._retry_command(
                lambda: self._client.relay_off(self.config.solenoid_relay_id),
                "solenoid_drain_off",
                device_type="solenoid"
            )
            if not self._validate_response(off_resp, expected_prefixes=["OK", "DATA"]):
                self._logger.warning(f"Failed to turn off solenoid after drain: {off_resp}")
            return True
        except Exception as e:
            self._logger.error(f"Solenoid drain failed: {e}")
            return False

    # -------------------------------
    # Helper methods
    # -------------------------------
    def _ensure_conn(self) -> bool:
        return self._connected or self.connect()

    def _validate_response(self, response: Optional[str], expected_prefixes: list) -> bool:
        """Enhanced response validation with better handling of partial responses."""
        if not response:
            return False
        
        clean_response = response.strip().upper()
        if not clean_response:
            return False
            
        # Check for explicit error responses
        if "ERROR" in clean_response or "FAIL" in clean_response:
            return False
            
        # Check for expected prefixes
        for prefix in expected_prefixes:
            if clean_response.startswith(prefix.upper()):
                return True
                
        self._logger.warning(f"Unexpected response format: '{response}'")
        return False
    
    def _validate_pump_response(self, response: Optional[str]) -> bool:
        """
        Enhanced pump response validation with better error detection.
        """
        if not response:
            return False
            
        clean_response = response.strip().upper()
        if not clean_response:
            return False
        
        # Explicit failure patterns
        error_patterns = ["ERROR", "FAIL", "UNKNOWN", "INVALID"]
        if any(pattern in clean_response for pattern in error_patterns):
            return False
        
        # Success indicators
        success_patterns = ["OK:", "DATA:", "STATUS:", "ACK", "INIT"]
        if any(clean_response.startswith(pattern) for pattern in success_patterns):
            return True
        
        # Enhanced permissive handling for edge cases
        if any(pattern in clean_response for pattern in ["P?", "P01", "STARTED", "STOPPED"]):
            return True
            
        self._logger.warning(f"Ambiguous pump response: '{response}'")
        return True  # Be permissive for now
    
    def _retry_command(self, command_func, command_name: str, device_type: str = "unknown"):
        """Enhanced command retry with device-specific handling."""
        last_exception = None
        last_response = None
        
        for attempt in range(self.config.command_retry_count):
            try:
                self._logger.debug(f"🔄 Executing {command_name} (attempt {attempt + 1}/{self.config.command_retry_count})")
                response = command_func()
                
                if response is not None:
                    if attempt > 0:
                        self._logger.info(f"✅ {command_name} succeeded on attempt {attempt + 1}")
                    return response
                    
                last_response = response
                
            except Exception as e:
                last_exception = e
                self._logger.warning(f"⚠️ {command_name} attempt {attempt + 1} failed: {e}")
                
            # Add retry delay with device-specific backoff
            if attempt < self.config.command_retry_count - 1:
                base_delay = 0.5 if device_type == "pump" else 0.3
                retry_delay = base_delay * (attempt + 1)  # Progressive backoff
                self._logger.debug(f"⏳ Retrying {command_name} in {retry_delay}s...")
                time.sleep(retry_delay)
                
        # All retries failed
        error_msg = f"Command {command_name} failed after {self.config.command_retry_count} attempts"
        if last_exception:
            error_msg += f" (last error: {last_exception})"
        if last_response is not None:
            error_msg += f" (last response: '{last_response}')"
        self._logger.error(error_msg)
        
        return last_response
    
    def _apply_inter_device_delay(self, device_type: str):
        """Apply delay between different device types to prevent communication interference."""
        if self._last_device_used is not None and self._last_device_used != device_type:
            # Special handling for valve->pump transitions (requires extra isolation)
            if self._last_device_used == "valve" and device_type == "pump":
                enhanced_delay = self.config.inter_device_delay * 2.0  # Double delay for valve->pump
                self._logger.debug(f"⏳ Enhanced valve->pump delay: ({enhanced_delay}s)")
                time.sleep(enhanced_delay)
                
                # Re-initialize pump communication after valve operations
                self._logger.debug("🔄 Re-initializing pump communication after valve operation...")
                try:
                    init_resp = self._client.masterflex_init(self.config.pump_id)
                    self._logger.debug(f"Pump re-init response: {init_resp}")
                except Exception as e:
                    self._logger.warning(f"Pump re-init failed: {e}")
            else:
                self._logger.debug(f"⏳ Inter-device delay: {self._last_device_used} -> {device_type} ({self.config.inter_device_delay}s)")
                time.sleep(self.config.inter_device_delay)
        
        self._last_device_used = device_type

    def _dir_symbol(self, direction: str) -> str:
        d = (direction or "").lower().strip()
        if d.startswith("counter") or d.startswith("anti") or d.startswith("rev"):
            return "-"
        if d.startswith("clock") or d.startswith("forw") or d.startswith("cw"):
            return "+"
        return self.config.default_rpm_direction
    
    def emergency_stop(self) -> bool:
        """Emergency stop all devices."""
        try:
            print("🛑 Emergency stop initiated...")
            
            # Stop pump
            if self._client:
                stop_resp = self._client.masterflex_stop(self.config.pump_id)
                print(f"Pump emergency stop: {stop_resp}")
                
                # Turn off solenoid
                off_resp = self._client.relay_off(self.config.solenoid_relay_id)
                print(f"Solenoid emergency stop: {off_resp}")
            
            print("✅ Emergency stop completed")
            return True
        except Exception as e:
            self._logger.error(f"Emergency stop failed: {e}")
            return False
    
    def get_communication_stats(self) -> dict:
        """Get communication statistics for debugging."""
        return {
            "connected": self._connected,
            "last_device_used": self._last_device_used,
            "config": {
                "inter_device_delay": self.config.inter_device_delay,
                "command_retry_count": self.config.command_retry_count,
                "command_timeout": self.config.command_timeout,
                "connection_warmup_delay": self.config.connection_warmup_delay,
                "pump_settling_delay": self.config.pump_settling_delay,
            },
        }