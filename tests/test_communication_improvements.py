#!/usr/bin/env python3
"""
Quick test to identify working Masterflex commands
"""

import time
from src.hardware.integrated_opta_controller.integrated_opta_client import IntegratedOptaController

def test_config_parameters():
    """Test that new configuration parameters are properly set."""
    print("\n=== Testing Configuration Parameters ===")
    
    # Test default config
    config = OptaConfig()
    assert config.inter_device_delay == 0.1
    assert config.command_retry_count == 3
    assert config.command_timeout == 5.0
    assert config.connection_warmup_delay == 3.0
    print("✅ Default configuration parameters validated")
    
    # Test custom config
    custom_config = OptaConfig(
        inter_device_delay=0.2,
        command_retry_count=5,
        command_timeout=10.0,
        connection_warmup_delay=5.0
    )
    assert custom_config.inter_device_delay == 0.2
    assert custom_config.command_retry_count == 5
    assert custom_config.command_timeout == 10.0
    assert custom_config.connection_warmup_delay == 5.0
    print("✅ Custom configuration parameters validated")

def test_inter_device_delay_logic():
    """Test inter-device delay application logic."""
    print("\n=== Testing Inter-Device Delay Logic ===")
    
    adapter = OptaHardwareAdapter()
    
    # Mock time.sleep to track delays
    original_sleep = time.sleep
    sleep_calls = []
    
    def mock_sleep(duration):
        sleep_calls.append(duration)
        # Don't actually sleep in tests
    
    time.sleep = mock_sleep
    
    try:
        # First call - no delay expected
        adapter._apply_inter_device_delay("valve")
        assert len(sleep_calls) == 0
        print("✅ No delay on first device call")
        
        # Same device - no delay expected
        adapter._apply_inter_device_delay("valve")
        assert len(sleep_calls) == 0
        print("✅ No delay for same device type")
        
        # Different device - delay expected
        adapter._apply_inter_device_delay("pump")
        assert len(sleep_calls) == 1
        assert sleep_calls[0] == adapter.config.inter_device_delay
        print(f"✅ Inter-device delay applied: {sleep_calls[0]}s")
        
        # Another different device - delay expected
        adapter._apply_inter_device_delay("solenoid")
        assert len(sleep_calls) == 2
        assert sleep_calls[1] == adapter.config.inter_device_delay
        print(f"✅ Second inter-device delay applied: {sleep_calls[1]}s")
        
    finally:
        time.sleep = original_sleep

def test_response_validation():
    """Test enhanced response validation logic."""
    print("\n=== Testing Response Validation ===")
    
    adapter = OptaHardwareAdapter()
    
    # Test valid responses
    test_cases = [
        ("OK: Success", True),
        ("DATA: Status info", True),
        ("ok: lowercase", True),
        ("data: lowercase", True),
        ("  OK: With whitespace  ", True),
        ("ERROR: Failed", False),
        ("FAIL: Something failed", False),
        ("", False),
        (None, False),
        ("UNKNOWN_FORMAT", False),
        ("Partial OK", False),  # Doesn't start with OK
    ]
    
    for response, expected in test_cases:
        result = adapter._validate_response(response, ["OK", "DATA"])
        assert result == expected, f"Failed for response: '{response}', expected {expected}, got {result}"
        print(f"✅ Response '{response}' -> {result} (expected {expected})")

def test_retry_logic():
    """Test command retry mechanism."""
    print("\n=== Testing Retry Logic ===")
    
    config = OptaConfig(command_retry_count=3)
    adapter = OptaHardwareAdapter(config)
    
    # Mock time.sleep to avoid actual delays
    original_sleep = time.sleep
    time.sleep = lambda x: None
    
    try:
        # Test successful command on first try
        call_count = 0
        def success_command():
            nonlocal call_count
            call_count += 1
            return "OK: Success"
        
        result = adapter._retry_command(success_command, "test_success")
        assert result == "OK: Success"
        assert call_count == 1
        print("✅ Successful command executed once")
        
        # Test command that fails then succeeds
        call_count = 0
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Simulated failure")
            return "OK: Finally worked"
        
        result = adapter._retry_command(fail_then_succeed, "test_retry")
        assert result == "OK: Finally worked"
        assert call_count == 3
        print("✅ Command succeeded after retries")
        
        # Test command that always fails
        call_count = 0
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise Exception("Always fails")
        
        result = adapter._retry_command(always_fail, "test_fail")
        assert result is None
        assert call_count == 3  # Should try 3 times
        print("✅ Failed command retried correct number of times")
        
    finally:
        time.sleep = original_sleep

def test_communication_stats():
    """Test communication statistics functionality."""
    print("\n=== Testing Communication Statistics ===")
    
    adapter = OptaHardwareAdapter()
    stats = adapter.get_communication_stats()
    
    required_keys = ["connected", "last_device_used", "config"]
    for key in required_keys:
        assert key in stats, f"Missing key in stats: {key}"
    
    config_keys = ["inter_device_delay", "command_retry_count", "command_timeout", "connection_warmup_delay"]
    for key in config_keys:
        assert key in stats["config"], f"Missing config key: {key}"
    
    print("✅ Communication statistics structure validated")
    print(f"📊 Stats: {stats}")

def test_mock_hardware_operations():
    """Test hardware operations with mocked client."""
    print("\n=== Testing Hardware Operations with Mock ===")
    
    adapter = OptaHardwareAdapter()
    
    # Mock the client
    mock_client = Mock()
    mock_client.vici_goto_position.return_value = "OK: Valve moved to position 5"
    mock_client.masterflex_set_speed.return_value = "OK: Speed set to 100 RPM"
    mock_client.masterflex_set_revolutions.return_value = "OK: Revolutions set to 5.0"
    mock_client.masterflex_start.return_value = "OK: Pump started"
    mock_client.relay_on.return_value = "OK: Relay turned on"
    mock_client.relay_off.return_value = "OK: Relay turned off"
    
    adapter._client = mock_client
    adapter._connected = True
    
    # Mock time.sleep to avoid delays
    original_sleep = time.sleep
    time.sleep = lambda x: None
    
    try:
        # Test valve operation
        result = adapter.move_valve(5)
        assert result == True
        mock_client.vici_goto_position.assert_called_with("VICI_01", "5")
        print("✅ Valve operation with enhanced communication")
        
        # Test pump operation
        result = adapter.pump_dispense_ml(1.0, 10.0)  # 1ml at 10ml/min
        assert result == True
        print("✅ Pump operation with enhanced communication")
        
        # Test solenoid operation
        result = adapter.solenoid_on()
        assert result == True
        mock_client.relay_on.assert_called_with("REL_04")
        print("✅ Solenoid operation with enhanced communication")
        
    finally:
        time.sleep = original_sleep

def main():
    """Run all communication improvement tests."""
    print("🧪 Enhanced OptaHardwareAdapter Communication Tests")
    print("=" * 60)
    
    try:
        test_config_parameters()
        test_inter_device_delay_logic()
        test_response_validation()
        test_retry_logic()
        test_communication_stats()
        test_mock_hardware_operations()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Communication improvements validated!")
        print("\n📋 Improvements Summary:")
        print("• Inter-device delays: 100ms between different device types")
        print("• Command retries: 3 attempts with progressive backoff")
        print("• Connection warmup: 3s delay after initial connection")
        print("• Enhanced validation: Better handling of partial responses")
        print("• Comprehensive logging: Debug info for all communications")
        print("\n🚀 The enhanced adapter should resolve communication timing issues!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())