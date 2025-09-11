"""
Hardware command interface for atomic hardware operations.
Supports both mock mode (human-readable sentences) and real mode (device calls).
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging


@dataclass
class HardwareCommand(ABC):
    """Base class for hardware commands."""
    command_id: str
    description: str
    
    @abstractmethod
    def to_mock_command(self) -> str:
        """Return human-readable mock command."""
        pass
    
    @abstractmethod
    def execute_real(self, device_manager) -> bool:
        """Execute real hardware command."""
        pass


@dataclass
class MoveValveCommand(HardwareCommand):
    """Command to move VICI valve to specific position."""
    position: int
    reagent_name: Optional[str] = None
    
    def __post_init__(self):
        if not hasattr(self, 'command_id'):
            self.command_id = "move_valve"
        if not hasattr(self, 'description'):
            reagent_info = f" ({self.reagent_name})" if self.reagent_name else ""
            self.description = f"Move valve to position {self.position}{reagent_info}"
    
    def to_mock_command(self) -> str:
        reagent_info = f" ({self.reagent_name})" if self.reagent_name else ""
        return f"move vici to R{self.position}{reagent_info}"
    
    def execute_real(self, device_manager) -> bool:
        try:
            # Prefer Opta adapter if provided
            if device_manager and hasattr(device_manager, "is_opta_adapter"):
                return bool(device_manager.move_valve(self.position))

            # Fallback to legacy device manager
            valve = device_manager.get_device("vici_valve")
            return valve.set_position(self.position)
        except Exception as e:
            logging.error(f"Failed to move valve: {e}")
            return False


@dataclass
class PumpCommand(HardwareCommand):
    """Command to operate masterflex pump."""
    volume_ml: Optional[float] = None
    flow_rate_ml_min: Optional[float] = None
    duration_seconds: Optional[float] = None
    direction: str = "clockwise"  # "clockwise" or "counterclockwise"
    
    def __post_init__(self):
        if not hasattr(self, 'command_id'):
            self.command_id = "pump"
        if not hasattr(self, 'description'):
            if self.volume_ml:
                self.description = f"Pump {self.volume_ml} mL"
            elif self.duration_seconds:
                self.description = f"Pump for {self.duration_seconds}s"
            else:
                self.description = "Pump operation"
    
    def to_mock_command(self) -> str:
        direction_info = f" {self.direction}" if self.direction != "clockwise" else ""
        
        if self.volume_ml:
            return f"masterflex pump{direction_info} {self.volume_ml} ml"
        elif self.duration_seconds:
            return f"masterflex pump{direction_info} {self.duration_seconds}s"
        else:
            return f"masterflex pump{direction_info}"
    
    def execute_real(self, device_manager) -> bool:
        try:
            # Prefer Opta adapter if provided
            if device_manager and hasattr(device_manager, "is_opta_adapter"):
                # Map direction to motor symbol inside adapter
                if self.volume_ml is not None and self.flow_rate_ml_min is not None:
                    return bool(
                        device_manager.pump_dispense_ml(
                            self.volume_ml, self.flow_rate_ml_min, self.direction
                        )
                    )
                elif self.duration_seconds is not None and self.flow_rate_ml_min is not None:
                    return bool(
                        device_manager.pump_run_time(
                            self.duration_seconds, self.flow_rate_ml_min, self.direction
                        )
                    )
                else:
                    logging.error("Insufficient pump parameters for Opta execution")
                    return False

            # Fallback to legacy device manager
            pump = device_manager.get_device("masterflex_pump")
            if self.volume_ml and self.flow_rate_ml_min:
                return pump.dispense_volume(self.volume_ml, self.flow_rate_ml_min)
            elif self.duration_seconds and self.flow_rate_ml_min:
                return pump.run_for_time(self.duration_seconds, self.flow_rate_ml_min)
            else:
                logging.error("Insufficient pump parameters")
                return False
        except Exception as e:
            logging.error(f"Failed to operate pump: {e}")
            return False


@dataclass 
class SolenoidCommand(HardwareCommand):
    """Command to operate solenoid valve."""
    action: str  # "on", "off", "drain"
    duration_seconds: Optional[float] = None
    
    def __post_init__(self):
        if not hasattr(self, 'command_id'):
            self.command_id = "solenoid"
        if not hasattr(self, 'description'):
            duration_info = f" for {self.duration_seconds}s" if self.duration_seconds else ""
            self.description = f"Solenoid {self.action}{duration_info}"
    
    def to_mock_command(self) -> str:
        duration_info = f" {self.duration_seconds}s" if self.duration_seconds else ""
        return f"solenoid valve {self.action}{duration_info}"
    
    def execute_real(self, device_manager) -> bool:
        try:
            # Prefer Opta adapter if provided
            if device_manager and hasattr(device_manager, "is_opta_adapter"):
                if self.action == "on":
                    return bool(device_manager.solenoid_on())
                elif self.action == "off":
                    return bool(device_manager.solenoid_off())
                elif self.action == "drain" and self.duration_seconds:
                    return bool(device_manager.solenoid_drain(self.duration_seconds))
                else:
                    logging.error(f"Invalid solenoid action: {self.action}")
                    return False

            # Fallback to legacy device manager
            solenoid = device_manager.get_device("solenoid_valve")
            if self.action == "on":
                return solenoid.open()
            elif self.action == "off":
                return solenoid.close()
            elif self.action == "drain" and self.duration_seconds:
                return solenoid.drain_reactor(self.duration_seconds)
            else:
                logging.error(f"Invalid solenoid action: {self.action}")
                return False
        except Exception as e:
            logging.error(f"Failed to operate solenoid: {e}")
            return False


@dataclass
class WaitCommand(HardwareCommand):
    """Command to wait for specified time."""
    duration_seconds: float
    reason: Optional[str] = None
    
    def __post_init__(self):
        if not hasattr(self, 'command_id'):
            self.command_id = "wait"
        if not hasattr(self, 'description'):
            reason_info = f" ({self.reason})" if self.reason else ""
            self.description = f"Wait {self.duration_seconds}s{reason_info}"
    
    def to_mock_command(self) -> str:
        reason_info = f" ({self.reason})" if self.reason else ""
        return f"wait {self.duration_seconds}s{reason_info}"
    
    def execute_real(self, device_manager) -> bool:
        try:
            import time
            time.sleep(self.duration_seconds)
            return True
        except Exception as e:
            logging.error(f"Failed to wait: {e}")
            return False


class HardwareCommandExecutor:
    """Executes lists of hardware commands in mock or real mode."""
    
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.logger = logging.getLogger("hardware_command_executor")
    
    def execute_commands(self, commands: List[HardwareCommand], 
                        device_manager=None) -> List[str]:
        """Execute a list of hardware commands."""
        results = []
        
        for command in commands:
            if self.mock_mode:
                mock_command = command.to_mock_command()
                results.append(mock_command)
                self.logger.info(f"Mock: {mock_command}")
            else:
                if device_manager is None:
                    self.logger.error("Device manager required for real mode")
                    results.append(f"ERROR: No device manager")
                    continue
                
                success = command.execute_real(device_manager)
                if success:
                    results.append(f"OK: {command.description}")
                    self.logger.info(f"Executed: {command.description}")
                else:
                    results.append(f"FAILED: {command.description}")
                    self.logger.error(f"Failed: {command.description}")
        
        return results
    
    def set_mock_mode(self, mock_mode: bool):
        """Set mock mode on/off."""
        self.mock_mode = mock_mode
        mode_str = "mock" if mock_mode else "real"
        self.logger.info(f"Hardware command executor set to {mode_str} mode")
