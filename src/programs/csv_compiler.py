import csv
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class ProgramStep:
    """Program step with integrated chemistry calculations."""
    seq: int
    source_step_id: str
    group_id: str
    function_id: str
    volume_per_mmol: Optional[float]  # mL per mmol scale
    time_seconds: Optional[float]
    reagent_port: Optional[str]
    dest_port: Optional[str]
    loop: Optional[Dict[str, Any]] = None
    comments: Optional[str] = None
    # Original parameters from CSV for composite functions
    param1: Optional[str] = None
    param2: Optional[str] = None
    
    def calculate_volume(self, target_scale_mmol: float) -> float:
        """Calculate actual volume from scale."""
        if self.volume_per_mmol:
            return self.volume_per_mmol * target_scale_mmol
        return 0.0
    
    def to_executable_params(self, target_scale_mmol: float) -> Dict[str, Any]:
        """Convert to executable parameters for composite functions."""
        params = {}
        
        # Add scale information
        params["target_scale_mmol"] = target_scale_mmol
        
        # Calculate actual volume
        if self.volume_per_mmol:
            params["volume_ml"] = self.calculate_volume(target_scale_mmol)
            params["volume_per_mmol"] = self.volume_per_mmol
        
        # Add timing
        if self.time_seconds:
            params["time_seconds"] = self.time_seconds
            params["time_minutes"] = self.time_seconds / 60.0
        
        # Add port information
        if self.reagent_port:
            params["source_port"] = self.reagent_port
            params["valve_position"] = self._port_to_valve_position(self.reagent_port)
        
        if self.dest_port:
            params["dest_port"] = self.dest_port
        
        # Add original CSV parameters for composite function parsing
        if self.param1:
            params["param1"] = self.param1
        
        if self.param2:
            params["param2"] = self.param2
        
        # Add loop information
        if self.loop:
            params["loop_info"] = self.loop
        
        return params
    
    def _port_to_valve_position(self, port: str) -> int:
        """Convert port name to VICI valve position."""
        port_positions = {
            'R1': 1, 'R2': 2, 'R3': 3, 'R4': 4, 'R5': 5, 'R6': 6,
            'MV': 0, 'RV': 7
        }
        return port_positions.get(port, 0)


class CSVCompiler:
    """Compiles enhanced CSV files with integrated chemistry into executable programs."""
    
    def __init__(self, build_dir: Path):
        self.build_dir = Path(build_dir)
        self.build_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("csv_compiler")
    
    def compile_program(self, csv_path: Path, target_scale_mmol: float = 1.0, 
                       program_version: str = "1.0") -> Path:
        """
        Compile enhanced CSV into executable JSON program.
        
        Args:
            csv_path: Path to enhanced CSV file
            target_scale_mmol: Target synthesis scale in mmol
            program_version: Program version
        
        Returns:
            Path to compiled JSON file
        """
        self.logger.info(f"Compiling enhanced CSV from {csv_path} at {target_scale_mmol} mmol scale")
        
        # Load and parse enhanced CSV
        raw_steps = self._load_enhanced_csv(csv_path)
        
        # Expand loops
        expanded_steps = self._expand_loops(raw_steps)
        
        # Build executable plan with calculated volumes
        executable_steps = self._build_executable_plan(expanded_steps, target_scale_mmol)
        
        # Create program structure
        program = {
            "program_id": csv_path.stem,
            "version": program_version,
            "source_file": str(csv_path),
            "target_scale_mmol": target_scale_mmol,
            "compiled_at": self._get_timestamp(),
            "chemistry_integrated": True,
            "steps": executable_steps,
            "step_count": len(executable_steps),
            "estimated_duration_minutes": self._calculate_duration(expanded_steps)
        }
        
        # Generate output path
        scale_suffix = f"{target_scale_mmol:.1f}mmol".replace('.', 'p')
        content_hash = self._calculate_hash(csv_path, target_scale_mmol, program_version)
        output_path = self.build_dir / f"{csv_path.stem}_{scale_suffix}_{content_hash}.json"
        
        # Write atomically
        self._write_json_atomically(program, output_path)
        
        self.logger.info(f"Compiled enhanced program to {output_path}")
        return output_path
    
    def _load_enhanced_csv(self, csv_path: Path) -> List[ProgramStep]:
        """Load CSV with support for both old and new formats."""
        steps = []
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            
            # Determine CSV format
            has_old_format = {'param1', 'param2', 'type'}.issubset(headers)
            has_new_format = {'volume_per_mmol', 'time_seconds'}.issubset(headers)
            
            if has_old_format:
                self.logger.info("Detected old CSV format (param1/param2)")
            elif has_new_format:
                self.logger.info("Detected new enhanced CSV format")
            else:
                self.logger.warning("Unknown CSV format, attempting to parse...")
            
            for row_num, row in enumerate(reader, start=2):
                # Skip empty rows and comments
                if not row['step_id'] or row['step_id'].startswith('#'):
                    continue
                
                try:
                    if has_old_format:
                        step = self._parse_old_format_row(row, row_num)
                    else:
                        step = self._parse_enhanced_row(row, row_num)
                    
                    if step:
                        steps.append(step)
                except Exception as e:
                    self.logger.warning(f"Skipping row {row_num}: {e}")
                    continue
        
        return steps
    
    def _parse_enhanced_row(self, row: Dict[str, str], row_num: int) -> Optional[ProgramStep]:
        """Parse a row from enhanced CSV format."""
        try:
            step_id = row['step_id'].strip()
            if not step_id or not step_id.isdigit():
                return None
            
            group_id = row['group_id'].strip() or step_id
            loop_type = row['loop_type'].strip()
            function_id = row['function_id'].strip()
            
            if not function_id:
                return None
            
            # Parse numeric fields
            volume_per_mmol = None
            if row['volume_per_mmol'].strip():
                try:
                    volume_per_mmol = float(row['volume_per_mmol'])
                except ValueError:
                    pass
            
            time_seconds = None
            if row['time_seconds'].strip():
                try:
                    time_seconds = float(row['time_seconds'])
                except ValueError:
                    pass
            
            loop_times = None
            if row['loop_times'].strip():
                try:
                    loop_times = int(row['loop_times'])
                except ValueError:
                    pass
            
            # Parse function command
            function_id, structural_params = self._parse_function_command(function_id)
            
            return ProgramStep(
                seq=0,  # Will be set during expansion
                source_step_id=step_id,
                group_id=group_id,
                function_id=function_id,
                volume_per_mmol=volume_per_mmol,
                time_seconds=time_seconds,
                reagent_port=row['reagent_port'].strip() or None,
                dest_port=row['dest_port'].strip() or None,
                comments=row['comments'].strip() or None
            )
            
        except Exception as e:
            raise ValueError(f"Error parsing row {row_num}: {e}")
    
    def _parse_old_format_row(self, row: Dict[str, str], row_num: int) -> Optional[ProgramStep]:
        """Parse a row from old CSV format (param1/param2/type)."""
        try:
            step_id = row['step_id'].strip()
            if not step_id or not step_id.isdigit():
                return None
            
            group_id = row['group_id'].strip() or step_id
            loop_type = row.get('type', '').strip()  # 'type' in old format, 'loop_type' in new
            function_id = row['function_id'].strip()
            
            if not function_id:
                return None
            
            # Handle loop times
            loop_times = None
            if row.get('loop_times', '').strip():
                try:
                    loop_times = int(row['loop_times'])
                except ValueError:
                    pass
            
            # Parse parameters from param1 and param2
            volume_per_mmol = None
            time_seconds = None
            
            param1 = row.get('param1', '').strip()
            param2 = row.get('param2', '').strip()
            
            # Try to extract volume from param1 (e.g., "v_1", "v_2")
            if param1.startswith('v_'):
                try:
                    volume_multiplier = float(param1[2:])
                    # Default volume calculation - will be overridden by chemistry calculations
                    volume_per_mmol = volume_multiplier * 10.0  # 10 mL per mmol as default
                except ValueError:
                    pass
            
            # Try to extract time from param1 or param2 (e.g., "60s", "180s")
            for param in [param1, param2]:
                if param.endswith('s'):
                    try:
                        time_seconds = float(param[:-1])
                        break
                    except ValueError:
                        continue
            
            # Parse function command to get final function_id
            function_id, structural_params = self._parse_function_command(function_id)
            
            step = ProgramStep(
                seq=0,  # Will be set during expansion
                source_step_id=step_id,
                group_id=group_id,
                function_id=function_id,
                volume_per_mmol=volume_per_mmol,
                time_seconds=time_seconds,
                reagent_port=None,  # Not specified in old format
                dest_port=None,     # Not specified in old format
                comments=row.get('comments', '').strip() or None,
                param1=param1 or None,
                param2=param2 or None
            )
            
            # Add loop information for NL types
            if loop_type == 'NL' and loop_times:
                step.loop_type = loop_type
                step.loop_times = loop_times
            
            return step
            
        except Exception as e:
            raise ValueError(f"Error parsing old format row {row_num}: {e}")
    
    def _parse_function_command(self, command: str) -> Tuple[str, Dict[str, Any]]:
        """Parse function command and return (function_id, structural_params)."""
        cmd = command.upper().strip()
        
        # Preserve composite function IDs instead of translating to atomic functions
        # This allows the functions layer to handle composite functions directly
        return cmd, {}
    
    def _expand_loops(self, steps: List[ProgramStep]) -> List[ProgramStep]:
        """Expand NL (nested loop) blocks."""
        expanded = []
        i = 0
        
        while i < len(steps):
            step = steps[i]
            
            # Check for NL loop
            if hasattr(step, 'loop_type') and step.loop_type == 'NL':
                # Find loop block
                nl_group_id = step.group_id
                nl_steps = []
                
                j = i
                while (j < len(steps) and 
                       hasattr(steps[j], 'loop_type') and
                       steps[j].group_id == nl_group_id and
                       steps[j].loop_type == 'NL'):
                    nl_steps.append(steps[j])
                    j += 1
                
                # Get loop count from first step
                loop_times = getattr(steps[i], 'loop_times', 1) or 1
                
                # Expand loop
                for loop_index in range(1, loop_times + 1):
                    for nl_step in nl_steps:
                        expanded_step = ProgramStep(
                            seq=0,  # Will be set later
                            source_step_id=nl_step.source_step_id,
                            group_id=nl_step.group_id,
                            function_id=nl_step.function_id,
                            volume_per_mmol=nl_step.volume_per_mmol,
                            time_seconds=nl_step.time_seconds,
                            reagent_port=nl_step.reagent_port,
                            dest_port=nl_step.dest_port,
                            loop={
                                'group_id': nl_group_id,
                                'loop_times': loop_times,
                                'loop_index': loop_index
                            },
                            comments=nl_step.comments,
                            param1=nl_step.param1,
                            param2=nl_step.param2
                        )
                        expanded.append(expanded_step)
                
                i = j
            else:
                expanded.append(step)
                i += 1
        
        # Set sequence numbers
        for seq, step in enumerate(expanded, start=1):
            step.seq = seq
        
        return expanded
    
    def _build_executable_plan(self, steps: List[ProgramStep], 
                              target_scale_mmol: float) -> List[Dict[str, Any]]:
        """Build executable plan with calculated volumes."""
        executable_steps = []
        
        for step in steps:
            exec_step = {
                "seq": step.seq,
                "source_step_id": step.source_step_id,
                "group_id": step.group_id,
                "function_id": step.function_id,
                "params": step.to_executable_params(target_scale_mmol),
                "loop": step.loop,
                "comments": step.comments
            }
            
            # Add calculated volume info for tracking
            if step.volume_per_mmol:
                exec_step["volume_calculation"] = {
                    "volume_per_mmol": step.volume_per_mmol,
                    "target_scale_mmol": target_scale_mmol,
                    "calculated_volume_ml": step.calculate_volume(target_scale_mmol)
                }
            
            executable_steps.append(exec_step)
        
        return executable_steps
    
    def _calculate_duration(self, steps: List[ProgramStep]) -> float:
        """Calculate total program duration."""
        total_minutes = 0.0
        
        for step in steps:
            if step.time_seconds:
                total_minutes += step.time_seconds / 60.0
            elif step.function_id == "transfer_reagent":
                total_minutes += 1.0  # Default transfer time
            else:
                total_minutes += 0.5  # Default step time
        
        return total_minutes
    
    def _calculate_hash(self, csv_path: Path, scale: float, version: str) -> str:
        """Calculate hash including scale."""
        hasher = hashlib.sha256()
        
        with open(csv_path, 'rb') as f:
            hasher.update(f.read())
        
        hasher.update(str(scale).encode('utf-8'))
        hasher.update(version.encode('utf-8'))
        
        return hasher.hexdigest()[:8]
    
    def _write_json_atomically(self, data: Dict[str, Any], output_path: Path):
        """Write JSON atomically, replacing existing file safely on Windows."""
        # Ensure target directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Use a deterministic temp name next to the target
        temp_path = output_path.with_suffix('.tmp')

        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)

        # Replace destination atomically; works even if destination exists
        temp_path.replace(output_path)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


# Convenience function
def compile_csv(csv_path: Path, build_dir: Path, target_scale_mmol: float = 1.0) -> Path:
    """Compile CSV with integrated chemistry."""
    compiler = CSVCompiler(build_dir)
    return compiler.compile_program(csv_path, target_scale_mmol)
