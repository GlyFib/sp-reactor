from typing import Dict, Type, Any, Optional, List
import logging
from .base_device import BaseDevice
from .solenoid_valve import SolenoidValve
from .vici_valve import VICIValve
from .masterflex_pump import MasterflexPump


class DeviceRegistry:
    """Registry for device types and their configurations."""
    
    def __init__(self):
        self._device_types: Dict[str, Type[BaseDevice]] = {}
        self._default_configs: Dict[str, Dict[str, Any]] = {}
        self.logger = logging.getLogger("device_registry")
        
        # Register built-in device types
        self._register_builtin_devices()
    
    def _register_builtin_devices(self):
        """Register the built-in device types."""
        self.register_device_type("solenoid_valve", SolenoidValve, {
            'control_method': 'arduino',
            'port': 'COM3',
            'baudrate': 9600
        })
        
        self.register_device_type("vici_valve", VICIValve, {
            'communication_method': 'opta',
            'port': 'COM3',
            'baudrate': 9600
        })
        
        self.register_device_type("masterflex_pump", MasterflexPump, {
            'port': 'COM4',
            'baudrate': 9600
        })
        
        # Convenience aliases
        self.register_device_type("solenoid", SolenoidValve, {
            'control_method': 'arduino',
            'port': 'COM3'
        })
        
        self.register_device_type("vici", VICIValve, {
            'communication_method': 'opta',
            'port': 'COM3'
        })
        
        self.register_device_type("pump", MasterflexPump, {
            'port': 'COM4'
        })
        
        # Future devices (placeholders)
        # self.register_device_type("ika_stirrer", IKAStirrer, {...})
        # self.register_device_type("mettler_scale", MettlerScale, {...})
        # self.register_device_type("huber_chiller", HuberChiller, {...})
    
    def register_device_type(self, device_type: str, device_class: Type[BaseDevice], 
                           default_config: Dict[str, Any] = None):
        """
        Register a new device type.
        
        Args:
            device_type: String identifier for the device type
            device_class: Class that implements BaseDevice
            default_config: Default connection parameters
        """
        if not issubclass(device_class, BaseDevice):
            raise ValueError(f"Device class {device_class} must inherit from BaseDevice")
        
        self._device_types[device_type] = device_class
        self._default_configs[device_type] = default_config or {}
        self.logger.info(f"Registered device type: {device_type} -> {device_class.__name__}")
    
    def get_device_types(self) -> List[str]:
        """Get list of all registered device types."""
        return list(self._device_types.keys())
    
    def get_device_class(self, device_type: str) -> Optional[Type[BaseDevice]]:
        """Get device class for a given type."""
        return self._device_types.get(device_type)
    
    def get_default_config(self, device_type: str) -> Dict[str, Any]:
        """Get default configuration for a device type."""
        return self._default_configs.get(device_type, {}).copy()


# Global device registry instance
device_registry = DeviceRegistry()


class DeviceFactory:
    """Factory for creating hardware devices with standardized configurations."""
    
    def __init__(self, registry: DeviceRegistry = None):
        self.registry = registry or device_registry
        self.logger = logging.getLogger("device_factory")
    
    def create_device(self, device_type: str, device_id: str = None, 
                     simulation_mode: bool = False, **kwargs) -> BaseDevice:
        """
        Create a device instance.
        
        Args:
            device_type: Type of device to create (from registry)
            device_id: Unique identifier for the device instance
            simulation_mode: Whether to create in simulation mode
            **kwargs: Additional parameters for device creation
            
        Returns:
            BaseDevice instance
            
        Raises:
            ValueError: If device_type is not registered
        """
        device_class = self.registry.get_device_class(device_type)
        if not device_class:
            available_types = ", ".join(self.registry.get_device_types())
            raise ValueError(f"Unknown device type '{device_type}'. Available: {available_types}")
        
        # Generate device ID if not provided
        if device_id is None:
            device_id = f"{device_type}_auto"
        
        # Create device instance
        device = device_class(device_id=device_id, simulation_mode=simulation_mode, **kwargs)
        self.logger.info(f"Created {device_type} device: {device_id} (simulation: {simulation_mode})")
        
        return device
    
    def create_and_connect(self, device_type: str, device_id: str = None,
                          simulation_mode: bool = False, connection_params: Dict[str, Any] = None,
                          **kwargs) -> BaseDevice:
        """
        Create a device and connect it using default or provided parameters.
        
        Args:
            device_type: Type of device to create
            device_id: Unique identifier for the device instance
            simulation_mode: Whether to create in simulation mode
            connection_params: Connection parameters (uses defaults if None)
            **kwargs: Additional parameters for device creation
            
        Returns:
            Connected BaseDevice instance
            
        Raises:
            RuntimeError: If connection fails
        """
        device = self.create_device(device_type, device_id, simulation_mode, **kwargs)
        
        # Use provided connection params or defaults from registry
        if connection_params is None:
            connection_params = self.registry.get_default_config(device_type)
        
        # Connect device
        if not device.connect(connection_params):
            error_msg = f"Failed to connect {device_type} device: {device_id}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        self.logger.info(f"Successfully connected {device_type} device: {device_id}")
        return device
    
    def create_standard_setup(self, simulation_mode: bool = True, 
                            port_base: str = "COM") -> Dict[str, BaseDevice]:
        """
        Create a standard peptide synthesizer device setup.
        
        Args:
            simulation_mode: Whether to create devices in simulation mode
            port_base: Base for serial port names (COM for Windows, /dev/ttyUSB for Linux)
            
        Returns:
            Dictionary of device_id -> device_instance
        """
        devices = {}
        
        # Standard device configuration
        standard_devices = [
            ("solenoid_valve", "vacuum_solenoid", f"{port_base}3"),
            ("vici_valve", "reagent_selector", f"{port_base}3"), 
            ("masterflex_pump", "main_pump", f"{port_base}4")
        ]
        
        for device_type, device_id, port in standard_devices:
            try:
                connection_params = self.registry.get_default_config(device_type)
                connection_params['port'] = port
                
                device = self.create_and_connect(
                    device_type=device_type,
                    device_id=device_id,
                    simulation_mode=simulation_mode,
                    connection_params=connection_params
                )
                devices[device_id] = device
                
            except Exception as e:
                self.logger.error(f"Failed to create {device_id}: {e}")
                if not simulation_mode:
                    # In real hardware mode, continue with other devices
                    continue
                else:
                    raise
        
        self.logger.info(f"Created standard setup with {len(devices)} devices")
        return devices
    
    def create_opta_setup(self, opta_port: str = "COM3", 
                         simulation_mode: bool = False) -> Dict[str, BaseDevice]:
        """
        Create a setup using Arduino Opta for both solenoid and VICI valve control.
        
        Args:
            opta_port: Serial port for Arduino Opta
            simulation_mode: Whether to create in simulation mode
            
        Returns:
            Dictionary of device_id -> device_instance
        """
        devices = {}
        
        # Both solenoid and VICI use the same Opta controller
        opta_devices = [
            ("solenoid_valve", "opta_solenoid", {
                'control_method': 'arduino', 
                'port': opta_port
            }),
            ("vici_valve", "opta_vici", {
                'communication_method': 'opta',
                'port': opta_port
            })
        ]
        
        for device_type, device_id, params in opta_devices:
            try:
                device = self.create_and_connect(
                    device_type=device_type,
                    device_id=device_id,
                    simulation_mode=simulation_mode,
                    connection_params=params
                )
                devices[device_id] = device
                
            except Exception as e:
                self.logger.error(f"Failed to create {device_id}: {e}")
                if not simulation_mode:
                    continue
                else:
                    raise
        
        self.logger.info(f"Created Opta setup with {len(devices)} devices on {opta_port}")
        return devices


# Global factory instance for convenience
device_factory = DeviceFactory()


def register_device_type(device_type: str, device_class: Type[BaseDevice], 
                        default_config: Dict[str, Any] = None):
    """
    Convenience function to register a new device type globally.
    
    Args:
        device_type: String identifier for the device type
        device_class: Class that implements BaseDevice
        default_config: Default connection parameters
    """
    device_registry.register_device_type(device_type, device_class, default_config)


def create_device(device_type: str, device_id: str = None, 
                 simulation_mode: bool = False, **kwargs) -> BaseDevice:
    """
    Convenience function to create a device using the global factory.
    
    Args:
        device_type: Type of device to create
        device_id: Unique identifier for the device instance
        simulation_mode: Whether to create in simulation mode
        **kwargs: Additional parameters for device creation
        
    Returns:
        BaseDevice instance
    """
    return device_factory.create_device(device_type, device_id, simulation_mode, **kwargs)


def create_and_connect(device_type: str, device_id: str = None,
                      simulation_mode: bool = False, connection_params: Dict[str, Any] = None,
                      **kwargs) -> BaseDevice:
    """
    Convenience function to create and connect a device using the global factory.
    
    Args:
        device_type: Type of device to create
        device_id: Unique identifier for the device instance
        simulation_mode: Whether to create in simulation mode
        connection_params: Connection parameters (uses defaults if None)
        **kwargs: Additional parameters for device creation
        
    Returns:
        Connected BaseDevice instance
    """
    return device_factory.create_and_connect(device_type, device_id, simulation_mode, 
                                           connection_params, **kwargs)


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print("Available device types:", device_registry.get_device_types())
    
    # Create individual devices
    solenoid = create_device("solenoid", "test_solenoid", simulation_mode=True)
    vici = create_device("vici", "test_vici", simulation_mode=True)
    
    print(f"Created: {solenoid.device_id} ({type(solenoid).__name__})")
    print(f"Created: {vici.device_id} ({type(vici).__name__})")
    
    # Create standard setup
    devices = device_factory.create_standard_setup(simulation_mode=True)
    print(f"Standard setup: {list(devices.keys())}")
    
    # Create Opta setup
    opta_devices = device_factory.create_opta_setup(simulation_mode=True)
    print(f"Opta setup: {list(opta_devices.keys())}")