import serial
import time
from typing import Dict, Any, Optional
from .base_device import BaseDevice, DeviceStatus


class VICIValve(BaseDevice):
    """VICI selector valve with multi-port position control."""
    
    def __init__(self, device_id: str = "vici_valve", simulation_mode: bool = False):
        super().__init__(device_id, simulation_mode)
        self.serial_port = None
        self.opta_controller = None  # Arduino Opta controller
        self.current_position = 1
        self.max_positions = 12  # Default for common VICI valves
        self.position_labels = {}  # Map position numbers to reagent names
        
    def connect(self, connection_params: Dict[str, Any]) -> bool:
        """Connect to VICI valve via serial or Arduino Opta communication."""
        required_params = ['port']
        if not self.validate_connection_params(connection_params, required_params):
            return False
            
        try:
            self.set_status(DeviceStatus.CONNECTING, "Connecting to VICI valve")
            
            if self.simulation_mode:
                self.logger.info("Simulation mode: VICI valve connection simulated")
                self.set_status(DeviceStatus.CONNECTED, "Connected (simulation)")
                return True
            
            communication_method = connection_params.get('communication_method', 'direct_serial')
            
            if communication_method == 'opta':
                return self._connect_via_opta(connection_params)
            elif communication_method == 'direct_serial':
                return self._connect_direct_serial(connection_params)
            else:
                self.set_status(DeviceStatus.ERROR, f"Unsupported communication method: {communication_method}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Connection failed: {str(e)}")
            return False
    
    def _connect_via_opta(self, connection_params: Dict[str, Any]) -> bool:
        """Connect to VICI valve via Arduino Opta RS485."""
        try:
            from .opta.opta_control import OptaController
            
            self.opta_controller = OptaController(
                port=connection_params['port'],
                baudrate=connection_params.get('baudrate', 9600),
                timeout=connection_params.get('timeout', 2)
            )
            
            # Test connection with valve ID command
            if self._initialize_valve():
                self.set_status(DeviceStatus.CONNECTED, "Connected to VICI valve via Opta")
                return True
            else:
                self.opta_controller.close()
                self.opta_controller = None
                return False
                
        except ImportError:
            self.set_status(DeviceStatus.ERROR, "OptaController not available - check opta module")
            return False
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Opta connection failed: {str(e)}")
            return False
    
    def _connect_direct_serial(self, connection_params: Dict[str, Any]) -> bool:
        """Connect to VICI valve via direct serial communication."""
        try:
            self.serial_port = serial.Serial(
                port=connection_params['port'],
                baudrate=connection_params.get('baudrate', 9600),
                timeout=connection_params.get('timeout', 2),
                bytesize=connection_params.get('bytesize', serial.EIGHTBITS),
                parity=connection_params.get('parity', serial.PARITY_NONE),
                stopbits=connection_params.get('stopbits', serial.STOPBITS_ONE)
            )
            
            # Initialize valve and get current position
            time.sleep(0.5)  # Allow valve to initialize
            if self._initialize_valve():
                self.set_status(DeviceStatus.CONNECTED, "Connected to VICI valve (direct serial)")
                return True
            else:
                self.disconnect()
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Direct serial connection failed: {str(e)}")
            return False
            
    def disconnect(self) -> bool:
        """Disconnect from VICI valve."""
        try:
            # Clean up Opta controller connection
            if self.opta_controller:
                self.opta_controller.close()
                self.opta_controller = None
                
            # Clean up direct serial connection
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                
            self.serial_port = None
            self.set_status(DeviceStatus.DISCONNECTED, "Disconnected from VICI valve")
            return True
            
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Disconnect failed: {str(e)}")
            return False
            
    def is_ready(self) -> bool:
        """Check if valve is ready for operations."""
        if self.simulation_mode:
            return self.status == DeviceStatus.CONNECTED
            
        return (self.status == DeviceStatus.CONNECTED and 
                (self.opta_controller is not None or
                 (self.serial_port and self.serial_port.is_open)))
                
    def get_status(self) -> Dict[str, Any]:
        """Get current valve status and position."""
        base_status = self.get_device_info()
        base_status.update({
            'current_position': self.current_position,
            'max_positions': self.max_positions,
            'position_labels': self.position_labels,
            'reagent_at_current_position': self.position_labels.get(self.current_position, 'Unknown')
        })
        return base_status
        
    def reset(self) -> bool:
        """Reset valve to position 1."""
        return self.set_position(1)
        
    def _initialize_valve(self) -> bool:
        """Initialize valve and read current position."""
        try:
            if self.simulation_mode:
                return True
                
            # Send initialization command (valve-specific)
            self._send_command("ID")  # Request valve ID
            response = self._read_response()
            
            if response:
                # Get current position
                current_pos = self._get_current_position()
                if current_pos:
                    self.current_position = current_pos
                    return True
                    
            return False
            
        except Exception as e:
            self.logger.error(f"Valve initialization failed: {e}")
            return False
            
    def _send_command(self, command: str) -> bool:
        """Send command to valve via appropriate communication method."""
        if self.simulation_mode:
            return True
            
        try:
            if self.opta_controller is not None:
                # Send via Arduino Opta RS485
                vici_command = f"VICI_CMD:{command}"
                response = self.opta_controller.send_command(vici_command)
                return response is not None
            elif self.serial_port is not None:
                # Send via direct serial
                command_bytes = f"{command}\r".encode()
                self.serial_port.write(command_bytes)
                self.serial_port.flush()
                return True
            else:
                self.logger.error("No communication method available")
                return False
            
        except Exception as e:
            self.logger.error(f"Command send failed: {e}")
            return False
            
    def _read_response(self, timeout: float = 2.0) -> Optional[str]:
        """Read response from valve via appropriate communication method."""
        if self.simulation_mode:
            return "OK"
            
        try:
            if self.opta_controller is not None:
                # Response already received in _send_command for opta method
                # This is a simplified implementation - the opta controller
                # handles the full request/response cycle
                return "OK"  # Assume success if we got here
            elif self.serial_port is not None:
                # Read via direct serial
                start_time = time.time()
                response = ""
                
                while time.time() - start_time < timeout:
                    if self.serial_port.in_waiting > 0:
                        byte = self.serial_port.read(1)
                        if byte == b'\r':
                            break
                        response += byte.decode()
                        
                return response.strip() if response else None
            else:
                self.logger.error("No communication method available")
                return None
            
        except Exception as e:
            self.logger.error(f"Response read failed: {e}")
            return None
            
    def _get_current_position(self) -> Optional[int]:
        """Get current valve position."""
        if self.simulation_mode:
            return self.current_position
            
        try:
            self._send_command("CP")  # Current Position command
            response = self._read_response()
            
            if response and response.isdigit():
                return int(response)
                
            return None
            
        except Exception as e:
            self.logger.error(f"Get position failed: {e}")
            return None
            
    def set_position(self, position: int) -> bool:
        """Set valve to specified position."""
        if position < 1 or position > self.max_positions:
            self.set_status(DeviceStatus.ERROR, 
                          f"Invalid position {position}. Must be 1-{self.max_positions}")
            return False
            
        try:
            self.set_status(DeviceStatus.BUSY, f"Moving to position {position}")
            
            if self.simulation_mode:
                # Simulate movement time
                time.sleep(0.5)
                self.current_position = position
                reagent = self.position_labels.get(position, f"Position {position}")
                self.set_status(DeviceStatus.CONNECTED, f"At position {position}: {reagent}")
                return True
                
            # Send position command to valve
            self._send_command(f"GO{position}")
            response = self._read_response()
            
            if response == "OK":
                # Verify position change
                time.sleep(1.0)  # Wait for movement
                actual_position = self._get_current_position()
                
                if actual_position == position:
                    self.current_position = position
                    reagent = self.position_labels.get(position, f"Position {position}")
                    self.set_status(DeviceStatus.CONNECTED, f"At position {position}: {reagent}")
                    return True
                else:
                    self.set_status(DeviceStatus.ERROR, 
                                  f"Position verification failed. Requested: {position}, Actual: {actual_position}")
                    return False
            else:
                self.set_status(DeviceStatus.ERROR, f"Position command failed: {response}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Set position failed: {str(e)}")
            return False
            
    def set_position_labels(self, labels: Dict[int, str]):
        """Set labels for valve positions (e.g., {1: 'DMF', 2: 'Fmoc-Ala', ...})."""
        self.position_labels = labels.copy()
        self.logger.info(f"Position labels updated: {labels}")
        
    def get_reagent_position(self, reagent_name: str) -> Optional[int]:
        """Get position number for a specific reagent."""
        for position, label in self.position_labels.items():
            if label.lower() == reagent_name.lower():
                return position
        return None
        
    def select_reagent(self, reagent_name: str) -> bool:
        """Select valve position by reagent name."""
        position = self.get_reagent_position(reagent_name)
        if position is None:
            self.set_status(DeviceStatus.ERROR, f"Reagent '{reagent_name}' not found in position labels")
            return False
            
        return self.set_position(position)