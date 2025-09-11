"""
Universal Hardware Configuration Manager
Centralized hardware configuration for VPR system
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class OptaConfig:
    """Arduino Opta controller configuration."""
    serial_port: str = "COM3"
    baud_rate: int = 115200
    connection_timeout_seconds: int = 5
    command_timeout_seconds: int = 30


@dataclass
class DeviceConfig:
    """Individual device configuration."""
    device_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass  
class ViciValveConfig(DeviceConfig):
    """VICI valve specific configuration."""
    positions: Dict[int, str] = field(default_factory=dict)
    switching_time_seconds: float = 2.0
    
    def __post_init__(self):
        if not self.positions:
            self.positions = {
                1: "AA",
                2: "Oxyma", 
                3: "pip",
                4: "dmf",
                5: "RV",
                6: "waste"
            }


@dataclass
class MasterflexPumpConfig(DeviceConfig):
    """Masterflex pump specific configuration."""
    ml_per_revolution: float = 0.8
    max_flow_rate_ml_min: float = 50.0
    min_flow_rate_ml_min: float = 0.1
    default_flow_rate_ml_min: float = 10.0
    default_direction: str = "clockwise"
    rpm_range: tuple = field(default_factory=lambda: (1, 600))


@dataclass
class SolenoidValveConfig(DeviceConfig):
    """Solenoid valve specific configuration."""
    relay_id: str = "REL_04"
    vacuum_pressure_mbar: int = -200
    drain_time_seconds: float = 60.0
    purge_time_seconds: float = 5.0


@dataclass
class ReactorConfig:
    """Reactor vessel configuration."""
    volume_ml: float = 10.0
    dead_volume_ml: float = 0.5
    mixing_method: str = "agitation"
    temperature_celsius: float = 25.0


@dataclass
class SafetyConfig:
    """Safety limits and constraints."""
    max_pressure_bar: float = 2.0
    max_pump_volume_ml: float = 50.0
    max_operation_time_minutes: int = 480
    emergency_stop_enabled: bool = True


@dataclass
class SimulationConfig:
    """Simulation settings."""
    enabled: bool = True
    speed_multiplier: float = 1.0
    mock_hardware_delays: bool = True


@dataclass
class ExportConfig:
    """Export and output settings."""
    include_hardware_details: bool = True
    include_calibration_info: bool = True
    timestamp_format: str = "%Y%m%d_%H%M%S"


@dataclass
class HardwareConfiguration:
    """Complete hardware configuration."""
    opta: OptaConfig = field(default_factory=OptaConfig)
    vici_valve: ViciValveConfig = field(default_factory=lambda: ViciValveConfig("VICI_01"))
    masterflex_pump: MasterflexPumpConfig = field(default_factory=lambda: MasterflexPumpConfig("MFLEX_01"))
    solenoid_valve: SolenoidValveConfig = field(default_factory=lambda: SolenoidValveConfig("REL_04"))
    reactor: ReactorConfig = field(default_factory=ReactorConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    export: ExportConfig = field(default_factory=ExportConfig)


class HardwareConfigManager:
    """Manager for hardware configuration loading and access."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("data/config/hardware.yaml")
        self._config: Optional[HardwareConfiguration] = None
    
    def load_config(self) -> HardwareConfiguration:
        """Load hardware configuration from YAML file."""
        if self._config is not None:
            return self._config
            
        try:
            if not self.config_path.exists():
                logger.warning(f"Hardware config not found at {self.config_path}, using defaults")
                self._config = HardwareConfiguration()
                return self._config
                
            with open(self.config_path, 'r') as f:
                data = yaml.safe_load(f)
            
            self._config = self._parse_config(data)
            logger.info(f"Loaded hardware configuration from {self.config_path}")
            return self._config
            
        except Exception as e:
            logger.error(f"Failed to load hardware config: {e}")
            logger.info("Using default hardware configuration")
            self._config = HardwareConfiguration()
            return self._config
    
    def _parse_config(self, data: Dict[str, Any]) -> HardwareConfiguration:
        """Parse YAML data into configuration objects."""
        config = HardwareConfiguration()
        
        # Parse Opta configuration
        if 'opta' in data:
            opta_data = data['opta']
            config.opta = OptaConfig(
                serial_port=opta_data.get('serial_port', 'COM3'),
                baud_rate=opta_data.get('baud_rate', 115200),
                connection_timeout_seconds=opta_data.get('connection_timeout_seconds', 5),
                command_timeout_seconds=opta_data.get('command_timeout_seconds', 30)
            )
        
        # Parse device configurations
        if 'devices' in data:
            devices = data['devices']
            
            # VICI valve
            if 'vici_valve' in devices:
                vici_data = devices['vici_valve']
                config.vici_valve = ViciValveConfig(
                    device_id=vici_data.get('device_id', 'VICI_01'),
                    positions=vici_data.get('positions', {}),
                    switching_time_seconds=vici_data.get('switching_time_seconds', 2.0)
                )
            
            # Masterflex pump
            if 'masterflex_pump' in devices:
                pump_data = devices['masterflex_pump']
                calib = pump_data.get('calibration', {})
                defaults = pump_data.get('default_settings', {})
                
                config.masterflex_pump = MasterflexPumpConfig(
                    device_id=pump_data.get('device_id', 'MFLEX_01'),
                    ml_per_revolution=calib.get('ml_per_revolution', 0.8),
                    max_flow_rate_ml_min=calib.get('max_flow_rate_ml_min', 50.0),
                    min_flow_rate_ml_min=calib.get('min_flow_rate_ml_min', 0.1),
                    default_flow_rate_ml_min=defaults.get('flow_rate_ml_min', 10.0),
                    default_direction=defaults.get('direction', 'clockwise'),
                    rpm_range=tuple(defaults.get('rpm_range', [1, 600]))
                )
            
            # Solenoid valve
            if 'solenoid_valve' in devices:
                solenoid_data = devices['solenoid_valve']
                config.solenoid_valve = SolenoidValveConfig(
                    device_id=solenoid_data.get('relay_id', 'REL_04'),
                    relay_id=solenoid_data.get('relay_id', 'REL_04'),
                    vacuum_pressure_mbar=solenoid_data.get('vacuum_pressure_mbar', -200),
                    drain_time_seconds=solenoid_data.get('drain_time_seconds', 60.0),
                    purge_time_seconds=solenoid_data.get('purge_time_seconds', 5.0)
                )
        
        # Parse other configurations
        if 'reactor' in data:
            reactor_data = data['reactor']
            config.reactor = ReactorConfig(**reactor_data)
        
        if 'safety' in data:
            safety_data = data['safety']
            config.safety = SafetyConfig(**safety_data)
        
        if 'simulation' in data:
            sim_data = data['simulation']
            config.simulation = SimulationConfig(**sim_data)
        
        if 'export' in data:
            export_data = data['export']
            config.export = ExportConfig(**export_data)
        
        return config
    
    def get_config(self) -> HardwareConfiguration:
        """Get the current hardware configuration."""
        if self._config is None:
            return self.load_config()
        return self._config
    
    def get_device_id(self, device_type: str) -> str:
        """Get device ID for a specific device type."""
        config = self.get_config()
        
        device_map = {
            'vici_valve': config.vici_valve.device_id,
            'masterflex_pump': config.masterflex_pump.device_id,
            'solenoid_valve': config.solenoid_valve.device_id
        }
        
        return device_map.get(device_type, "")
    
    def calculate_pump_revolutions(self, volume_ml: float) -> float:
        """Calculate pump revolutions needed for a given volume."""
        config = self.get_config()
        return volume_ml / config.masterflex_pump.ml_per_revolution
    
    def calculate_pump_rpm(self, flow_rate_ml_min: float) -> float:
        """Calculate pump RPM for a given flow rate."""
        config = self.get_config()
        revolutions_per_minute = flow_rate_ml_min / config.masterflex_pump.ml_per_revolution
        return revolutions_per_minute
    
    def get_valve_position(self, reagent_name: str) -> Optional[int]:
        """Get valve position for a reagent name."""
        config = self.get_config()
        for pos, name in config.vici_valve.positions.items():
            if name.lower() == reagent_name.lower():
                return pos
        return None


# Global hardware configuration manager instance
_hardware_config_manager = None

def get_hardware_config() -> HardwareConfiguration:
    """Get the global hardware configuration."""
    global _hardware_config_manager
    if _hardware_config_manager is None:
        _hardware_config_manager = HardwareConfigManager()
    return _hardware_config_manager.get_config()

def get_hardware_manager() -> HardwareConfigManager:
    """Get the global hardware configuration manager."""
    global _hardware_config_manager
    if _hardware_config_manager is None:
        _hardware_config_manager = HardwareConfigManager()
    return _hardware_config_manager