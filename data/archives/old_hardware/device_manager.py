from typing import Dict, Optional, List, Any
import logging
from .base_device import BaseDevice, DeviceStatus


class DeviceManager:
    """Manages all hardware devices for the peptide synthesizer."""
    
    def __init__(self):
        self.devices = {}
        self.device_configs = {}
        self.logger = logging.getLogger("device_manager")
        
    def register_device(self, device: BaseDevice, config: Dict[str, Any] = None):
        """Register a device with the manager."""
        self.devices[device.device_id] = device
        self.device_configs[device.device_id] = config or {}
        self.logger.info(f"Registered device: {device.device_id}")
        
    def get_device(self, device_id: str) -> Optional[BaseDevice]:
        """Get device by ID."""
        return self.devices.get(device_id)
        
    def connect_all_devices(self) -> bool:
        """Connect all registered devices."""
        self.logger.info("Connecting all devices...")
        
        success = True
        for device_id, device in self.devices.items():
            config = self.device_configs.get(device_id, {})
            
            if not device.connect(config):
                self.logger.error(f"Failed to connect {device_id}")
                success = False
            else:
                self.logger.info(f"Connected {device_id}")
                
        return success
        
    def disconnect_all_devices(self) -> bool:
        """Disconnect all devices."""
        self.logger.info("Disconnecting all devices...")
        
        success = True
        for device_id, device in self.devices.items():
            if not device.disconnect():
                self.logger.error(f"Failed to disconnect {device_id}")
                success = False
                
        return success
        
    def get_system_status(self) -> Dict[str, Any]:
        """Get status of all devices."""
        status = {
            "devices": {},
            "all_ready": True,
            "connected_count": 0,
            "total_count": len(self.devices)
        }
        
        for device_id, device in self.devices.items():
            device_status = device.get_status()
            status["devices"][device_id] = device_status
            
            if device.status == DeviceStatus.CONNECTED:
                status["connected_count"] += 1
                
            if not device.is_ready():
                status["all_ready"] = False
                
        return status
        
    def validate_required_devices(self, required_devices: List[str]) -> bool:
        """Check if all required devices are available and ready."""
        for device_id in required_devices:
            device = self.get_device(device_id)
            if not device:
                self.logger.error(f"Required device not found: {device_id}")
                return False
                
            if not device.is_ready():
                self.logger.error(f"Required device not ready: {device_id}")
                return False
                
        return True