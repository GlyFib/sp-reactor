"""
Command exporter for generating CSV tables of atomic device commands.
Helps verify the complete command sequence for a synthesis program.
"""

import csv
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import logging

from .hardware_commands import HardwareCommand
from .composite_functions import CompositeFunction
from ..hardware.config import get_hardware_config, get_hardware_manager


@dataclass
class AtomicCommandRecord:
    """Record for a single atomic device command in the synthesis sequence."""
    # Required fields first (no defaults)
    sequence_number: int
    program_step: int
    composite_function: str
    atomic_command_index: int
    device: str
    command_type: str
    parameters: Dict[str, Any]
    mock_command: str
    estimated_duration_seconds: float
    # Optional fields with defaults after
    comments: str = ""
    device_id: str = ""
    # Hardware-oriented optional fields (mostly for pump commands)
    rpm: Optional[float] = None
    direction: Optional[str] = None  # '+' or '-'
    revolutions: Optional[float] = None
    
    def to_csv_row(self) -> Dict[str, str]:
        """Convert to CSV row dictionary."""
        # Format parameters as readable string
        param_str = ", ".join([f"{k}={v}" for k, v in self.parameters.items()])
        
        return {
            "Sequence": self.sequence_number,
            "Program_Step": self.program_step,
            "Composite_Function": self.composite_function,
            "Atomic_Index": self.atomic_command_index,
            "Device": self.device,
            "Device_ID": self.device_id,
            "Command_Type": self.command_type,
            "Parameters": param_str,
            "Mock_Command": self.mock_command,
            "Duration_Seconds": self.estimated_duration_seconds,
            "RPM": f"{self.rpm:.3f}" if isinstance(self.rpm, (int, float)) else "",
            "Direction": self.direction or "",
            "Revolutions": f"{self.revolutions:.6f}" if isinstance(self.revolutions, (int, float)) else "",
            "Comments": self.comments
        }


class CommandTrackingExecutor:
    """Hardware command executor that tracks all executed commands for export."""
    
    def __init__(self, mock_mode: bool = True):
        self.mock_mode = mock_mode
        self.command_records = []
        self.sequence_counter = 0
        self.logger = logging.getLogger("command_tracking_executor")
    
    def execute_commands_with_tracking(self, 
                                     commands: List[HardwareCommand], 
                                     program_step: int,
                                     composite_function_id: str,
                                     device_manager=None) -> List[str]:
        """Execute commands and track them for export."""
        results = []
        
        for i, command in enumerate(commands):
            self.sequence_counter += 1
            
            # Determine device from command type
            device = self._get_device_from_command(command)
            device_id = self._get_device_id_for_command(device_manager, device)
            
            # Get command parameters
            parameters = self._extract_command_parameters(command)
            
            # Estimate duration
            duration = self._estimate_command_duration(command)

            # Derive hardware metrics (rpm, direction, revolutions) for pump
            rpm, direction, revolutions = self._derive_pump_metrics(command, device_manager)
            
            # Execute command
            if self.mock_mode:
                mock_command = command.to_mock_command()
                results.append(mock_command)
                self.logger.info(f"Mock: {mock_command}")
            else:
                if device_manager is None:
                    self.logger.error("Device manager required for real mode")
                    results.append(f"ERROR: No device manager")
                    continue
                
                success = command.execute_real(device_manager)
                if success:
                    mock_command = command.to_mock_command()
                    results.append(f"OK: {command.description}")
                    self.logger.info(f"Executed: {command.description}")
                else:
                    mock_command = f"FAILED: {command.description}"
                    results.append(f"FAILED: {command.description}")
                    self.logger.error(f"Failed: {command.description}")
            
            # Create command record
            record = AtomicCommandRecord(
                sequence_number=self.sequence_counter,
                program_step=program_step,
                composite_function=composite_function_id,
                atomic_command_index=i + 1,
                device=device,
                device_id=device_id,
                command_type=command.command_id,
                parameters=parameters,
                mock_command=command.to_mock_command(),
                estimated_duration_seconds=duration,
                comments=command.description,
                rpm=rpm,
                direction=direction,
                revolutions=revolutions
            )
            
            self.command_records.append(record)
        
        return results
    
    def _get_device_from_command(self, command: HardwareCommand) -> str:
        """Determine which device this command targets."""
        command_type = command.command_id.lower()
        
        if "valve" in command_type or "move" in command_type:
            return "vici_valve"
        elif "pump" in command_type:
            return "masterflex_pump"
        elif "solenoid" in command_type or "drain" in command_type:
            return "solenoid_valve"
        elif "wait" in command_type:
            return "system"
        else:
            return "unknown"
    
    def _extract_command_parameters(self, command: HardwareCommand) -> Dict[str, Any]:
        """Extract relevant parameters from command."""
        params = {}
        
        # Extract dataclass fields as parameters
        for field_name, field_value in command.__dict__.items():
            if not field_name.startswith('_') and field_name not in ['command_id', 'description']:
                if field_value is not None:
                    params[field_name] = field_value
        
        return params
    
    def _estimate_command_duration(self, command: HardwareCommand) -> float:
        """Estimate command execution duration in seconds."""
        command_type = command.command_id.lower()
        
        # Check if command has explicit duration
        if hasattr(command, 'duration_seconds') and command.duration_seconds:
            return float(command.duration_seconds)
        elif hasattr(command, 'time_seconds') and command.time_seconds:
            return float(command.time_seconds)
        
        # Default estimates based on command type
        if "move" in command_type or "valve" in command_type:
            return 2.0  # Valve movement time
        elif "pump" in command_type:
            # Estimate based on volume and flow rate
            if hasattr(command, 'volume_ml') and hasattr(command, 'flow_rate_ml_min'):
                volume = getattr(command, 'volume_ml', 0)
                flow_rate = getattr(command, 'flow_rate_ml_min', 10)
                if flow_rate > 0:
                    return (volume / flow_rate) * 60  # Convert minutes to seconds
            return 30.0  # Default pump time
        elif "solenoid" in command_type or "drain" in command_type:
            return 30.0  # Default drain time
        elif "wait" in command_type:
            return getattr(command, 'duration_seconds', 0)
        else:
            return 5.0  # Default command time
    
    def export_to_csv(self, output_path: Path, synthesis_info: Dict[str, Any] = None) -> Path:
        """Export all tracked commands to CSV file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # CSV headers
        headers = [
            "Sequence",
            "Program_Step", 
            "Composite_Function",
            "Atomic_Index",
            "Device",
            "Device_ID",
            "Command_Type",
            "Parameters",
            "Mock_Command",
            "Duration_Seconds",
            "RPM",
            "Direction",
            "Revolutions",
            "Comments"
        ]
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            
            # Write header
            writer.writeheader()
            
            # Write synthesis info as comments
            if synthesis_info:
                writer.writerow({
                    "Sequence": f"# Synthesis: {synthesis_info.get('program_id', 'Unknown')}",
                    "Program_Step": f"# Scale: {synthesis_info.get('scale_mmol', 'Unknown')} mmol",
                    "Composite_Function": f"# Generated: {datetime.now().isoformat()}",
                    "Atomic_Index": f"# Total Steps: {len(self.command_records)}",
                    "Device": "",
                    "Command_Type": "",
                    "Parameters": "",
                    "Mock_Command": "",
                    "Duration_Seconds": "",
                    "Comments": ""
                })
                writer.writerow({})  # Empty row
            
            # Write command records
            for record in self.command_records:
                writer.writerow(record.to_csv_row())
        
        self.logger.info(f"Exported {len(self.command_records)} commands to {output_path}")
        return output_path
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """Get summary statistics of tracked commands."""
        if not self.command_records:
            return {}
        
        # Count by device
        device_counts = {}
        total_duration = 0
        command_type_counts = {}
        
        for record in self.command_records:
            # Device counts
            device_counts[record.device] = device_counts.get(record.device, 0) + 1
            
            # Total duration
            total_duration += record.estimated_duration_seconds
            
            # Command type counts
            command_type_counts[record.command_type] = command_type_counts.get(record.command_type, 0) + 1
        
        return {
            "total_commands": len(self.command_records),
            "total_duration_seconds": total_duration,
            "total_duration_minutes": total_duration / 60,
            "device_usage": device_counts,
            "command_types": command_type_counts,
            "average_command_duration": total_duration / len(self.command_records) if self.command_records else 0
        }
    
    def clear_tracking(self):
        """Clear all tracked command records."""
        self.command_records.clear()
        self.sequence_counter = 0
        self.logger.info("Cleared command tracking records")

    # -------------------------------
    # Helpers for device IDs and metrics
    # -------------------------------
    def _get_device_id_for_command(self, device_manager, device: str) -> str:
        """Resolve device_id for CSV using universal hardware configuration."""
        try:
            # Always use universal hardware configuration first
            hw_manager = get_hardware_manager()
            device_id = hw_manager.get_device_id(device)
            if device_id:
                return device_id
            
            # Fallback to device_manager if present (for backwards compatibility)
            if device_manager is None:
                return ""
            # Opta adapter path
            if hasattr(device_manager, "is_opta_adapter") and getattr(device_manager, "is_opta_adapter"):
                cfg = getattr(device_manager, "config", None)
                if not cfg:
                    return ""
                if device == "vici_valve":
                    return getattr(cfg, "vici_id", "")
                if device == "masterflex_pump":
                    return getattr(cfg, "pump_id", "")
                if device == "solenoid_valve":
                    return getattr(cfg, "solenoid_relay_id", "")
                return ""
            # Legacy device manager path
            if hasattr(device_manager, "get_device"):
                dev = device_manager.get_device(device)
                if dev and hasattr(dev, "device_id"):
                    return str(dev.device_id)
            return ""
        except Exception:
            return ""

    def _derive_pump_metrics(self, command: HardwareCommand, device_manager) -> tuple[Optional[float], Optional[str], Optional[float]]:
        """Compute RPM, direction (+/-), and revolutions for pump commands when possible."""
        try:
            if getattr(command, "command_id", "").lower() not in ["pump_reagent", "pump_time", "pump"]:
                return None, None, None
                
            flow = getattr(command, "flow_rate_ml_min", None)
            volume = getattr(command, "volume_ml", None)
            direction_str = getattr(command, "direction", "clockwise")

            # Get ml_per_rev from universal hardware configuration
            hw_config = get_hardware_config()
            ml_per_rev = hw_config.masterflex_pump.ml_per_revolution
            
            # Fallback to device_manager if universal config not available
            if ml_per_rev is None:
                if device_manager is not None and hasattr(device_manager, "is_opta_adapter") and getattr(device_manager, "is_opta_adapter"):
                    cfg = getattr(device_manager, "config", None)
                    if cfg and hasattr(cfg, "ml_per_rev"):
                        ml_per_rev = float(cfg.ml_per_rev)

            # Derive RPM only if we know ml_per_rev and flow
            rpm = None
            revolutions = None
            if ml_per_rev and flow:
                rpm = max(0.0, float(flow) / ml_per_rev)
            if ml_per_rev and volume:
                revolutions = max(0.0, float(volume) / ml_per_rev)

            # Map direction to + / - symbols
            symbol = None
            d = (direction_str or "").lower().strip()
            if d.startswith("counter") or d.startswith("anti") or d.startswith("rev"):
                symbol = "-"
            elif d.startswith("clock") or d.startswith("forw") or d.startswith("cw"):
                symbol = "+"

            return rpm, symbol, revolutions
        except Exception as e:
            self.logger.debug(f"Failed to derive pump metrics: {e}")
            return None, None, None


class SynthesisCommandExporter:
    """High-level exporter for synthesis program atomic commands."""
    
    def __init__(self, output_dir: Path = None):
        self.output_dir = Path(output_dir) if output_dir else Path("output/command_exports")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("synthesis_command_exporter")
    
    def export_synthesis_commands(self, 
                                program_id: str,
                                target_scale_mmol: float,
                                output_filename: str = None) -> Path:
        """Export all atomic commands for a synthesis program."""
        from ..programs.programs import get_program
        
        # Get the program
        program = get_program(program_id)
        if not program:
            raise ValueError(f"Program not found: {program_id}")
        
        # Compile program for the target scale
        program_data = program.compile_for_scale(target_scale_mmol)
        if not program_data:
            raise ValueError(f"Failed to compile program: {program_id}")
        
        # Create tracking executor
        executor = CommandTrackingExecutor(mock_mode=True)
        
        self.logger.info(f"Exporting commands for {program_id} at {target_scale_mmol} mmol scale")
        
        # Execute all steps with tracking
        for step_data in program_data['steps']:
            success = self._execute_step_with_tracking(step_data, executor)
            if not success:
                self.logger.warning(f"Step {step_data['seq']} failed during export")
        
        # Generate output filename
        if not output_filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            scale_str = f"{target_scale_mmol:.1f}mmol".replace('.', 'p')
            output_filename = f"{program_id}_commands_{scale_str}_{timestamp}.csv"
        
        output_path = self.output_dir / output_filename
        
        # Export to CSV
        synthesis_info = {
            "program_id": program_id,
            "scale_mmol": target_scale_mmol,
            "step_count": len(program_data['steps']),
            "estimated_duration_minutes": program_data.get('estimated_duration_minutes', 0)
        }
        
        csv_path = executor.export_to_csv(output_path, synthesis_info)
        
        # Print summary
        stats = executor.get_summary_statistics()
        self.logger.info(f"Export complete: {stats['total_commands']} commands, "
                        f"{stats['total_duration_minutes']:.1f} minutes total")
        
        return csv_path
    
    def _execute_step_with_tracking(self, step_data: Dict[str, Any], executor: CommandTrackingExecutor) -> bool:
        """Execute a program step with command tracking."""
        try:
            from ..functions.composite_functions import get_composite_function
            
            function_id = step_data['function_id']
            params = step_data['params']
            
            # Get composite function
            composite_function = get_composite_function(function_id)
            if not composite_function:
                self.logger.error(f"Composite function not found: {function_id}")
                return False
            
            # Parse parameters and generate commands
            if not composite_function.parse_parameters(**params):
                self.logger.error(f"Parameter parsing failed: {composite_function.last_error}")
                return False
            
            commands = composite_function.generate_hardware_commands(**params)
            
            # Execute with tracking
            results = executor.execute_commands_with_tracking(
                commands,
                step_data['seq'],
                function_id
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Step execution failed during export: {e}")
            return False
