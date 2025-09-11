#!/usr/bin/env python3
"""
Communication Test Script for Arduino Opta and Masterflex Pump Debugging
"""

import time
import sys
import traceback
from src.hardware.integrated_opta_controller.integrated_opta_client import IntegratedOptaController


def test_basic_communication(controller):
    """Test basic communication with the Opta controller."""
    print("\n" + "="*60)
    print("🔌 BASIC COMMUNICATION TEST")
    print("="*60)
    
    # Test STATUS command
    print("📊 Testing STATUS command...")
    status = controller.get_status()
    print(f"   Response: '{status}'")
    
    # Test HELP command
    print("🆘 Testing HELP command...")
    help_info = controller.get_help()
    print(f"   Response: '{help_info}'")
    
    return status is not None


def test_masterflex_commands_detailed(controller, pump_id="MFLEX_01"):
    """Test individual Masterflex commands with detailed logging."""
    print("\n" + "="*60)
    print("🧪 DETAILED MASTERFLEX PUMP TEST")
    print("="*60)
    
    commands_to_test = [
        ("INIT", lambda: controller.masterflex_init(pump_id)),
        ("STATUS", lambda: controller.masterflex_get_status(pump_id)),
        ("REMOTE", lambda: controller.masterflex_remote_mode(pump_id)),
        ("SPEED:10.0:+", lambda: controller.masterflex_set_speed(pump_id, 10.0, "+")),
        ("REV:1.0", lambda: controller.masterflex_set_revolutions(pump_id, 1.0)),
        ("STATUS (after setup)", lambda: controller.masterflex_get_status(pump_id)),
    ]
    
    results = {}
    
    for command_name, command_func in commands_to_test:
        print(f"\n🔧 Testing: {command_name}")
        try:
            response = command_func()
            print(f"   ✅ Response: '{response}'")
            results[command_name] = {
                "success": True,
                "response": response,
                "error": None
            }
            
            # Add delay between commands
            time.sleep(0.5)
            
        except Exception as e:
            error_msg = f"Exception: {str(e)}"
            print(f"   ❌ {error_msg}")
            results[command_name] = {
                "success": False,
                "response": None,
                "error": error_msg
            }
            traceback.print_exc()
    
    return results


def test_alternative_pump_commands(controller, pump_id="MFLEX_01"):
    """Test alternative pump command formats to debug communication."""
    print("\n" + "="*60)
    print("🔄 ALTERNATIVE COMMAND FORMAT TEST")
    print("="*60)
    
    # Try sending raw commands directly
    alternative_commands = [
        # Basic device identification
        f"{pump_id}:STATUS",
        f"{pump_id}:INIT",
        
        # Try different speed command formats
        f"{pump_id}:SPD:10",
        f"{pump_id}:SPEED:10",
        f"{pump_id}:SETSPEED:10",
        f"{pump_id}:SET_SPEED:10",
        
        # Try different revolution formats
        f"{pump_id}:REV:1",
        f"{pump_id}:REVOLUTIONS:1", 
        f"{pump_id}:SETREV:1",
        f"{pump_id}:SET_REV:1",
        
        # Control commands
        f"{pump_id}:START",
        f"{pump_id}:RUN",
        f"{pump_id}:STOP",
        f"{pump_id}:HALT",
    ]
    
    results = {}
    
    for command in alternative_commands:
        print(f"\n🧪 Testing raw command: '{command}'")
        try:
            response = controller.send_command(command)
            print(f"   Response: '{response}'")
            results[command] = response
            time.sleep(0.3)  # Short delay between commands
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            results[command] = f"EXCEPTION: {e}"
    
    return results


def test_vici_valve(controller, valve_id="VICI_01"):
    """Test VICI valve commands for comparison."""
    print("\n" + "="*60)
    print("🔄 VICI VALVE COMMUNICATION TEST")
    print("="*60)
    
    valve_commands = [
        ("STATUS", lambda: controller.vici_get_status(valve_id)),
        ("POSITION", lambda: controller.vici_get_position(valve_id)),
        ("GOTO:3", lambda: controller.vici_goto_position(valve_id, "3")),
        ("POSITION (after move)", lambda: controller.vici_get_position(valve_id)),
    ]
    
    results = {}
    
    for command_name, command_func in valve_commands:
        print(f"\n🔧 Testing VICI: {command_name}")
        try:
            response = command_func()
            print(f"   ✅ Response: '{response}'")
            results[command_name] = response
            time.sleep(1.0)  # Longer delay for valve movements
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
            results[command_name] = f"EXCEPTION: {e}"
    
    return results


def main():
    """Main test function."""
    print("🧪 Arduino Opta Communication Diagnostic Tool")
    print("=" * 80)
    
    # Get serial port from command line or use default
    serial_port = sys.argv[1] if len(sys.argv) > 1 else "COM3"
    print(f"📡 Connecting to: {serial_port}")
    
    controller = None
    try:
        # Initialize controller
        controller = IntegratedOptaController(port=serial_port, timeout=5.0)
        
        if not controller.connected:
            print("❌ Failed to connect to Arduino Opta")
            print("   - Check USB connection")
            print("   - Verify correct serial port")
            print("   - Ensure Arduino is powered and programmed")
            return
        
        print(f"✅ Connected successfully to {serial_port}")
        
        # Run all tests
        basic_ok = test_basic_communication(controller)
        
        if basic_ok:
            vici_results = test_vici_valve(controller)
            masterflex_results = test_masterflex_commands_detailed(controller)
            alternative_results = test_alternative_pump_commands(controller)
            
            # Summary
            print("\n" + "="*60)
            print("📋 TEST SUMMARY")
            print("="*60)
            
            print("\n🔄 VICI Valve Results:")
            for cmd, result in vici_results.items():
                status = "✅" if result and "ERROR" not in str(result) else "❌"
                print(f"   {status} {cmd}: {result}")
            
            print("\n🧪 Masterflex Pump Results:")
            for cmd, result in masterflex_results.items():
                if result["success"]:
                    status = "✅" if result["response"] and "ERROR" not in str(result["response"]) else "⚠️"
                    print(f"   {status} {cmd}: {result['response']}")
                else:
                    print(f"   ❌ {cmd}: {result['error']}")
            
            print("\n🔄 Alternative Commands Results:")
            working_commands = []
            for cmd, result in alternative_results.items():
                if result and "ERROR" not in str(result) and "EXCEPTION" not in str(result):
                    working_commands.append((cmd, result))
                    print(f"   ✅ {cmd}: {result}")
                else:
                    print(f"   ❌ {cmd}: {result}")
            
            print(f"\n🎯 Working Commands Found: {len(working_commands)}")
            if working_commands:
                print("   These commands might work for pump control:")
                for cmd, resp in working_commands:
                    print(f"     • {cmd} -> {resp}")
        
    except KeyboardInterrupt:
        print("\n⏹️ Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        traceback.print_exc()
    finally:
        if controller:
            controller.disconnect()
            print("🔌 Disconnected from Arduino")


if __name__ == "__main__":
    main()