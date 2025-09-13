#!/usr/bin/env python3
"""
Main entry point for the Virtual Peptide Reactor.
Command-line interface with multiple operation modes.
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.display.cli import SynthesisCLI, run_interactive_mode, run_file_mode
from src.synthesis.coordinator import SynthesisCoordinator, SynthesisParameters
from src.synthesis.stoichiometry_deprecated import StoichiometryCalculator
from src.vpr_io.config import ConfigManager, create_default_config_file
from src.vpr_io.logger import SynthesisLogger


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('vpr.log'),
            logging.StreamHandler()
        ]
    )


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Virtual Peptide Reactor - Automated Peptide Synthesis System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Interactive mode
  %(prog)s --sequence sequences/fmrf.txt      # Hardware execution with sequence file
  %(prog)s --simulated --sequence sequences/fmrf.txt  # Simulated execution
  %(prog)s --recipe-only --sequence sequences/fmrf.txt  # Generate recipe only
  %(prog)s --config config/standard.yaml      # Use custom config
  %(prog)s --create-config config/my.yaml     # Create default config file
        """
    )
    
    # Operation modes
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--simulated', '-S',
        action='store_true',
        help='Run in simulation mode (default is hardware execution)'
    )
    mode_group.add_argument(
        '--recipe-only', '-r',
        action='store_true',
        help='Generate recipe file only, no execution'
    )
    mode_group.add_argument(
        '--create-config',
        metavar='FILE',
        help='Create default configuration file and exit'
    )
    
    # Input files
    parser.add_argument(
        '--sequence', '-s',
        type=Path,
        metavar='FILE',
        help='Peptide sequence file (.txt or .csv)'
    )
    parser.add_argument(
        '--config', '-c',
        type=Path,
        metavar='FILE',
        help='Configuration file (.yaml)'
    )
    
    # Synthesis parameters
    parser.add_argument(
        '--scale', '-m',
        type=float,
        default=None,
        metavar='MMOL',
        help='Synthesis scale in mmol (default: from config or 0.1)'
    )
    parser.add_argument(
        '--resin-mass', '-R',
        type=float,
        metavar='GRAMS',
        help='Resin mass in grams (calculated if not provided)'
    )
    parser.add_argument(
        '--program', '-p',
        default='aa_oxyma_dic_v1',
        metavar='NAME',
        help='Default AA program name (default: aa_oxyma_dic_v1)'
    )
    
    # Output control
    parser.add_argument(
        '--output-dir', '-o',
        type=Path,
        default=Path('output'),
        metavar='DIR',
        help='Output directory (default: output)'
    )
    parser.add_argument(
        '--output-format', '-f',
        choices=['csv', 'json', 'yaml'],
        default='csv',
        help='Output format for recipes (default: csv)'
    )
    
    # Execution control
    parser.add_argument(
        '--fast',
        action='store_true',
        help='Fast simulation mode (10x speed)'
    )
    parser.add_argument(
        '--speed',
        type=float,
        default=1.0,
        metavar='MULTIPLIER',
        help='Speed multiplier for simulation (0.1-10.0, default: 1.0)'
    )
    parser.add_argument(
        '--no-interactive-controls',
        action='store_true',
        help='Disable interactive controls during synthesis'
    )
    
    # System options
    parser.add_argument(
        '--programs-dir',
        type=Path,
        default=Path('src/programs'),
        metavar='DIR',
        help='Programs directory (default: src/programs)'
    )
    parser.add_argument(
        '--stoichiometry-file',
        type=Path,
        metavar='FILE',
        help='Stoichiometry configuration file'
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
        help='Pump calibration: mL per revolution (default: 0.8 for Masterflex 16)'
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
        help='Verbose output'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet mode (minimal output)'
    )
    
    return parser


def generate_atomic_commands_csv(params: SynthesisParameters, args, schedule=None) -> Optional[Path]:
    """Generate atomic device commands CSV for the complete synthesis."""
    try:
        from src.functions.command_exporter import CommandTrackingExecutor
        from datetime import datetime
        
        # Create timestamp for filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Extract sequence identifier from peptide sequence (first 4 characters)
        seq_id = params.peptide_sequence[:4].upper() if len(params.peptide_sequence) >= 4 else params.peptide_sequence.upper()
        
        # Create output filename
        scale_str = f"{params.target_scale_mmol:.1f}mmol".replace('.', 'p')
        filename = f"atomic_commands_{seq_id}_{scale_str}_{timestamp}.csv"
        
        # Create output directory
        output_dir = args.output_dir / "atomic_commands"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        
        # Create synthesis coordinator
        from src.synthesis.coordinator import SynthesisCoordinator
        
        coordinator = SynthesisCoordinator(args.programs_dir)
        
        # Create synthesis schedule if not provided
        if schedule is None:
            schedule = coordinator.create_synthesis_schedule(params)
        
        # Create tracking executor
        executor = CommandTrackingExecutor(mock_mode=True)
        
        print(f"🔧 Generating atomic commands for complete {params.peptide_sequence} synthesis...")
        print(f"   Schedule has {len(schedule.steps)} steps")
        
        # Execute all steps in the schedule with tracking
        for step in schedule.steps:
            print(f"   Processing step {step.step_number}: {step.amino_acid or 'Program'} ({step.program_name})")
            success = _execute_schedule_step_with_tracking(step, coordinator, executor, args.verbose)
            if not success:
                print(f"   ⚠️  Step {step.step_number} failed during export")
        
        # Export to CSV
        synthesis_info = {
            "program_id": f"{params.peptide_sequence}_synthesis",
            "scale_mmol": params.target_scale_mmol,
            "step_count": len(schedule.steps),
            "estimated_duration_minutes": schedule.total_estimated_time_minutes
        }
        
        csv_path = executor.export_to_csv(output_path, synthesis_info)
        
        # Print summary
        stats = executor.get_summary_statistics()
        if stats:
            print(f"   ✅ Export complete: {stats['total_commands']} commands, "
                  f"{stats['total_duration_minutes']:.1f} minutes total")
        else:
            print(f"   ✅ Export complete: 0 commands exported")
        
        return csv_path
        
    except Exception as e:
        print(f"Error generating atomic commands CSV: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return None


def _execute_schedule_step_with_tracking(step, coordinator, executor, verbose=False, device_manager=None):
    """Execute a synthesis schedule step with command tracking."""
    try:
        from src.functions.composite_functions import get_composite_function
        
        # Generate executable program for this step
        executable_program = coordinator.generate_executable_program(step)
        
        # Execute each program step with tracking
        for program_step in executable_program.get('steps', []):
            function_id = program_step['function_id']
            params = program_step['params']
            
            # Get composite function
            composite_function = get_composite_function(function_id)
            if not composite_function:
                if verbose:
                    print(f"      Composite function not found: {function_id}")
                return False
            
            # Parse parameters and generate commands
            if not composite_function.parse_parameters(**params):
                if verbose:
                    print(f"      Parameter parsing failed: {composite_function.last_error}")
                return False
            
            commands = composite_function.generate_hardware_commands(**params)
            
            # Execute with tracking
            results = executor.execute_commands_with_tracking(
                commands,
                program_step['seq'],
                function_id,
                device_manager
            )
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"      Step execution failed during export: {e}")
            import traceback
            traceback.print_exc()
        return False


def run_recipe_only_mode(sequence_file: Path, args) -> int:
    """Generate recipe file without running synthesis."""
    print("📝 Recipe Generation Mode")
    print("=" * 40)
    
    try:
        # Check if input file is a synthesis config (YAML) or sequence (TXT)
        if sequence_file.suffix.lower() == '.yaml':
            # Load synthesis configuration
            from src.synthesis.synthesis_config import load_synthesis_config
            config = load_synthesis_config(sequence_file)
            
            sequence = config.sequence
            scale = config.scale.target_mmol if args.scale is None else args.scale  # CLI arg overrides
            aa_program = config.default_aa_program
            
            print(f"📋 Sequence: {sequence}")
            print(f"📏 Scale: {scale} mmol")
            print(f"🧪 Program: {aa_program}")
            print(f"🔄 Double coupling: {config.double_couple_difficult}")
            
            # Initialize synthesis system
            coordinator = SynthesisCoordinator(args.programs_dir)
            
            # Create parameters from config
            params = SynthesisParameters(
                peptide_sequence=sequence,
                target_scale_mmol=scale,
                resin_mass_g=args.resin_mass,
                aa_program=aa_program,
                double_couple_difficult=config.double_couple_difficult,
                perform_capping=config.perform_capping,
                monitor_coupling=config.monitor_coupling
            )
            
        elif sequence_file.suffix.lower() == '.txt':
            # Load sequence from text file
            with open(sequence_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        sequence = line
                        break
                else:
                    print("❌ No valid sequence found in file")
                    return 1
            
            # Check if config file is provided via -c flag
            if args.config:
                from src.synthesis.synthesis_config import load_synthesis_config
                config = load_synthesis_config(args.config)
                
                scale = config.scale.target_mmol if args.scale is None else args.scale  # CLI arg overrides
                aa_program = config.default_aa_program
                
                print(f"📋 Sequence: {sequence}")
                print(f"📏 Scale: {scale} mmol")
                print(f"🧪 Program: {aa_program}")
                print(f"🔄 Double coupling: {config.double_couple_difficult}")
                
                # Initialize synthesis system
                coordinator = SynthesisCoordinator(args.programs_dir)
                
                # Create parameters from config
                params = SynthesisParameters(
                    peptide_sequence=sequence,
                    target_scale_mmol=scale,
                    resin_mass_g=args.resin_mass,
                    aa_program=aa_program,
                    double_couple_difficult=config.double_couple_difficult,
                    perform_capping=config.perform_capping,
                    monitor_coupling=config.monitor_coupling
                )
            else:
                # No config file, use defaults
                print(f"📋 Sequence: {sequence}")
                print(f"📏 Scale: {args.scale or 0.1} mmol")
                
                # Initialize synthesis system
                coordinator = SynthesisCoordinator(args.programs_dir)
                
                # Create parameters with defaults
                params = SynthesisParameters(
                    peptide_sequence=sequence,
                    target_scale_mmol=args.scale or 0.1,
                    resin_mass_g=args.resin_mass,
                    aa_program=args.program
                )
        else:
            print("❌ Unsupported sequence file format. Use .yaml for synthesis config or .txt for sequence")
            return 1
        
        # Generate schedule
        print("🔨 Generating synthesis schedule...")
        schedule = coordinator.create_synthesis_schedule(params)
        
        print(f"✅ Schedule created: {len(schedule.steps)} steps")
        print(f"   Estimated time: {schedule.total_estimated_time_minutes:.1f} minutes")
        print(f"   Resin mass: {schedule.resin_mass_g:.2f} g")
        
        # Generate recipe file
        from src.vpr_io.config import OutputManager
        output_manager = OutputManager(args.output_dir)
        recipe_path = output_manager.generate_recipe_file(schedule, args.output_format)
        
        print(f"📄 Recipe saved: {recipe_path}")
        
        # Generate atomic command CSV table
        print("🔧 Generating atomic device command table...")
        atomic_commands_path = generate_atomic_commands_csv(params, args, schedule)
        if atomic_commands_path:
            print(f"📊 Atomic commands CSV: {atomic_commands_path}")
        else:
            print("⚠️  Failed to generate atomic commands CSV")
        
        print("✅ Recipe generation completed!")
        
        return 0
        
    except Exception as e:
        print(f"❌ Recipe generation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def run_simulation_mode(sequence_file: Path, args) -> int:
    """Run synthesis simulation with timing and interactive controls."""
    print("🎮 Simulation Mode")
    print("=" * 40)
    
    try:
        # Parse sequence/config
        if sequence_file.suffix.lower() == '.yaml':
            from src.synthesis.synthesis_config import load_synthesis_config
            config = load_synthesis_config(sequence_file)
            sequence = config.sequence
            scale = config.scale.target_mmol if args.scale is None else args.scale
            aa_program = config.default_aa_program
        elif sequence_file.suffix.lower() == '.txt':
            with open(sequence_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        sequence = line
                        break
                else:
                    print("❌ No valid sequence found in file")
                    return 1
            
            if args.config:
                from src.synthesis.synthesis_config import load_synthesis_config
                cfg = load_synthesis_config(args.config)
                scale = cfg.scale.target_mmol if args.scale is None else args.scale
                aa_program = cfg.default_aa_program
            else:
                scale = args.scale or 0.1
                aa_program = args.program
        else:
            print("❌ Unsupported sequence file format. Use .yaml or .txt")
            return 1
        
        # Initialize synthesis system
        coordinator = SynthesisCoordinator(args.programs_dir)
        
        # Create parameters
        params = SynthesisParameters(
            peptide_sequence=sequence,
            target_scale_mmol=scale,
            resin_mass_g=args.resin_mass,
            aa_program=aa_program
        )
        
        # Generate schedule
        print(f"🧪 Simulating synthesis of {sequence} at {scale} mmol scale")
        schedule = coordinator.create_synthesis_schedule(params)
        print(f"✅ Schedule created: {len(schedule.steps)} steps")
        
        # Setup speed multiplier
        speed = 10.0 if args.fast else args.speed
        
        # Run simulation execution
        from src.execution.simulation_executor import SynthesisSimulationExecutor
        sim_executor = SynthesisSimulationExecutor(coordinator, speed)
        
        print(f"▶️  Starting simulation (speed: {speed}x)")
        
        for step in schedule.steps:
            print(f"   Step {step.step_number}: {step.amino_acid or 'Program'} ({step.program_name})")
            results = sim_executor.execute_synthesis_step_simulation(step)
            if not results:
                print(f"   ❌ Step {step.step_number} simulation failed")
                return 1
            print(f"   ✅ Step {step.step_number} completed ({len(results)} commands)")
        
        print(f"🎉 Simulation completed successfully!")
        return 0
        
    except Exception as e:
        print(f"❌ Simulation failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def run_hardware_mode(sequence_file: Path, args) -> int:
    """Run synthesis on real hardware using Arduino Opta."""
    print("🔌 Hardware Execution Mode (Arduino Opta)")
    print("=" * 40)
    
    try:
        # Parse sequence/config similar to recipe-only mode
        if sequence_file.suffix.lower() == '.yaml':
            from src.synthesis.synthesis_config import load_synthesis_config
            config = load_synthesis_config(sequence_file)
            sequence = config.sequence
            scale = config.scale.target_mmol if args.scale is None else args.scale
            aa_program = config.default_aa_program
        elif sequence_file.suffix.lower() == '.txt':
            with open(sequence_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        sequence = line
                        break
                else:
                    print("❌ No valid sequence found in file")
                    return 1
            # Optional external config
            if args.config:
                from src.synthesis.synthesis_config import load_synthesis_config
                cfg = load_synthesis_config(args.config)
                scale = cfg.scale.target_mmol if args.scale is None else args.scale
                aa_program = cfg.default_aa_program
            else:
                scale = args.scale or 0.1
                aa_program = args.program
        else:
            print("❌ Unsupported sequence file format. Use .yaml or .txt")
            return 1

        # Initialize synthesis system
        coordinator = SynthesisCoordinator(args.programs_dir)

        # Create parameters
        params = SynthesisParameters(
            peptide_sequence=sequence,
            target_scale_mmol=scale,
            resin_mass_g=args.resin_mass,
            aa_program=aa_program
        )

        # Generate schedule
        print("🔨 Generating synthesis schedule...")
        schedule = coordinator.create_synthesis_schedule(params)
        print(f"✅ Schedule created: {len(schedule.steps)} steps")
        print(f"   Estimated time: {schedule.total_estimated_time_minutes:.1f} minutes")
        print(f"   Resin mass: {schedule.resin_mass_g:.2f} g")

        # Set up Opta adapter
        from src.hardware.opta_adapter import OptaHardwareAdapter, OptaConfig
        
        # Handle backward compatibility with --serial-port (deprecated)
        if args.serial_port:
            print("⚠️  WARNING: --serial-port is deprecated. Use --host and --port for ethernet.")
            # If serial_port looks like an IP, use it as host
            if '.' in str(args.serial_port) and str(args.serial_port).replace('.', '').replace(':', '').isdigit():
                host_to_use = str(args.serial_port).split(':')[0]  # Extract host if port is included
                print(f"   Using {host_to_use} as ethernet host")
            else:
                print(f"   Using default ethernet host: {args.host}")
                host_to_use = args.host
        else:
            host_to_use = args.host
        
        opta_cfg = OptaConfig(
            host=host_to_use,
            port=args.port,
            vici_id=str(args.vici_id),
            pump_id=str(args.pump_id),
            solenoid_relay_id=str(args.solenoid_relay_id),
            ml_per_rev=float(args.ml_per_rev),
        )
        adapter = OptaHardwareAdapter(opta_cfg)
        if not adapter.connect():
            print(f"❌ Failed to connect to Arduino Opta at {host_to_use}:{args.port}")
            print("   Check ethernet cable, Opta power, and network configuration.")
            return 1

        print("🔧 Connected to Opta. Beginning hardware execution...")
        
        # Use pure hardware executor (no simulation dependencies)
        from src.execution.hardware_executor import HardwareExecutor
        hw_executor = HardwareExecutor(coordinator, adapter)
        
        print(f"▶️  Starting hardware execution")
        results = hw_executor.execute_synthesis_schedule(schedule)
        
        # Check results
        failed_steps = [r for r in results if not r.success]
        if failed_steps:
            print(f"❌ Hardware execution failed. {len(failed_steps)} steps failed:")
            for result in failed_steps:
                print(f"   Step {result.step_number}: {result.error_message}")
            adapter.disconnect()
            return 1
        
        # Export execution log
        output_dir = args.output_dir / "hardware_runs"
        output_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"hardware_run_{schedule.synthesis_id}_{run_id}.csv"
        info = {
            "program_id": f"{params.peptide_sequence}_hardware",
            "scale_mmol": params.target_scale_mmol,
            "step_count": len(schedule.steps),
            "estimated_duration_minutes": schedule.total_estimated_time_minutes,
        }
        
        hw_executor.export_execution_log(csv_path, info)
        summary = hw_executor.get_execution_summary()
        
        print(f"✅ Hardware execution complete: {summary['successful_steps']}/{summary['total_steps']} steps successful")
        print(f"📄 Execution log: {csv_path}")
        
        adapter.disconnect()
        return 0

    except Exception as e:
        print(f"❌ Hardware execution failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main() -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    if not args.quiet:
        setup_logging(args.verbose)
    
    # Handle create-config mode
    if args.create_config:
        config_path = Path(args.create_config)
        print(f"📝 Creating default configuration: {config_path}")
        
        if create_default_config_file(config_path):
            print("✅ Configuration file created successfully!")
            return 0
        else:
            print("❌ Failed to create configuration file")
            return 1
    
    # Ensure programs directory exists
    if not args.programs_dir.exists():
        print(f"❌ Programs directory not found: {args.programs_dir}")
        print("   Run synthesis tests first to compile programs")
        return 1
    
    # Handle different modes
    if args.sequence:
        # File-based mode
        if not args.sequence.exists():
            print(f"❌ Sequence file not found: {args.sequence}")
            return 1
        
        if args.simulated:
            return run_simulation_mode(args.sequence, args)
        elif args.recipe_only:
            return run_recipe_only_mode(args.sequence, args)
        else:
            return run_hardware_mode(args.sequence, args)
    
    else:
        # Interactive mode (default)
        if args.recipe_only:
            print("❌ Recipe-only mode requires --sequence option")
            return 1
        
        print("🧪 Virtual Peptide Reactor")
        print("Starting interactive mode...")
        
        try:
            run_interactive_mode()
            return 0
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            return 0
        except Exception as e:
            print(f"❌ Interactive mode failed: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            return 1


if __name__ == "__main__":
    sys.exit(main())
