#!/usr/bin/env python3
"""
Helper script to execute synthesis from atomic commands CSV files.
Reads atomic device commands and executes them on hardware or in simulation.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import List, Dict, Optional
import time

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.hardware.opta_adapter import OptaHardwareAdapter, OptaConfig


class AtomicCommand:
    """Represents a single atomic command from CSV."""
    
    def __init__(self, row: Dict[str, str]):
        self.sequence = row.get('Sequence', '')
        self.program_step = row.get('Program_Step', '')
        self.composite_function = row.get('Composite_Function', '')
        self.atomic_index = row.get('Atomic_Index', '')
        self.device = row.get('Device', '')
        self.device_id = row.get('Device_ID', '')
        self.command_type = row.get('Command_Type', '')
        self.parameters = row.get('Parameters', '')
        self.mock_command = row.get('Mock_Command', '')
        duration_str = row.get('Duration_Seconds', '0').strip()
        self.duration_seconds = float(duration_str) if duration_str else 0.0
        self.rpm = row.get('RPM', '')
        self.direction = row.get('Direction', '')
        self.revolutions = row.get('Revolutions', '')
        self.comments = row.get('Comments', '')
    
    def is_valid_command(self) -> bool:
        """Check if this is a valid command row (not header or comment)."""
        return (self.device and 
                self.command_type and 
                not self.sequence.startswith('#') and
                self.sequence.strip())
    
    def parse_parameters(self) -> Dict:
        """Parse the parameters string into a dictionary."""
        params = {}
        if self.parameters:
            # Parse "key=value, key2=value2" format
            param_pairs = self.parameters.split(',')
            for pair in param_pairs:
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"')
                    params[key] = value
        return params
    
    def __str__(self) -> str:
        return f"Step {self.program_step}: {self.device} {self.command_type} ({self.duration_seconds}s)"


def load_atomic_commands(csv_file: Path) -> List[AtomicCommand]:
    """Load atomic commands from CSV file."""
    commands = []
    
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            command = AtomicCommand(row)
            if command.is_valid_command():
                commands.append(command)
    
    return commands


def execute_command_simulation(command: AtomicCommand, verbose: bool = False) -> bool:
    """Execute command in simulation mode."""
    if verbose:
        print(f"  🔄 {command.mock_command}")
    
    # Simulate command execution time
    if command.duration_seconds > 0:
        time.sleep(min(command.duration_seconds / 10, 0.5))  # Speed up simulation
    
    return True


def execute_command_hardware(command: AtomicCommand, adapter: OptaHardwareAdapter, verbose: bool = False) -> bool:
    """Execute command on real hardware."""
    try:
        params = command.parse_parameters()
        
        if command.device == 'vici_valve' and command.command_type == 'move_valve':
            position = int(params.get('position', 1))
            if verbose:
                print(f"  🔄 Moving VICI valve to position {position}")
            
            success = adapter.move_valve(position)
            if not success:
                # Try to get more info by checking the raw response
                try:
                    raw_response = adapter._client.vici_goto_position(adapter.config.vici_id, str(position))
                    print(f"  🔍 VICI response: '{raw_response}'")
                except:
                    print(f"  🔍 Unable to get VICI response details")
            return success
            
        elif command.device == 'masterflex_pump' and command.command_type == 'pump_reagent':
            volume_ml = float(params.get('volume_ml', 0))
            flow_rate = float(params.get('flow_rate_ml_min', 10))
            direction = params.get('direction', 'clockwise')
            
            if verbose:
                print(f"  🔄 Pumping {volume_ml} mL at {flow_rate} mL/min ({direction})")
            
            success = adapter.pump_dispense_ml(volume_ml, flow_rate, direction)
            if not success:
                # Try to get pump status for debugging
                try:
                    status_response = adapter._client.masterflex_get_status(adapter.config.pump_id)
                    print(f"  🔍 Pump status: '{status_response}'")
                except:
                    print(f"  🔍 Unable to get pump status")
            return success
            
        elif command.device == 'masterflex_pump' and command.command_type == 'pump_time':
            duration = float(params.get('duration_seconds', 0))
            flow_rate = float(params.get('flow_rate_ml_min', 10))
            direction = params.get('direction', 'clockwise')
            
            if verbose:
                print(f"  🔄 Pumping for {duration}s at {flow_rate} mL/min ({direction})")
            
            success = adapter.pump_run_time(duration, flow_rate, direction)
            if not success:
                # Try to get pump status for debugging
                try:
                    status_response = adapter._client.masterflex_get_status(adapter.config.pump_id)
                    print(f"  🔍 Pump status: '{status_response}'")
                except:
                    print(f"  🔍 Unable to get pump status")
            return success
            
        elif command.device == 'solenoid_valve' and command.command_type == 'drain_reactor':
            duration = float(params.get('duration_seconds', 0))
            
            if verbose:
                print(f"  🔄 Draining reactor for {duration}s")
            return adapter.solenoid_drain(duration)
            
        elif command.device == 'system' and command.command_type == 'wait_mix':
            duration = float(params.get('duration_seconds', 0))
            
            if verbose:
                print(f"  ⏳ Mixing/waiting for {duration}s")
            time.sleep(duration)
            return True
            
        else:
            print(f"  ⚠️  Unknown command: {command.device} {command.command_type}")
            return False
            
    except Exception as e:
        print(f"  ❌ Command execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_atomic_commands(csv_file: Path, hardware: bool = False, verbose: bool = False,
                       host: str = '192.168.0.100', port: int = 502, ml_per_rev: float = 0.8,
                       vici_id: str = 'VICI_01', pump_id: str = 'MFLEX_01',
                       solenoid_relay_id: str = 'REL_04', serial_port: Optional[str] = None) -> bool:
    """Execute all atomic commands from CSV file."""
    print(f"📄 Loading atomic commands from: {csv_file}")
    
    # Load commands
    commands = load_atomic_commands(csv_file)
    if not commands:
        print("❌ No valid commands found in CSV file")
        return False
    
    print(f"✅ Loaded {len(commands)} commands")
    
    # Setup hardware adapter if needed
    adapter = None
    if hardware:
        print("🔌 Connecting to Arduino Opta...")
        
        # Handle backward compatibility with --serial-port (deprecated)
        if serial_port:
            print("⚠️  WARNING: --serial-port is deprecated. Use --host and --port for ethernet.")
            # If serial_port looks like an IP, use it as host
            if '.' in str(serial_port) and str(serial_port).replace('.', '').replace(':', '').isdigit():
                host_to_use = str(serial_port).split(':')[0]  # Extract host if port is included
                print(f"   Using {host_to_use} as ethernet host")
            else:
                print(f"   Using default ethernet host: {host}")
                host_to_use = host
        else:
            host_to_use = host
        
        opta_cfg = OptaConfig(
            host=host_to_use,
            port=port,
            vici_id=vici_id,
            pump_id=pump_id,
            solenoid_relay_id=solenoid_relay_id,
            ml_per_rev=ml_per_rev,
        )
        adapter = OptaHardwareAdapter(opta_cfg)
        if not adapter.connect():
            print("❌ Failed to connect to Arduino Opta")
            return False
        print("✅ Connected to hardware")
    else:
        print("🔄 Running in simulation mode")
    
    # Execute commands
    print("🚀 Starting execution...")
    start_time = time.time()
    failed_commands = 0
    
    try:
        for i, command in enumerate(commands, 1):
            print(f"[{i:3}/{len(commands)}] {command}")
            
            if hardware:
                success = execute_command_hardware(command, adapter, verbose)
            else:
                success = execute_command_simulation(command, verbose)
            
            if not success:
                failed_commands += 1
                print(f"  ❌ Command failed")
                if not hardware:  # In hardware mode, continue despite failures
                    break
    
    except KeyboardInterrupt:
        print("\n🛑 Execution interrupted by user")
        return False
    
    finally:
        if adapter:
            print("🔌 Disconnecting from hardware...")
            adapter.disconnect()
    
    # Summary
    elapsed_time = time.time() - start_time
    print("\n" + "="*50)
    print(f"✅ Execution completed in {elapsed_time:.1f} seconds")
    print(f"📊 Commands executed: {len(commands) - failed_commands}/{len(commands)}")
    
    if failed_commands > 0:
        print(f"⚠️  Failed commands: {failed_commands}")
        return False
    
    return True


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Execute synthesis from atomic commands CSV file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s atomic_commands.csv                    # Simulate execution
  %(prog)s atomic_commands.csv --hardware         # Execute on hardware (ethernet)
  %(prog)s atomic_commands.csv --hardware --host 192.168.1.100 --port 502  # Custom ethernet
        """
    )
    
    parser.add_argument(
        'csv_file',
        type=Path,
        help='Atomic commands CSV file to execute'
    )
    
    parser.add_argument(
        '--hardware', '-H',
        action='store_true',
        help='Execute on real hardware via Arduino Opta'
    )
    
    parser.add_argument(
        '--host',
        default='192.168.0.100',
        help='Ethernet host for Arduino Opta (default: 192.168.0.100)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=502,
        help='Ethernet port for Arduino Opta (default: 502)'
    )
    
    parser.add_argument(
        '--serial-port',
        help='[DEPRECATED] Use --host and --port for ethernet communication'
    )
    
    parser.add_argument(
        '--ml-per-rev',
        type=float,
        default=0.8,
        help='Pump calibration: mL per revolution (default: 0.8)'
    )
    
    parser.add_argument(
        '--vici-id',
        default='VICI_01',
        help='VICI valve device ID on Opta (default: VICI_01)'
    )
    
    parser.add_argument(
        '--pump-id',
        default='MFLEX_01',
        help='Masterflex pump device ID on Opta (default: MFLEX_01)'
    )
    
    parser.add_argument(
        '--solenoid-relay-id',
        default='REL_04',
        help='Solenoid/vacuum relay ID on Opta (default: REL_04)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output showing individual commands'
    )
    
    return parser


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Check if CSV file exists
    if not args.csv_file.exists():
        print(f"❌ CSV file not found: {args.csv_file}")
        return 1
    
    print("🧪 Atomic Commands Executor")
    print("=" * 40)
    
    try:
        success = run_atomic_commands(
            csv_file=args.csv_file,
            hardware=args.hardware,
            verbose=args.verbose,
            host=args.host,
            port=args.port,
            serial_port=args.serial_port,
            ml_per_rev=args.ml_per_rev,
            vici_id=args.vici_id,
            pump_id=args.pump_id,
            solenoid_relay_id=args.solenoid_relay_id
        )
        
        return 0 if success else 1
        
    except Exception as e:
        print(f"❌ Execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())