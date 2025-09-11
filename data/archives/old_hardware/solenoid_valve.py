import time
from typing import Dict, Any
from .base_device import BaseDevice, DeviceStatus


class SolenoidValve(BaseDevice):
    """Solenoid valve for vacuum control in peptide synthesis reactor."""
    
    def __init__(self, device_id: str = "solenoid_valve", simulation_mode: bool = False):
        super().__init__(device_id, simulation_mode)
        self.is_open = False
        self.control_pin = None  # GPIO pin for control (platform-specific)
        self.valve_type = "normally_closed"  # or "normally_open"
        self.response_time = 0.1  # seconds for valve actuation
        
    def connect(self, connection_params: Dict[str, Any]) -> bool:
        """Connect to solenoid valve control system."""
        required_params = ['control_method']
        if not self.validate_connection_params(connection_params, required_params):
            return False
            
        try:
            self.set_status(DeviceStatus.CONNECTING, "Connecting to solenoid valve")
            
            control_method = connection_params['control_method']
            
            if self.simulation_mode:
                self.logger.info("Simulation mode: Solenoid valve connection simulated")
                self.is_open = False
                self.set_status(DeviceStatus.CONNECTED, "Connected (simulation)")
                return True
                
            if control_method == "gpio":
                return self._connect_gpio(connection_params)
            elif control_method == "relay_board":
                return self._connect_relay_board(connection_params)
            elif control_method == "arduino":
                return self._connect_arduino(connection_params)
            else:
                self.set_status(DeviceStatus.ERROR, f"Unsupported control method: {control_method}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Connection failed: {str(e)}")
            return False
            
    def _connect_gpio(self, connection_params: Dict[str, Any]) -> bool:
        """Connect via GPIO (Raspberry Pi, etc.)."""
        try:
            import RPi.GPIO as GPIO
            
            pin = connection_params.get('gpio_pin')
            if pin is None:
                self.set_status(DeviceStatus.ERROR, "GPIO pin not specified")
                return False
                
            self.control_pin = pin
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.control_pin, GPIO.OUT)
            
            # Initialize to closed state
            GPIO.output(self.control_pin, GPIO.LOW)
            self.is_open = False
            
            self.set_status(DeviceStatus.CONNECTED, f"Connected via GPIO pin {pin}")
            return True
            
        except ImportError:
            self.set_status(DeviceStatus.ERROR, "RPi.GPIO library not available")
            return False
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"GPIO connection failed: {str(e)}")
            return False
            
    def _connect_relay_board(self, connection_params: Dict[str, Any]) -> bool:
        """Connect via USB relay board."""
        # Placeholder for relay board implementation
        self.set_status(DeviceStatus.ERROR, "Relay board control not yet implemented")
        return False
        
    def _connect_arduino(self, connection_params: Dict[str, Any]) -> bool:
        """Connect via Arduino Opta controller."""
        try:
            from .opta.opta_control import OptaController
            
            port = connection_params.get('port')
            if not port:
                self.set_status(DeviceStatus.ERROR, "Serial port not specified for Arduino connection")
                return False
                
            self.opta_controller = OptaController(
                port=port,
                baudrate=connection_params.get('baudrate', 9600),
                timeout=connection_params.get('timeout', 2)
            )
            
            # Test connection with a status command
            response = self.opta_controller.send_command("STATUS")
            if response and "OK" in response:
                self.is_open = False  # Initialize to closed state
                self.set_status(DeviceStatus.CONNECTED, f"Connected to Arduino Opta on {port}")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, f"Arduino Opta not responding: {response}")
                return False
                
        except ImportError:
            self.set_status(DeviceStatus.ERROR, "OptaController not available - check opta module")
            return False
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Arduino connection failed: {str(e)}")
            return False
        
    def disconnect(self) -> bool:
        """Disconnect from solenoid valve."""
        try:
            # Ensure valve is closed before disconnecting
            if self.is_open:
                self.close()
                
            # Clean up Arduino Opta connection
            if hasattr(self, 'opta_controller') and self.opta_controller:
                self.opta_controller.close()
                self.opta_controller = None
                
            # Clean up GPIO connection
            if hasattr(self, 'control_pin') and self.control_pin is not None:
                try:
                    import RPi.GPIO as GPIO
                    GPIO.cleanup(self.control_pin)
                except:
                    pass  # GPIO cleanup may fail if not initialized
                    
            self.control_pin = None
            self.set_status(DeviceStatus.DISCONNECTED, "Disconnected from solenoid valve")
            return True
            
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Disconnect failed: {str(e)}")
            return False
            
    def is_ready(self) -> bool:
        """Check if valve is ready for operations."""
        if self.simulation_mode:
            return self.status == DeviceStatus.CONNECTED
            
        return (self.status == DeviceStatus.CONNECTED and 
                (self.control_pin is not None or 
                 (hasattr(self, 'opta_controller') and self.opta_controller is not None)))
                
    def get_status(self) -> Dict[str, Any]:
        """Get current valve status."""
        base_status = self.get_device_info()
        base_status.update({
            'is_open': self.is_open,
            'valve_type': self.valve_type,
            'control_pin': self.control_pin,
            'response_time': self.response_time
        })
        return base_status
        
    def reset(self) -> bool:
        """Reset valve to closed state."""
        return self.close()
        
    def open(self) -> bool:
        """Open solenoid valve (enable vacuum)."""
        if not self.is_ready():
            self.set_status(DeviceStatus.ERROR, "Valve not ready")
            return False
            
        try:
            self.set_status(DeviceStatus.BUSY, "Opening solenoid valve")
            
            if self.simulation_mode:
                time.sleep(self.response_time)
                self.is_open = True
                self.set_status(DeviceStatus.CONNECTED, "Valve opened (vacuum ON)")
                return True
                
            # Control actual hardware
            if hasattr(self, 'opta_controller') and self.opta_controller is not None:
                # Use Arduino Opta for control
                success = self.opta_controller.relay(4, 'on')
                if success:
                    time.sleep(self.response_time)
                    self.is_open = True
                    self.set_status(DeviceStatus.CONNECTED, "Valve opened (vacuum ON)")
                    return True
                else:
                    self.set_status(DeviceStatus.ERROR, "Failed to open valve via Opta")
                    return False
            elif self.control_pin is not None:
                # Use GPIO for control
                import RPi.GPIO as GPIO
                GPIO.output(self.control_pin, GPIO.HIGH)
                time.sleep(self.response_time)
                self.is_open = True
                self.set_status(DeviceStatus.CONNECTED, "Valve opened (vacuum ON)")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, "No control method configured")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Open valve failed: {str(e)}")
            return False
            
    def close(self) -> bool:
        """Close solenoid valve (disable vacuum)."""
        if not self.is_ready():
            self.set_status(DeviceStatus.ERROR, "Valve not ready")
            return False
            
        try:
            self.set_status(DeviceStatus.BUSY, "Closing solenoid valve")
            
            if self.simulation_mode:
                time.sleep(self.response_time)
                self.is_open = False
                self.set_status(DeviceStatus.CONNECTED, "Valve closed (vacuum OFF)")
                return True
                
            # Control actual hardware
            if hasattr(self, 'opta_controller') and self.opta_controller is not None:
                # Use Arduino Opta for control
                success = self.opta_controller.relay(4, 'off')
                if success:
                    time.sleep(self.response_time)
                    self.is_open = False
                    self.set_status(DeviceStatus.CONNECTED, "Valve closed (vacuum OFF)")
                    return True
                else:
                    self.set_status(DeviceStatus.ERROR, "Failed to close valve via Opta")
                    return False
            elif self.control_pin is not None:
                # Use GPIO for control
                import RPi.GPIO as GPIO
                GPIO.output(self.control_pin, GPIO.LOW)
                time.sleep(self.response_time)
                self.is_open = False
                self.set_status(DeviceStatus.CONNECTED, "Valve closed (vacuum OFF)")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, "No control method configured")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Close valve failed: {str(e)}")
            return False
            
    def pulse(self, duration_seconds: float) -> bool:
        """
        Open valve for specified duration then close.
        Useful for timed vacuum pulses.
        """
        if duration_seconds <= 0:
            self.set_status(DeviceStatus.ERROR, f"Invalid pulse duration: {duration_seconds}")
            return False
            
        try:
            self.logger.info(f"Pulsing valve for {duration_seconds} seconds")
            
            # Open valve
            if not self.open():
                return False
                
            # Wait for specified duration
            time.sleep(duration_seconds)
            
            # Close valve
            if not self.close():
                return False
                
            self.logger.info(f"Valve pulse completed ({duration_seconds}s)")
            return True
            
        except Exception as e:
            # Ensure valve is closed on error
            self.close()
            self.set_status(DeviceStatus.ERROR, f"Valve pulse failed: {str(e)}")
            return False
            
    def drain_reactor(self, drain_time_seconds: float = 10.0) -> bool:
        """
        Open valve to drain reactor contents.
        
        Args:
            drain_time_seconds: Time to keep vacuum on for draining
        """
        self.logger.info(f"Draining reactor for {drain_time_seconds} seconds")
        return self.pulse(drain_time_seconds)
        
    def quick_drain(self) -> bool:
        """Quick drain pulse for removing excess solvent."""
        return self.drain_reactor(3.0)
        
    def deep_drain(self) -> bool:
        """Extended drain for thorough liquid removal."""
        return self.drain_reactor(15.0)