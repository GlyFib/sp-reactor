from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
import logging


class DeviceStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"


class BaseDevice(ABC):
    """Abstract base class for all hardware devices in the peptide synthesizer."""
    
    def __init__(self, device_id: str, simulation_mode: bool = False):
        self.device_id = device_id
        self.simulation_mode = simulation_mode
        self.status = DeviceStatus.DISCONNECTED
        self.error_message = None
        self.logger = logging.getLogger(f"device.{device_id}")
        
    @abstractmethod
    def connect(self, connection_params: Dict[str, Any]) -> bool:
        """
        Connect to the device.
        
        Args:
            connection_params: Device-specific connection parameters
            
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Disconnect from the device.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if device is ready for operations.
        
        Returns:
            bool: True if device is ready, False otherwise
        """
        pass
    
    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Get current device status and information.
        
        Returns:
            Dict containing status information
        """
        pass
    
    @abstractmethod
    def reset(self) -> bool:
        """
        Reset device to initial state.
        
        Returns:
            bool: True if reset successful, False otherwise
        """
        pass
    
    def set_status(self, status: DeviceStatus, error_message: Optional[str] = None):
        """Update device status and optional error message."""
        self.status = status
        self.error_message = error_message
        self.logger.info(f"Status changed to {status.value}")
        if error_message:
            self.logger.error(f"Error: {error_message}")
    
    def get_device_info(self) -> Dict[str, Any]:
        """Get basic device information."""
        return {
            "device_id": self.device_id,
            "simulation_mode": self.simulation_mode,
            "status": self.status.value,
            "error_message": self.error_message
        }
    
    def validate_connection_params(self, params: Dict[str, Any], required_keys: list) -> bool:
        """Validate that required connection parameters are present."""
        missing_keys = [key for key in required_keys if key not in params]
        if missing_keys:
            self.set_status(DeviceStatus.ERROR, f"Missing connection parameters: {missing_keys}")
            return False
        return True