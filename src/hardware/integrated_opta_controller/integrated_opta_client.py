import serial
import time
import threading
from typing import Dict, List, Optional, Tuple

class IntegratedOptaController:
    """
    Unified controller for Arduino Opta integrated device system.
    
    Supports:
    - Relay control (REL_01 to REL_04)
    - VICI valve control (VICI_01, VICI_02, etc.)
    - Masterflex pump control (MFLEX_01, MFLEX_02, etc.)
    
    Command Protocol: DEVICE_ID:COMMAND[:PARAM1[:PARAM2]]
    """
    
    def __init__(self, port='COM3', baudrate=115200, timeout=2):
        """
        Initialize the integrated controller.
        
        Args:
            port (str): Serial port (e.g., 'COM3', '/dev/ttyUSB0')
            baudrate (int): Serial baud rate (default: 115200)
            timeout (float): Serial timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = None
        self.connected = False
        self._lock = threading.Lock()
        
        self.connect()
    
    def connect(self):
        """Establish serial connection to Arduino Opta."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            
            # Wait for Arduino to initialize
            time.sleep(2)
            
            # Test connection
            response = self.get_status()
            if response:
                self.connected = True
                print(f"Successfully connected to Arduino Opta on {self.port}")
                print(f"Device status: {response}")
            else:
                print("Warning: Connected but no response to status command")
                self.connected = True
                
        except serial.SerialException as e:
            print(f"Error connecting to {self.port}: {e}")
            self.connected = False
    
    def disconnect(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.connected = False
            print(f"Disconnected from {self.port}")
    
    def send_command(self, command: str) -> Optional[str]:
        """
        Send a command to the Arduino and return the response.
        
        Args:
            command (str): Command to send
            
        Returns:
            str: Response from Arduino, or None if error
        """
        if not self.connected or not self.ser:
            print("Error: Not connected to Arduino")
            return None
        
        with self._lock:
            try:
                # Clear input buffer
                self.ser.reset_input_buffer()
                
                # Send command
                full_command = command + '\n'
                self.ser.write(full_command.encode('utf-8'))
                
                # Read response
                response = self.ser.readline().decode('utf-8').strip()
                return response
                
            except serial.SerialException as e:
                print(f"Serial communication error: {e}")
                return None
    
    def get_status(self) -> Optional[str]:
        """Get status of all devices."""
        return self.send_command("STATUS")
    
    def get_help(self) -> Optional[str]:
        """Get list of available commands."""
        return self.send_command("HELP")
    
    # ======================================================================
    # RELAY CONTROL METHODS
    # ======================================================================
    
    def relay_on(self, relay_id: str) -> Optional[str]:
        """Turn on a relay."""
        return self.send_command(f"{relay_id}:ON")
    
    def relay_off(self, relay_id: str) -> Optional[str]:
        """Turn off a relay."""
        return self.send_command(f"{relay_id}:OFF")
    
    def relay_toggle(self, relay_id: str) -> Optional[str]:
        """Toggle a relay state."""
        return self.send_command(f"{relay_id}:TOGGLE")
    
    # Convenience methods for numbered relays
    def relay_1_on(self): return self.relay_on("REL_01")
    def relay_1_off(self): return self.relay_off("REL_01")
    def relay_2_on(self): return self.relay_on("REL_02")
    def relay_2_off(self): return self.relay_off("REL_02")
    def relay_3_on(self): return self.relay_on("REL_03")
    def relay_3_off(self): return self.relay_off("REL_03")
    def relay_4_on(self): return self.relay_on("REL_04")
    def relay_4_off(self): return self.relay_off("REL_04")
    
    # ======================================================================
    # VICI VALVE CONTROL METHODS
    # ======================================================================
    
    def vici_goto_position(self, valve_id: str, position: str) -> Optional[str]:
        """Move VICI valve to specified position (A, B, or number)."""
        return self.send_command(f"{valve_id}:GOTO:{position}")
    
    def vici_toggle(self, valve_id: str) -> Optional[str]:
        """Toggle VICI valve position."""
        return self.send_command(f"{valve_id}:TOGGLE")
    
    def vici_home(self, valve_id: str) -> Optional[str]:
        """Home VICI valve."""
        return self.send_command(f"{valve_id}:HOME")
    
    def vici_get_position(self, valve_id: str) -> Optional[str]:
        """Get current VICI valve position."""
        return self.send_command(f"{valve_id}:POSITION")
    
    def vici_get_status(self, valve_id: str) -> Optional[str]:
        """Get VICI valve status."""
        return self.send_command(f"{valve_id}:STATUS")
    
    def vici_cw(self, valve_id: str) -> Optional[str]:
        """Move VICI valve clockwise."""
        return self.send_command(f"{valve_id}:CW")
    
    def vici_ccw(self, valve_id: str) -> Optional[str]:
        """Move VICI valve counter-clockwise."""
        return self.send_command(f"{valve_id}:CCW")
    
    # Convenience methods for primary VICI valve
    def vici_goto_a(self): return self.vici_goto_position("VICI_01", "2")
    def vici_goto_b(self): return self.vici_goto_position("VICI_01", "3")
    def vici_toggle_primary(self): return self.vici_toggle("VICI_01")
    def vici_get_position_primary(self): return self.vici_get_position("VICI_01")
    
    # ======================================================================
    # MASTERFLEX PUMP CONTROL METHODS
    # ======================================================================
    
    def masterflex_init(self, pump_id: str) -> Optional[str]:
        """Initialize Masterflex pump communication."""
        return self.send_command(f"{pump_id}:INIT")
    
    def masterflex_set_speed(self, pump_id: str, rpm: float, direction: str = '+') -> Optional[str]:
        """Set Masterflex pump speed and direction."""
        return self.send_command(f"{pump_id}:SPEED:{rpm}:{direction}")
    
    def masterflex_start(self, pump_id: str) -> Optional[str]:
        """Start Masterflex pump."""
        return self.send_command(f"{pump_id}:START")
    
    def masterflex_stop(self, pump_id: str) -> Optional[str]:
        """Stop Masterflex pump."""
        return self.send_command(f"{pump_id}:STOP")
    
    def masterflex_set_revolutions(self, pump_id: str, revolutions: float) -> Optional[str]:
        """Set number of revolutions for Masterflex pump."""
        return self.send_command(f"{pump_id}:REV:{revolutions}")
    
    def masterflex_get_status(self, pump_id: str) -> Optional[str]:
        """Get Masterflex pump status."""
        return self.send_command(f"{pump_id}:STATUS")
    
    def masterflex_remote_mode(self, pump_id: str) -> Optional[str]:
        """Enable remote mode for Masterflex pump."""
        return self.send_command(f"{pump_id}:REMOTE")
    
    def masterflex_local_mode(self, pump_id: str) -> Optional[str]:
        """Enable local mode for Masterflex pump."""
        return self.send_command(f"{pump_id}:LOCAL")
    
    # Convenience methods for primary Masterflex pump
    def pump_init(self): return self.masterflex_init("MFLEX_01")
    def pump_set_speed(self, rpm: float, direction: str = '+'): 
        return self.masterflex_set_speed("MFLEX_01", rpm, direction)
    def pump_start(self): return self.masterflex_start("MFLEX_01")
    def pump_stop(self): return self.masterflex_stop("MFLEX_01")
    def pump_set_revolutions(self, revolutions: float): 
        return self.masterflex_set_revolutions("MFLEX_01", revolutions)
    def pump_status(self): return self.masterflex_get_status("MFLEX_01")
    
    # ======================================================================
    # HIGH-LEVEL OPERATION METHODS
    # ======================================================================
    
    def run_pump_sequence(self, pump_id: str, rpm: float, revolutions: float, direction: str = '+') -> bool:
        """
        Run a complete pump sequence: set speed, set revolutions, start, and monitor.
        
        Args:
            pump_id (str): Pump device ID
            rpm (float): Pump speed in RPM
            revolutions (float): Number of revolutions to run
            direction (str): Direction ('+' for forward, '-' for reverse)
            
        Returns:
            bool: True if sequence completed successfully
        """
        try:
            # Set speed
            response = self.masterflex_set_speed(pump_id, rpm, direction)
            if not response or not response.startswith("OK"):
                print(f"Failed to set speed: {response}")
                return False
            
            # Set revolutions
            response = self.masterflex_set_revolutions(pump_id, revolutions)
            if not response or not response.startswith("OK"):
                print(f"Failed to set revolutions: {response}")
                return False
            
            # Start pump
            response = self.masterflex_start(pump_id)
            if not response or not response.startswith("OK"):
                print(f"Failed to start pump: {response}")
                return False
            
            print(f"Pump {pump_id} sequence started: {rpm} RPM, {revolutions} rev, direction {direction}")
            return True
            
        except Exception as e:
            print(f"Error in pump sequence: {e}")
            return False
    
    def valve_cycle_test(self, valve_id: str, cycles: int = 3, delay: float = 2.0) -> bool:
        """
        Test VICI valve by cycling between A and B positions.
        
        Args:
            valve_id (str): Valve device ID
            cycles (int): Number of cycles to perform
            delay (float): Delay between moves in seconds
            
        Returns:
            bool: True if test completed successfully
        """
        try:
            print(f"Starting valve cycle test for {valve_id}: {cycles} cycles")
            
            for i in range(cycles):
                print(f"Cycle {i+1}/{cycles}")
                
                # Move to 2
                response = self.vici_goto_position(valve_id, "2")
                if not response or "ERROR" in response:
                    print(f"Failed to move to 2: {response}")
                    return False
                time.sleep(delay)
                
                # Get position
                position = self.vici_get_position(valve_id)
                print(f"Position after 2: {position}")
                
                # Move to 3
                response = self.vici_goto_position(valve_id, "3")
                if not response or "ERROR" in response:
                    print(f"Failed to move to 3: {response}")
                    return False
                time.sleep(delay)
                
                # Get position
                position = self.vici_get_position(valve_id)
                print(f"Position after 3: {position}")
            
            print("Valve cycle test completed successfully")
            return True
            
        except Exception as e:
            print(f"Error in valve cycle test: {e}")
            return False
    
    def emergency_stop(self):
        """Emergency stop - turn off all relays and stop all pumps."""
        print("EMERGENCY STOP - Shutting down all devices")
        
        # Turn off all relays
        for i in range(1, 5):
            relay_id = f"REL_{i:02d}"
            self.relay_off(relay_id)
        
        # Stop all pumps (try common pump IDs)
        for i in range(1, 9):
            pump_id = f"MFLEX_{i:02d}"
            self.masterflex_stop(pump_id)
        
        print("Emergency stop completed")
    
    def system_info(self):
        """Print system information and device status."""
        print("=== Integrated Opta Controller System Info ===")
        print(f"Port: {self.port}")
        print(f"Baudrate: {self.baudrate}")
        print(f"Connected: {self.connected}")
        
        if self.connected:
            print("\n=== Device Status ===")
            status = self.get_status()
            print(f"All devices: {status}")
            
            print("\n=== Available Commands ===")
            help_info = self.get_help()
            if help_info:
                print(help_info)
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure proper cleanup."""
        self.disconnect()


# ============================================================================
# EXAMPLE USAGE AND TEST FUNCTIONS
# ============================================================================

def main():
    """Example usage of the IntegratedOptaController."""
    
    # Replace with your actual serial port
    controller = IntegratedOptaController(port='COM3')
    
    if not controller.connected:
        print("Failed to connect to Arduino. Check port and wiring.")
        return
    
    try:
        # Show system info
        controller.system_info()
        
        print("\n=== Testing Relay Control ===")
        print("Testing Relay 1...")
        print(controller.relay_1_on())
        time.sleep(1)
        print(controller.relay_1_off())
        
        print("\n=== Testing VICI Valve ===")
        print("Getting valve position...")
        print(controller.vici_get_position_primary())
        
        print("Moving to position A...")
        print(controller.vici_goto_a())
        time.sleep(2)
        
        print("Moving to position B...")
        print(controller.vici_goto_b())
        time.sleep(2)
        
        print("\n=== Testing Masterflex Pump ===")
        print("Initializing pump...")
        print(controller.pump_init())
        
        print("Setting pump to remote mode...")
        print(controller.masterflex_remote_mode("MFLEX_01"))
        
        print("Setting pump speed to 50 RPM...")
        print(controller.pump_set_speed(50.0))
        
        print("Getting pump status...")
        print(controller.pump_status())
        
        # Uncomment to test actual pump operation
        # print("Running pump for 5 revolutions...")
        # controller.run_pump_sequence("MFLEX_01", 100.0, 5.0)
        
    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
    finally:
        controller.disconnect()


if __name__ == '__main__':
    main()