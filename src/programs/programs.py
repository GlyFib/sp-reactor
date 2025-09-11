from typing import Dict, Any, List, Optional
import json
import logging
from pathlib import Path
from .csv_compiler import compile_csv


class ProgramDefinition:
    """Program definition using enhanced CSV format with integrated chemistry."""
    
    def __init__(self, program_id: str, csv_path: Path, build_dir: Path):
        self.program_id = program_id
        self.csv_path = csv_path
        self.build_dir = build_dir
        self.logger = logging.getLogger(f"program.{program_id}")
        self.last_error = None
        self._compiled_programs = {}  # Cache compiled programs by scale
        
    def compile_for_scale(self, target_scale_mmol: float) -> Optional[Dict[str, Any]]:
        """Compile CSV program for specific scale."""
        scale_key = f"{target_scale_mmol:.3f}"
        
        if scale_key not in self._compiled_programs:
            try:
                compiled_path = compile_csv(
                    self.csv_path, 
                    self.build_dir, 
                    target_scale_mmol=target_scale_mmol
                )
                
                with open(compiled_path, 'r') as f:
                    program_data = json.load(f)
                
                self._compiled_programs[scale_key] = program_data
                self.logger.info(f"Compiled {self.program_id} for {target_scale_mmol} mmol scale")
                
            except Exception as e:
                self.last_error = f"Compilation failed: {e}"
                self.logger.error(self.last_error)
                return None
        
        return self._compiled_programs[scale_key]
    
    def execute(self, device_manager, **parameters) -> bool:
        """Execute the program with given parameters."""
        try:
            # Extract scale from parameters
            target_scale_mmol = parameters.get('resin_mmol', 0.1)  # Default 0.1 mmol
            
            # Compile program for this scale
            program_data = self.compile_for_scale(target_scale_mmol)
            if not program_data:
                return False
            
            self.logger.info(f"Executing {self.program_id} at {target_scale_mmol} mmol scale")
            self.logger.info(f"Program has {program_data['step_count']} steps, "
                           f"estimated duration: {program_data['estimated_duration_minutes']:.1f} min")
            
            # Execute each step
            for step_data in program_data['steps']:
                if not self._execute_step(step_data, device_manager):
                    return False
            
            self.logger.info(f"Program {self.program_id} completed successfully")
            return True
            
        except Exception as e:
            self.last_error = f"Execution failed: {e}"
            self.logger.error(self.last_error)
            return False
    
    def _execute_step(self, step_data: Dict[str, Any], device_manager) -> bool:
        """Execute a single program step using composite functions."""
        try:
            function_id = step_data['function_id']
            params = step_data['params']
            
            self.logger.debug(f"Executing step {step_data['seq']}: {function_id}")
            
            # Import and execute the composite function
            from src.functions.composite_functions import get_composite_function
            
            composite_function = get_composite_function(function_id)
            if not composite_function:
                self.last_error = f"Composite function not found: {function_id}"
                return False
            
            # Execute with parameters (mock mode for now)
            mock_mode = True  # TODO: Make this configurable
            success, results = composite_function.execute(
                device_manager=device_manager, 
                mock_mode=mock_mode, 
                **params
            )
            
            if not success:
                self.last_error = f"Step {step_data['seq']} failed: {composite_function.last_error}"
                return False
            
            # Log the hardware commands that were generated
            self.logger.info(f"Generated commands for {function_id}:")
            for i, command_result in enumerate(results, 1):
                self.logger.info(f"  {i}. {command_result}")
            
            return True
            
        except Exception as e:
            self.last_error = f"Step execution failed: {e}"
            return False
    
    def estimate_duration(self, **parameters) -> float:
        """Estimate program duration in minutes."""
        target_scale_mmol = parameters.get('resin_mmol', 0.1)
        program_data = self.compile_for_scale(target_scale_mmol)
        
        if program_data:
            return program_data.get('estimated_duration_minutes', 0.0)
        return 0.0
    
    def validate_parameters(self, **parameters) -> bool:
        """Validate program parameters."""
        required_params = ['resin_mmol']
        
        for param in required_params:
            if param not in parameters:
                self.last_error = f"Missing required parameter: {param}"
                return False
        
        resin_mmol = parameters['resin_mmol']
        if not isinstance(resin_mmol, (int, float)) or resin_mmol <= 0:
            self.last_error = "resin_mmol must be a positive number"
            return False
        
        return True
    
    def get_required_devices(self) -> List[str]:
        """Get list of required device IDs."""
        # For VICI + Masterflex + Solenoid setup
        return ["vici_valve", "masterflex_pump", "solenoid_valve"]
    
    def get_parameter_definitions(self) -> Dict[str, Any]:
        """Get parameter definitions for this program."""
        return {
            "resin_mmol": {
                "type": float,
                "required": True,
                "min": 0.001,
                "max": 10.0,
                "description": "Amount of resin in mmol (determines volumes)"
            },
            "amino_acid": {
                "type": str,
                "required": False,
                "description": "Single letter amino acid code (for coupling programs)"
            }
        }


# Program Registry
class ProgramRegistry:
    """Registry for CSV-based programs."""
    
    def __init__(self, csv_source_dir: Path, build_dir: Path):
        self.csv_source_dir = Path(csv_source_dir)
        self.build_dir = Path(build_dir)
        self.build_dir.mkdir(exist_ok=True)
        self.programs = {}
        self.logger = logging.getLogger("program_registry")
        
        # Auto-discover CSV programs
        self._discover_programs()
    
    def _discover_programs(self):
        """Discover CSV programs in source directory."""
        if not self.csv_source_dir.exists():
            self.logger.warning(f"CSV source directory not found: {self.csv_source_dir}")
            return
        
        for csv_file in self.csv_source_dir.glob("*.csv"):
            program_id = csv_file.stem
            program = ProgramDefinition(program_id, csv_file, self.build_dir)
            self.programs[program_id] = program
            
        self.logger.info(f"Discovered {len(self.programs)} programs: {list(self.programs.keys())}")
    
    def get_program(self, program_id: str) -> Optional[ProgramDefinition]:
        """Get program by ID."""
        return self.programs.get(program_id)
    
    def list_programs(self) -> List[str]:
        """List all available program IDs."""
        return list(self.programs.keys())


# Global registry instance
_program_registry = None

def get_program_registry(csv_source_dir: Path = None, build_dir: Path = None) -> ProgramRegistry:
    """Get the global program registry."""
    global _program_registry
    
    if _program_registry is None:
        if csv_source_dir is None:
            csv_source_dir = Path(__file__).parent.parent.parent / "data" / "programs"
        if build_dir is None:
            build_dir = Path(__file__).parent / "compiled"
        
        _program_registry = ProgramRegistry(csv_source_dir, build_dir)
    
    return _program_registry

def get_program(program_id: str) -> Optional[ProgramDefinition]:
    """Get program definition by ID."""
    registry = get_program_registry()
    return registry.get_program(program_id)


# Enhanced program interface (for backward compatibility)
def get_enhanced_program_registry(csv_source_dir: Path = None, build_dir: Path = None):
    """Get the enhanced program registry (compatibility wrapper)."""
    return get_program_registry(csv_source_dir, build_dir)


def get_enhanced_program(program_id: str) -> Optional[ProgramDefinition]:
    """Get enhanced program definition by ID (compatibility wrapper)."""
    return get_program(program_id)