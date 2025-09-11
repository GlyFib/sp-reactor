from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List, Optional
import logging
from dataclasses import dataclass


class ProgramStatus(Enum):
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    PAUSED = "paused"
    ERROR = "error"
    ABORTED = "aborted"


@dataclass
class ProgramParameter:
    """Definition of a program parameter with validation rules."""
    name: str
    param_type: type
    required: bool = True
    default: Any = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    description: str = ""


class ProgramBase(ABC):
    """Abstract base class for all synthesis programs."""
    
    def __init__(self, program_id: str):
        self.program_id = program_id
        self.status = ProgramStatus.READY
        self.parameters = {}
        self.required_devices = []
        self.execution_time_estimate = 0.0
        self.current_step = 0
        self.total_steps = 0
        self.error_message = None
        self.logger = logging.getLogger(f"program.{program_id}")
        
    @abstractmethod
    def get_parameter_definitions(self) -> List[ProgramParameter]:
        """
        Get list of parameters this program accepts.
        
        Returns:
            List of ProgramParameter objects defining program parameters
        """
        pass
    
    @abstractmethod
    def get_required_devices(self) -> List[str]:
        """
        Get list of device IDs required for this program.
        
        Returns:
            List of device IDs that must be available
        """
        pass
    
    @abstractmethod
    def validate_parameters(self, parameters: Dict[str, Any]) -> bool:
        """
        Validate program parameters.
        
        Args:
            parameters: Dictionary of parameter values
            
        Returns:
            bool: True if parameters are valid, False otherwise
        """
        pass
    
    @abstractmethod
    def estimate_execution_time(self, parameters: Dict[str, Any]) -> float:
        """
        Estimate program execution time in minutes.
        
        Args:
            parameters: Dictionary of parameter values
            
        Returns:
            float: Estimated execution time in minutes
        """
        pass
    
    @abstractmethod
    def execute(self, parameters: Dict[str, Any], device_manager) -> bool:
        """
        Execute the program with given parameters.
        
        Args:
            parameters: Dictionary of parameter values
            device_manager: DeviceManager instance for hardware control
            
        Returns:
            bool: True if execution successful, False otherwise
        """
        pass
    
    @abstractmethod
    def pause(self) -> bool:
        """
        Pause program execution.
        
        Returns:
            bool: True if pause successful, False otherwise
        """
        pass
    
    @abstractmethod
    def resume(self) -> bool:
        """
        Resume paused program execution.
        
        Returns:
            bool: True if resume successful, False otherwise
        """
        pass
    
    @abstractmethod
    def abort(self) -> bool:
        """
        Abort program execution.
        
        Returns:
            bool: True if abort successful, False otherwise
        """
        pass
    
    def set_status(self, status: ProgramStatus, error_message: Optional[str] = None):
        """Update program status and optional error message."""
        self.status = status
        self.error_message = error_message
        self.logger.info(f"Status changed to {status.value}")
        if error_message:
            self.logger.error(f"Error: {error_message}")
    
    def update_progress(self, current_step: int, total_steps: int):
        """Update program execution progress."""
        self.current_step = current_step
        self.total_steps = total_steps
        progress_percent = (current_step / total_steps * 100) if total_steps > 0 else 0
        self.logger.info(f"Progress: {current_step}/{total_steps} ({progress_percent:.1f}%)")
    
    def validate_parameter_value(self, param_def: ProgramParameter, value: Any) -> bool:
        """Validate a single parameter value against its definition."""
        if not isinstance(value, param_def.param_type):
            self.set_status(ProgramStatus.ERROR, 
                          f"Parameter {param_def.name} must be of type {param_def.param_type.__name__}")
            return False
            
        if param_def.min_value is not None and value < param_def.min_value:
            self.set_status(ProgramStatus.ERROR, 
                          f"Parameter {param_def.name} must be >= {param_def.min_value}")
            return False
            
        if param_def.max_value is not None and value > param_def.max_value:
            self.set_status(ProgramStatus.ERROR, 
                          f"Parameter {param_def.name} must be <= {param_def.max_value}")
            return False
            
        if param_def.allowed_values is not None and value not in param_def.allowed_values:
            self.set_status(ProgramStatus.ERROR, 
                          f"Parameter {param_def.name} must be one of {param_def.allowed_values}")
            return False
            
        return True
    
    def get_program_info(self) -> Dict[str, Any]:
        """Get program information and current status."""
        return {
            "program_id": self.program_id,
            "status": self.status.value,
            "parameters": self.parameters,
            "required_devices": self.required_devices,
            "execution_time_estimate": self.execution_time_estimate,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "error_message": self.error_message,
            "progress_percent": (self.current_step / self.total_steps * 100) if self.total_steps > 0 else 0
        }