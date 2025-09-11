import serial
import time
from typing import Dict, Any, Optional
from .base_device import BaseDevice, DeviceStatus


class MasterflexPump(BaseDevice):
    """Masterflex pump with precision flow rate and volume dispensing control."""
    
    def __init__(self, device_id: str = "masterflex_pump", simulation_mode: bool = False):
        super().__init__(device_id, simulation_mode)
        self.serial_port = None
        self.current_flow_rate = 0.0  # mL/min
        self.max_flow_rate = 50.0  # mL/min (typical for peptide synthesis)
        self.min_flow_rate = 0.1   # mL/min
        self.is_pumping = False
        self.total_volume_dispensed = 0.0  # mL
        
    def connect(self, connection_params: Dict[str, Any]) -> bool:
        """Connect to Masterflex pump via serial communication."""
        required_params = ['port', 'baudrate']
        if not self.validate_connection_params(connection_params, required_params):
            return False
            
        try:
            self.set_status(DeviceStatus.CONNECTING, "Connecting to Masterflex pump")
            
            if self.simulation_mode:
                self.logger.info("Simulation mode: Masterflex pump connection simulated")
                self.set_status(DeviceStatus.CONNECTED, "Connected (simulation)")
                return True
                
            self.serial_port = serial.Serial(
                port=connection_params['port'],
                baudrate=connection_params.get('baudrate', 9600),
                timeout=connection_params.get('timeout', 2),
                bytesize=connection_params.get('bytesize', serial.EIGHTBITS),
                parity=connection_params.get('parity', serial.PARITY_NONE),
                stopbits=connection_params.get('stopbits', serial.STOPBITS_ONE)
            )
            
            # Initialize pump
            time.sleep(0.5)
            if self._initialize_pump():
                self.set_status(DeviceStatus.CONNECTED, "Connected to Masterflex pump")
                return True
            else:
                self.disconnect()
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Connection failed: {str(e)}")
            return False
            
    def disconnect(self) -> bool:
        """Disconnect from Masterflex pump."""
        try:
            # Stop pump before disconnecting
            if self.is_pumping:
                self.stop()
                
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                
            self.serial_port = None
            self.set_status(DeviceStatus.DISCONNECTED, "Disconnected from Masterflex pump")
            return True
            
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Disconnect failed: {str(e)}")
            return False
            
    def is_ready(self) -> bool:
        """Check if pump is ready for operations."""
        if self.simulation_mode:
            return self.status == DeviceStatus.CONNECTED
            
        return (self.status == DeviceStatus.CONNECTED and 
                self.serial_port and 
                self.serial_port.is_open)
                
    def get_status(self) -> Dict[str, Any]:
        """Get current pump status."""
        base_status = self.get_device_info()
        base_status.update({
            'current_flow_rate': self.current_flow_rate,
            'max_flow_rate': self.max_flow_rate,
            'min_flow_rate': self.min_flow_rate,
            'is_pumping': self.is_pumping,
            'total_volume_dispensed': self.total_volume_dispensed
        })
        return base_status
        
    def reset(self) -> bool:
        """Reset pump to stopped state with zero flow rate."""
        success = self.stop()
        if success:
            self.total_volume_dispensed = 0.0
            self.logger.info("Pump reset: stopped and volume counter cleared")
        return success
        
    def _initialize_pump(self) -> bool:
        """Initialize pump and verify communication."""
        try:
            if self.simulation_mode:
                return True
                
            # Send identification command
            self._send_command("ID")
            response = self._read_response()
            
            if response:
                # Stop pump and set flow rate to 0
                self._send_command("STP")
                self._send_command("FR0")
                self.current_flow_rate = 0.0
                self.is_pumping = False
                return True
                
            return False
            
        except Exception as e:
            self.logger.error(f"Pump initialization failed: {e}")
            return False
            
    def _send_command(self, command: str) -> bool:
        """Send command to pump."""
        if self.simulation_mode:
            return True
            
        try:
            command_bytes = f"{command}\r\n".encode()
            self.serial_port.write(command_bytes)
            self.serial_port.flush()
            return True
            
        except Exception as e:
            self.logger.error(f"Command send failed: {e}")
            return False
            
    def _read_response(self, timeout: float = 2.0) -> Optional[str]:
        """Read response from pump."""
        if self.simulation_mode:
            return "OK"
            
        try:
            start_time = time.time()
            response = ""
            
            while time.time() - start_time < timeout:
                if self.serial_port.in_waiting > 0:
                    byte = self.serial_port.read(1)
                    if byte in [b'\r', b'\n']:
                        if response:  # Only break if we have some response
                            break
                    else:
                        response += byte.decode()
                        
            return response.strip() if response else None
            
        except Exception as e:
            self.logger.error(f"Response read failed: {e}")
            return None
            
    def set_flow_rate(self, flow_rate: float) -> bool:
        """Set pump flow rate in mL/min."""
        if flow_rate < 0 or flow_rate > self.max_flow_rate:
            self.set_status(DeviceStatus.ERROR, 
                          f"Invalid flow rate {flow_rate}. Must be 0-{self.max_flow_rate} mL/min")
            return False
            
        try:
            if self.simulation_mode:
                self.current_flow_rate = flow_rate
                self.logger.info(f"Flow rate set to {flow_rate} mL/min (simulation)")
                return True
                
            # Send flow rate command (format depends on pump model)
            flow_rate_str = f"{flow_rate:.2f}"
            self._send_command(f"FR{flow_rate_str}")
            response = self._read_response()
            
            if response == "OK" or "FR" in str(response):
                self.current_flow_rate = flow_rate
                self.logger.info(f"Flow rate set to {flow_rate} mL/min")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, f"Set flow rate failed: {response}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Set flow rate failed: {str(e)}")
            return False
            
    def start(self) -> bool:
        """Start pumping at current flow rate."""
        if self.current_flow_rate <= 0:
            self.set_status(DeviceStatus.ERROR, "Cannot start pump: flow rate is zero")
            return False
            
        try:
            self.set_status(DeviceStatus.BUSY, f"Starting pump at {self.current_flow_rate} mL/min")
            
            if self.simulation_mode:
                self.is_pumping = True
                self.set_status(DeviceStatus.CONNECTED, f"Pumping at {self.current_flow_rate} mL/min")
                return True
                
            self._send_command("RUN")
            response = self._read_response()
            
            if response == "OK" or "RUN" in str(response):
                self.is_pumping = True
                self.set_status(DeviceStatus.CONNECTED, f"Pumping at {self.current_flow_rate} mL/min")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, f"Start pump failed: {response}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Start pump failed: {str(e)}")
            return False
            
    def stop(self) -> bool:
        """Stop pumping."""
        try:
            self.set_status(DeviceStatus.BUSY, "Stopping pump")
            
            if self.simulation_mode:
                self.is_pumping = False
                self.set_status(DeviceStatus.CONNECTED, "Pump stopped")
                return True
                
            self._send_command("STP")
            response = self._read_response()
            
            if response == "OK" or "STP" in str(response):
                self.is_pumping = False
                self.set_status(DeviceStatus.CONNECTED, "Pump stopped")
                return True
            else:
                self.set_status(DeviceStatus.ERROR, f"Stop pump failed: {response}")
                return False
                
        except Exception as e:
            self.set_status(DeviceStatus.ERROR, f"Stop pump failed: {str(e)}")
            return False
            
    def dispense_volume(self, volume_ml: float, flow_rate: float = None) -> bool:
        """
        Dispense a specific volume at given flow rate.
        
        Args:
            volume_ml: Volume to dispense in mL
            flow_rate: Flow rate in mL/min (uses current rate if None)
        """
        if volume_ml <= 0:
            self.set_status(DeviceStatus.ERROR, f"Invalid volume: {volume_ml} mL")
            return False
            
        # Set flow rate if specified
        if flow_rate is not None:
            if not self.set_flow_rate(flow_rate):
                return False
        elif self.current_flow_rate <= 0:
            self.set_status(DeviceStatus.ERROR, "No flow rate set for volume dispensing")
            return False
            
        try:
            # Calculate dispensing time
            dispense_time = (volume_ml / self.current_flow_rate) * 60  # seconds
            
            self.set_status(DeviceStatus.BUSY, 
                          f"Dispensing {volume_ml} mL at {self.current_flow_rate} mL/min")
            
            # Start pumping
            if not self.start():
                return False
                
            # Wait for dispensing to complete
            time.sleep(dispense_time)
            
            # Stop pumping
            if not self.stop():
                return False
                
            # Update total volume dispensed
            self.total_volume_dispensed += volume_ml
            
            self.set_status(DeviceStatus.CONNECTED, 
                          f"Dispensed {volume_ml} mL (total: {self.total_volume_dispensed:.2f} mL)")
            return True
            
        except Exception as e:
            self.stop()  # Ensure pump is stopped on error
            self.set_status(DeviceStatus.ERROR, f"Volume dispensing failed: {str(e)}")
            return False
            
    def prime_lines(self, prime_volume: float = 2.0, prime_flow_rate: float = 10.0) -> bool:
        """Prime pump lines with specified volume and flow rate."""
        self.logger.info(f"Priming lines with {prime_volume} mL at {prime_flow_rate} mL/min")
        return self.dispense_volume(prime_volume, prime_flow_rate)
        
    def get_volume_for_time(self, time_minutes: float) -> float:
        """Calculate volume that would be dispensed in given time at current flow rate."""
        return self.current_flow_rate * time_minutes