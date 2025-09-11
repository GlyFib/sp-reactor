#!/usr/bin/env python3
"""
Hardware Device Testing Tool for VPR Phase 2
===========================================

This tool provides comprehensive testing capabilities for Arduino Opta integrated devices:
- Relay control (REL_01 to REL_04)
- VICI valve control (VICI_01)
- Masterflex pump control (MFLEX_01)

Usage:
    python test_hardware_control.py
    
Interactive menu will guide you through testing each device type.
"""

import sys
import time
import traceback
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

try:
    from hardware.integrated_opta_controller.integrated_opta_client import IntegratedOptaController
except ImportError as e:
    print(f"Error importing IntegratedOptaController: {e}")
    print("Make sure the src/hardware directory is properly set up.")
    sys.exit(1)


class HardwareTestSuite:
    """Comprehensive test suite for hardware devices."""
    
    def __init__(self, port='COM3', baudrate=115200):
        """Initialize the test suite."""
        self.port = port
        self.baudrate = baudrate
        self.controller = None
        self.connected = False
        
    def connect(self):
        """Establish connection to Arduino Opta."""
        print(f"🔌 Connecting to Arduino Opta on {self.port}...")
        print("-" * 50)
        
        try:
            self.controller = IntegratedOptaController(port=self.port, baudrate=self.baudrate)
            self.connected = self.controller.connected
            
            if self.connected:
                print("✅ Connection successful!")
                self.controller.system_info()
            else:
                print("❌ Connection failed!")
                print("Check:")
                print("  - Arduino is connected and powered")
                print("  - Correct COM port (try COM4, COM5, etc.)")
                print("  - No other programs using the serial port")
                
        except Exception as e:
            print(f"❌ Connection error: {e}")
            self.connected = False
            
        return self.connected
    
    def disconnect(self):
        """Disconnect from Arduino Opta."""
        if self.controller:
            self.controller.disconnect()
            self.connected = False
    
    def test_relay_control(self):
        """Test relay control functionality."""
        if not self.connected:
            print("❌ Not connected to Arduino")
            return False
            
        print("\n🔌 RELAY CONTROL TEST")
        print("=" * 50)
        
        success = True
        relay_ids = ["REL_01", "REL_02", "REL_03", "REL_04"]
        
        try:
            for relay_id in relay_ids:
                print(f"\n📍 Testing {relay_id}:")
                
                # Turn ON
                print(f"  Turning {relay_id} ON...")
                response = self.controller.relay_on(relay_id)
                print(f"  Response: {response}")
                
                if not response or "ERROR" in str(response):
                    print(f"  ❌ Failed to turn {relay_id} ON")
                    success = False
                    continue
                    
                time.sleep(1)
                
                # Turn OFF
                print(f"  Turning {relay_id} OFF...")
                response = self.controller.relay_off(relay_id)
                print(f"  Response: {response}")
                
                if not response or "ERROR" in str(response):
                    print(f"  ❌ Failed to turn {relay_id} OFF")
                    success = False
                    continue
                    
                time.sleep(0.5)
                print(f"  ✅ {relay_id} test completed")
            
            # Test convenience methods
            print("\n📍 Testing convenience methods:")
            print("  Testing relay_1_on() and relay_1_off()...")
            response1 = self.controller.relay_1_on()
            print(f"  relay_1_on(): {response1}")
            time.sleep(1)
            response2 = self.controller.relay_1_off()
            print(f"  relay_1_off(): {response2}")
            
            if success:
                print("\n✅ All relay tests passed!")
            else:
                print("\n❌ Some relay tests failed!")
                
        except Exception as e:
            print(f"\n❌ Relay test error: {e}")
            traceback.print_exc()
            success = False
            
        return success
    
    def test_vici_valve_control(self):
        """Test VICI valve control functionality."""
        if not self.connected:
            print("❌ Not connected to Arduino")
            return False
            
        print("\n🚿 VICI VALVE CONTROL TEST")
        print("=" * 50)
        
        success = True
        valve_id = "VICI_01"
        
        try:
            # Get initial status
            print(f"\n📍 Testing {valve_id}:")
            print("  Getting initial status...")
            status = self.controller.vici_get_status(valve_id)
            print(f"  Status: {status}")
            
            print("  Getting initial position...")
            position = self.controller.vici_get_position(valve_id)
            print(f"  Position: {position}")
            
            # Test homing
            print("\n  Homing valve...")
            response = self.controller.vici_home(valve_id)
            print(f"  Home response: {response}")
            
            if response and "ERROR" not in str(response):
                time.sleep(3)  # Give time for homing
                position = self.controller.vici_get_position(valve_id)
                print(f"  Position after home: {position}")
            else:
                print("  ❌ Homing failed")
                success = False
            
            # Test position movements
            positions_to_test = ["2", "6"]
            
            for pos in positions_to_test:
                print(f"\n  Moving to position {pos}...")
                response = self.controller.vici_goto_position(valve_id, pos)
                print(f"  Response: {response}")
                
                if not response or "ERROR" in str(response):
                    print(f"  ❌ Failed to move to position {pos}")
                    success = False
                    continue
                    
                time.sleep(2)  # Give time for movement
                
                # Verify position
                actual_pos = self.controller.vici_get_position(valve_id)
                print(f"  Actual position: {actual_pos}")
            
            # Test convenience methods
            print("\n📍 Testing convenience methods:")
            print("  Testing vici_goto_a()...")
            response = self.controller.vici_goto_a()
            print(f"  vici_goto_a(): {response}")
            time.sleep(2)
            
            print("  Testing vici_goto_b()...")
            response = self.controller.vici_goto_b()
            print(f"  vici_goto_b(): {response}")
            time.sleep(2)
            
            # Test toggle
            print("  Testing toggle function...")
            response = self.controller.vici_toggle_primary()
            print(f"  Toggle response: {response}")
            time.sleep(2)
            position = self.controller.vici_get_position_primary()
            print(f"  Position after toggle: {position}")
            
            # Test cycle function
            print("\n📍 Running valve cycle test (3 cycles)...")
            cycle_success = self.controller.valve_cycle_test(valve_id, cycles=3, delay=1.5)
            
            if not cycle_success:
                success = False
            
            if success:
                print("\n✅ All VICI valve tests passed!")
            else:
                print("\n❌ Some VICI valve tests failed!")
                
        except Exception as e:
            print(f"\n❌ VICI valve test error: {e}")
            traceback.print_exc()
            success = False
            
        return success
    
    def test_masterflex_pump_control(self):
        """Test Masterflex pump control functionality."""
        if not self.connected:
            print("❌ Not connected to Arduino")
            return False
            
        print("\n⚙️ MASTERFLEX PUMP CONTROL TEST")
        print("=" * 50)
        
        success = True
        pump_id = "MFLEX_01"
        
        try:
            # Initialize pump
            print(f"\n📍 Testing {pump_id}:")
            print("  Initializing pump...")
            response = self.controller.masterflex_init(pump_id)
            print(f"  Init response: {response}")
            
            if not response or "ERROR" in str(response):
                print("  ❌ Pump initialization failed")
                success = False
                return success
                
            time.sleep(2)  # Give time for initialization
            
            # Get initial status
            print("  Getting pump status...")
            status = self.controller.masterflex_get_status(pump_id)
            print(f"  Status: {status}")
            
            # Set to remote mode
            print("  Setting to remote mode...")
            response = self.controller.masterflex_remote_mode(pump_id)
            print(f"  Remote mode response: {response}")
            
            if not response or "ERROR" in str(response):
                print("  ❌ Failed to set remote mode")
                success = False
                return success
            
            # Test speed setting (without running)
            speeds_to_test = [50.0, 100.0, 150.0]
            directions = ['+', '-']
            
            for speed in speeds_to_test:
                for direction in directions:
                    print(f"\n  Setting speed: {speed} RPM, direction: {direction}")
                    response = self.controller.masterflex_set_speed(pump_id, speed, direction)
                    print(f"  Response: {response}")
                    
                    if not response or "ERROR" in str(response):
                        print(f"  ❌ Failed to set speed {speed} RPM, direction {direction}")
                        success = False
                        continue
                        
                    # Get status after setting speed
                    status = self.controller.masterflex_get_status(pump_id)
                    print(f"  Status after speed set: {status}")
                    time.sleep(1)
            
            # Test revolutions setting
            print(f"\n  Setting revolutions to 10...")
            response = self.controller.masterflex_set_revolutions(pump_id, 10.0)
            print(f"  Response: {response}")
            
            if not response or "ERROR" in str(response):
                print("  ❌ Failed to set revolutions")
                success = False
            
            # Test convenience methods
            print("\n📍 Testing convenience methods:")
            print("  Testing pump_init()...")
            response = self.controller.pump_init()
            print(f"  pump_init(): {response}")
            
            print("  Testing pump_set_speed(75.0)...")
            response = self.controller.pump_set_speed(75.0)
            print(f"  pump_set_speed(): {response}")
            
            print("  Testing pump_status()...")
            response = self.controller.pump_status()
            print(f"  pump_status(): {response}")
            
            # Ask user before running pump
            print(f"\n📍 Pump sequence test:")
            print("  CAUTION: This will actually run the pump!")
            print("  Make sure tubing is properly connected and primed.")
            user_input = input("  Do you want to run pump sequence test? (y/N): ").lower()
            
            if user_input == 'y':
                print("  Running pump sequence: 50 RPM, 2 revolutions...")
                seq_success = self.controller.run_pump_sequence(pump_id, 50.0, 2.0, '+')
                
                if seq_success:
                    print("  ✅ Pump sequence started successfully")
                    print("  Monitoring pump operation...")
                    
                    # Monitor for a few seconds
                    for i in range(10):
                        status = self.controller.pump_status()
                        print(f"    Status ({i+1}/10): {status}")
                        time.sleep(1)
                    
                    # Stop pump
                    print("  Stopping pump...")
                    response = self.controller.pump_stop()
                    print(f"  Stop response: {response}")
                else:
                    print("  ❌ Pump sequence failed")
                    success = False
            else:
                print("  Skipping pump sequence test")
            
            # Return to local mode
            print("\n  Returning pump to local mode...")
            response = self.controller.masterflex_local_mode(pump_id)
            print(f"  Local mode response: {response}")
            
            if success:
                print("\n✅ All Masterflex pump tests passed!")
            else:
                print("\n❌ Some Masterflex pump tests failed!")
                
        except Exception as e:
            print(f"\n❌ Masterflex pump test error: {e}")
            traceback.print_exc()
            success = False
            
        return success
    
    def run_full_system_test(self):
        """Run comprehensive test of all systems."""
        print("\n🚀 FULL SYSTEM TEST")
        print("=" * 50)
        
        results = {
            'relay': False,
            'vici': False,
            'masterflex': False
        }
        
        # Test each subsystem
        print("Testing all hardware subsystems...")
        
        results['relay'] = self.test_relay_control()
        input("\nPress Enter to continue to VICI valve test...")
        
        results['vici'] = self.test_vici_valve_control()
        input("\nPress Enter to continue to Masterflex pump test...")
        
        results['masterflex'] = self.test_masterflex_pump_control()
        
        # Print final results
        print("\n" + "=" * 50)
        print("📊 FINAL TEST RESULTS")
        print("=" * 50)
        
        for system, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{system.upper():12}: {status}")
        
        all_passed = all(results.values())
        
        if all_passed:
            print("\n🎉 All systems operational!")
        else:
            print("\n⚠️ Some systems failed. Check connections and Arduino code.")
        
        return all_passed
    
    def emergency_stop(self):
        """Emergency stop all devices."""
        if self.controller:
            self.controller.emergency_stop()
        else:
            print("❌ No controller connection for emergency stop")


def print_menu():
    """Print the main menu."""
    print("\n" + "=" * 60)
    print("🔧 HARDWARE DEVICE TESTING TOOL")
    print("=" * 60)
    print("1. Connection Test")
    print("2. Test Relay Control")
    print("3. Test VICI Valve Control")
    print("4. Test Masterflex Pump Control")
    print("5. Run Full System Test")
    print("6. Emergency Stop All Devices")
    print("7. System Information")
    print("8. Change COM Port")
    print("0. Exit")
    print("-" * 60)


def main():
    """Main program loop."""
    print("🚀 VPR Phase 2 - Hardware Testing Tool")
    print("=" * 60)
    print("This tool helps test Arduino Opta integrated device control.")
    print("Default COM port: COM3")
    print("")
    
    # Initialize test suite
    test_suite = HardwareTestSuite()
    
    try:
        while True:
            print_menu()
            
            try:
                choice = input("Enter your choice (0-8): ").strip()
            except KeyboardInterrupt:
                print("\n\nExiting...")
                break
            
            if choice == '0':
                print("👋 Goodbye!")
                break
                
            elif choice == '1':
                test_suite.connect()
                
            elif choice == '2':
                if not test_suite.connected:
                    print("❌ Please connect first (option 1)")
                else:
                    test_suite.test_relay_control()
                    
            elif choice == '3':
                if not test_suite.connected:
                    print("❌ Please connect first (option 1)")
                else:
                    test_suite.test_vici_valve_control()
                    
            elif choice == '4':
                if not test_suite.connected:
                    print("❌ Please connect first (option 1)")
                else:
                    test_suite.test_masterflex_pump_control()
                    
            elif choice == '5':
                if not test_suite.connected:
                    print("❌ Please connect first (option 1)")
                else:
                    test_suite.run_full_system_test()
                    
            elif choice == '6':
                test_suite.emergency_stop()
                
            elif choice == '7':
                if test_suite.connected:
                    test_suite.controller.system_info()
                else:
                    print("❌ Please connect first (option 1)")
                    
            elif choice == '8':
                new_port = input("Enter new COM port (e.g., COM4): ").strip()
                if new_port:
                    test_suite.disconnect()
                    test_suite.port = new_port
                    print(f"COM port changed to {new_port}")
                    
            else:
                print("❌ Invalid choice. Please try again.")
            
            if choice != '0':
                input("\nPress Enter to continue...")
                
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user")
        
    finally:
        # Cleanup
        test_suite.disconnect()
        print("🔌 Disconnected from hardware")


if __name__ == '__main__':
    main()