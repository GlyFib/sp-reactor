"""
Composite functions that break down high-level operations into atomic hardware commands.
Each composite function represents a complete operation from the CSV programs.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
import re
import logging

from .hardware_commands import (
    HardwareCommand, HardwareCommandExecutor,
    MoveValveCommand, PumpCommand, SolenoidCommand, WaitCommand
)


class CompositeFunction(ABC):
    """Base class for composite functions."""
    
    def __init__(self, function_id: str):
        self.function_id = function_id
        self.logger = logging.getLogger(f"composite_function.{function_id}")
        self.last_error = None
        
    @abstractmethod
    def parse_parameters(self, **kwargs) -> bool:
        """Parse and validate parameters for this function."""
        pass
    
    @abstractmethod
    def generate_hardware_commands(self, **kwargs) -> List[HardwareCommand]:
        """Generate list of hardware commands for this composite function."""
        pass
    
    def execute(self, device_manager=None, mock_mode: bool = True, command_tracker=None, **kwargs) -> Tuple[bool, List[str]]:
        """Execute the composite function and return (success, command_results)."""
        try:
            # Parse parameters
            if not self.parse_parameters(**kwargs):
                return False, [f"Parameter validation failed: {self.last_error}"]
            
            # Generate hardware commands
            commands = self.generate_hardware_commands(**kwargs)
            
            # Execute commands with optional tracking
            if command_tracker:
                # Use tracking executor if provided
                program_step = kwargs.get('program_step', 0)
                results = command_tracker.execute_commands_with_tracking(
                    commands, program_step, self.function_id, device_manager
                )
            else:
                # Use regular executor
                executor = HardwareCommandExecutor(mock_mode=mock_mode)
                results = executor.execute_commands(commands, device_manager)
            
            self.logger.info(f"Executed {self.function_id} with {len(commands)} commands")
            return True, results
            
        except Exception as e:
            self.last_error = f"Execution failed: {str(e)}"
            self.logger.error(self.last_error)
            return False, [self.last_error]


class MeterReagentFunction(CompositeFunction):
    """
    Handles Meter_Rx_MV functions (e.g., Meter_R3_MV).
    Moves VICI valve to position x and pumps specific volume of reagent.
    """
    
    def __init__(self, function_name: str):
        # Extract valve position from function name (e.g., Meter_R3_MV -> 3)
        match = re.match(r'METER_R(\d+)_MV', function_name.upper())
        if not match:
            raise ValueError(f"Invalid meter function name: {function_name}")
        
        self.valve_position = int(match.group(1))
        super().__init__(function_name)
        
        # Reagent mapping based on CSV
        self.reagent_map = {
            1: "AA",      # Amino acid
            2: "Oxyma",   # Activator
            3: "pip",     # Piperidine (deprotection)
            4: "dmf",     # DMF solvent
            5: "rv",      # Reactor vessel
            6: "W1"       # Waste 1
        }
    
    def parse_parameters(self, **kwargs) -> bool:
        """Parse volume parameter."""
        # Volume can be specified directly or calculated from scale
        if "volume_ml" in kwargs:
            self.volume_ml = kwargs["volume_ml"]
        elif "volume_per_mmol" in kwargs and "target_scale_mmol" in kwargs:
            self.volume_ml = kwargs["volume_per_mmol"] * kwargs["target_scale_mmol"]
        else:
            self.last_error = "Missing volume_ml or volume calculation parameters"
            return False
        
        if self.volume_ml <= 0:
            self.last_error = "Volume must be positive"
            return False
        
        # Optional flow rate
        self.flow_rate = kwargs.get("flow_rate_ml_min", 10.0)  # Default 10 mL/min
        
        return True
    
    def generate_hardware_commands(self, **kwargs) -> List[HardwareCommand]:
        """Generate commands to move valve and pump reagent."""
        commands = []
        
        reagent_name = self.reagent_map.get(self.valve_position, f"R{self.valve_position}")
        
        # 1. Move valve to reagent position
        commands.append(MoveValveCommand(
            position=self.valve_position,
            reagent_name=reagent_name,
            command_id="move_valve",
            description=f"Move valve to {reagent_name} position"
        ))
        
        # 2. Pump reagent volume
        commands.append(PumpCommand(
            volume_ml=self.volume_ml,
            flow_rate_ml_min=self.flow_rate,
            direction="clockwise",  # To reactor
            command_id="pump_reagent",
            description=f"Pump {self.volume_ml} mL of {reagent_name}"
        ))
        
        return commands


class TransferFunction(CompositeFunction):
    """
    Handles Transfer_MV_RV_Time functions.
    Moves valve to RV (reactor vessel) position and pumps for specified time.
    """
    
    def __init__(self, function_name: str = "Transfer_MV_RV_Time"):
        super().__init__(function_name)
        self.rv_position = 5  # RV position from CSV mapping
    
    def parse_parameters(self, **kwargs) -> bool:
        """Parse time parameter."""
        time_param = kwargs.get("time_seconds")
        if time_param is None:
            # Try to parse from param1 or param2 (e.g., "60s")
            for param in ["param1", "param2", "time_seconds"]:
                if param in kwargs:
                    time_str = str(kwargs[param]).strip()
                    if time_str.endswith('s'):
                        try:
                            self.duration_seconds = float(time_str[:-1])
                            break
                        except ValueError:
                            continue
                    elif time_str.isdigit():
                        self.duration_seconds = float(time_str)
                        break
            else:
                self.last_error = "Missing time parameter (time_seconds or param with 'Xs' format)"
                return False
        else:
            self.duration_seconds = float(time_param)
        
        if self.duration_seconds <= 0:
            self.last_error = "Duration must be positive"
            return False
        
        # Optional flow rate
        self.flow_rate = kwargs.get("flow_rate_ml_min", 10.0)
        
        return True
    
    def generate_hardware_commands(self, **kwargs) -> List[HardwareCommand]:
        """Generate commands to move valve and pump for time."""
        commands = []
        
        # 1. Move valve to RV position
        commands.append(MoveValveCommand(
            position=self.rv_position,
            reagent_name="RV",
            command_id="move_valve",
            description="Move valve to reactor vessel position"
        ))
        
        # 2. Pump for specified time (counterclockwise - from reactor)
        commands.append(PumpCommand(
            duration_seconds=self.duration_seconds,
            flow_rate_ml_min=self.flow_rate,
            direction="counterclockwise",  # From reactor
            command_id="pump_time",
            description=f"Pump counterclockwise for {self.duration_seconds}s"
        ))
        
        return commands


class MixFunction(CompositeFunction):
    """
    Handles Mix functions.
    Currently just waits for specified time (no stirrer control yet).
    """
    
    def __init__(self, function_name: str = "Mix"):
        super().__init__(function_name)
    
    def parse_parameters(self, **kwargs) -> bool:
        """Parse mix time parameter."""
        time_param = kwargs.get("time_seconds")
        if time_param is None:
            # Try to parse from param1 or param2 (e.g., "180s")
            for param in ["param1", "param2", "time_seconds"]:
                if param in kwargs:
                    time_str = str(kwargs[param]).strip()
                    if time_str.endswith('s'):
                        try:
                            self.duration_seconds = float(time_str[:-1])
                            break
                        except ValueError:
                            continue
                    elif time_str.isdigit():
                        self.duration_seconds = float(time_str)
                        break
            else:
                self.duration_seconds = 120.0  # Default 2 minutes
        else:
            self.duration_seconds = float(time_param)
        
        if self.duration_seconds <= 0:
            self.last_error = "Duration must be positive"
            return False
        
        return True
    
    def generate_hardware_commands(self, **kwargs) -> List[HardwareCommand]:
        """Generate wait command for mixing time."""
        commands = []
        
        # Wait for mixing (no stirrer control yet)
        commands.append(WaitCommand(
            duration_seconds=self.duration_seconds,
            reason="mixing/agitation",
            command_id="wait_mix",
            description=f"Mix for {self.duration_seconds}s"
        ))
        
        return commands


class DrainFunction(CompositeFunction):
    """
    Handles Drain_RV_Time functions.
    Opens solenoid valve for drainage for specified time.
    """
    
    def __init__(self, function_name: str = "Drain_RV_Time"):
        super().__init__(function_name)
    
    def parse_parameters(self, **kwargs) -> bool:
        """Parse drain time parameter."""
        time_param = kwargs.get("time_seconds")
        if time_param is None:
            # Try to parse from param1 or param2 (e.g., "60s")
            for param in ["param1", "param2", "time_seconds"]:
                if param in kwargs:
                    time_str = str(kwargs[param]).strip()
                    if time_str.endswith('s'):
                        try:
                            self.duration_seconds = float(time_str[:-1])
                            break
                        except ValueError:
                            continue
                    elif time_str.isdigit():
                        self.duration_seconds = float(time_str)
                        break
            else:
                self.duration_seconds = 30.0  # Default 30 seconds
        else:
            self.duration_seconds = float(time_param)
        
        if self.duration_seconds <= 0:
            self.last_error = "Duration must be positive"
            return False
        
        return True
    
    def generate_hardware_commands(self, **kwargs) -> List[HardwareCommand]:
        """Generate solenoid command for draining."""
        commands = []
        
        # Open solenoid valve for drainage
        commands.append(SolenoidCommand(
            action="drain",
            duration_seconds=self.duration_seconds,
            command_id="drain_reactor",
            description=f"Drain reactor for {self.duration_seconds}s"
        ))
        
        return commands


# Composite Function Registry
class CompositeFunctionRegistry:
    """Registry for composite functions."""
    
    def __init__(self):
        self.functions = {}
        self.logger = logging.getLogger("composite_function_registry")
        self._register_default_functions()
    
    def _register_default_functions(self):
        """Register default composite functions."""
        # Register meter functions for all reagent positions
        for pos in range(1, 7):  # R1-R6
            func_name = f"Meter_R{pos}_MV"
            # Use a closure to capture the function name correctly
            def make_meter_function(fn):
                return lambda: MeterReagentFunction(fn)
            self.functions[func_name.upper()] = make_meter_function(func_name)
        
        # Register transfer, mix, and drain functions
        self.functions["TRANSFER_MV_RV_TIME"] = lambda: TransferFunction()
        self.functions["MIX"] = lambda: MixFunction()
        self.functions["DRAIN_RV_TIME"] = lambda: DrainFunction()
        
        self.logger.info(f"Registered {len(self.functions)} composite functions")
    
    def get_function(self, function_id: str) -> Optional[CompositeFunction]:
        """Get composite function by ID."""
        function_id = function_id.upper()
        if function_id in self.functions:
            return self.functions[function_id]()
        return None
    
    def list_functions(self) -> List[str]:
        """List all available function IDs."""
        return list(self.functions.keys())
    
    def register_function(self, function_id: str, function_factory):
        """Register a new composite function."""
        self.functions[function_id.upper()] = function_factory
        self.logger.info(f"Registered composite function: {function_id}")


# Global registry instance
_composite_registry = CompositeFunctionRegistry()

def get_composite_function(function_id: str) -> Optional[CompositeFunction]:
    """Get composite function by ID from global registry."""
    return _composite_registry.get_function(function_id)

def get_composite_function_registry() -> CompositeFunctionRegistry:
    """Get the global composite function registry."""
    return _composite_registry