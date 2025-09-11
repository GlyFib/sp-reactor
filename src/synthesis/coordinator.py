import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import re

from .sequence_parser import PeptideSequence, PeptideSequenceParser
from .synthesis_utils import SynthesisUtils


@dataclass
class SynthesisParameters:
    """Parameters for a complete peptide synthesis."""
    peptide_sequence: str
    target_scale_mmol: float
    resin_substitution_mmol_g: float = 0.5  # Typical resin loading
    resin_mass_g: Optional[float] = None     # Calculated if not provided
    
    # Program selection - programs now contain their own chemistry
    aa_program: str = "aa_oxyma_dic_v1"      # Default Oxyma/DIC program
    begin_program: Optional[str] = None      # Initial setup program
    end_program: Optional[str] = None        # Final cleavage program
    
    # Synthesis conditions (chemistry now in programs)
    double_couple_difficult: bool = False     # Double couple Pro, etc.
    perform_capping: bool = True             # Cap unreacted sequences
    
    # Quality control
    monitor_coupling: bool = False           # Kaiser test, etc.
    save_sample_each_cycle: bool = False     # Sample collection


@dataclass  
class SynthesisStep:
    """Represents a single step in the synthesis schedule."""
    step_number: int
    amino_acid: Optional[str] = None           # Single letter code
    program_name: str = ""                     # Program to execute
    parameters: Dict[str, Any] = field(default_factory=dict)
    estimated_time_minutes: float = 0.0
    reagents_consumed: Dict[str, float] = field(default_factory=dict)
    notes: Optional[str] = None


@dataclass
class SynthesisSchedule:
    """Complete synthesis schedule with all steps and parameters."""
    synthesis_id: str
    peptide_sequence: str
    target_scale_mmol: float
    resin_mass_g: float
    
    steps: List[SynthesisStep] = field(default_factory=list)
    total_estimated_time_minutes: float = 0.0
    total_reagent_consumption: Dict[str, float] = field(default_factory=dict)
    
    created_at: Optional[str] = None
    created_by: Optional[str] = None


class ParameterSubstitution:
    """Handles parameter substitution in program templates."""
    
    def __init__(self):
        self.logger = logging.getLogger("parameter_substitution")
    
    def substitute_program_parameters(self, program_data: Dict[str, Any], 
                                    substitutions: Dict[str, Any]) -> Dict[str, Any]:
        """
        Substitute placeholder parameters in a compiled program with actual values.
        
        Args:
            program_data: Compiled program JSON data
            substitutions: Dictionary of placeholder -> actual value mappings
        
        Returns:
            Program data with substituted parameters
        """
        # Deep copy the program data
        substituted_program = json.loads(json.dumps(program_data))
        
        # Process each step
        for step in substituted_program.get('steps', []):
            if 'params' in step:
                step['params'] = self._substitute_params_dict(step['params'], substitutions)
        
        return substituted_program
    
    def _substitute_params_dict(self, params: Dict[str, Any], 
                               substitutions: Dict[str, Any]) -> Dict[str, Any]:
        """Substitute parameters in a dictionary."""
        substituted = {}
        
        for key, value in params.items():
            substituted[key] = self._substitute_value(value, substitutions)
        
        return substituted
    
    def _substitute_value(self, value: Any, substitutions: Dict[str, Any]) -> Any:
        """Substitute a single value."""
        if isinstance(value, str):
            return self._substitute_string_value(value, substitutions)
        elif isinstance(value, dict):
            return self._substitute_params_dict(value, substitutions)
        elif isinstance(value, list):
            return [self._substitute_value(item, substitutions) for item in value]
        else:
            return value
    
    def _substitute_string_value(self, value: str, substitutions: Dict[str, Any]) -> Any:
        """Substitute string value, handling templates and placeholders."""
        
        # Handle template expressions like {{ v_1 }}
        template_pattern = r'\{\{\s*([^}]+)\s*\}\}'
        matches = re.findall(template_pattern, value)
        
        if matches:
            # This is a template string
            result = value
            for match in matches:
                placeholder = match.strip()
                if placeholder in substitutions:
                    replacement = str(substitutions[placeholder])
                    result = result.replace('{{' + match + '}}', replacement)
                else:
                    self.logger.warning(f"No substitution found for placeholder: {placeholder}")
            
            # Try to convert to number if the entire result is numeric
            try:
                if '.' in result:
                    return float(result)
                else:
                    return int(result)
            except ValueError:
                return result
        
        # Handle direct placeholder substitution (like "v_1" -> actual value)
        if value in substitutions:
            return substitutions[value]
        
        return value


class SynthesisCoordinator:
    """Coordinates the complete synthesis process from sequence to execution."""
    
    def __init__(self, programs_dir: Path):
        self.logger = logging.getLogger("synthesis_coordinator") 
        self.programs_dir = Path(programs_dir)
        self.sequence_parser = PeptideSequenceParser()
        self.parameter_substitution = ParameterSubstitution()
        
        # Load available programs
        self.available_programs = self._discover_programs()
    
    def _discover_programs(self) -> Dict[str, Path]:
        """Discover available program files in the programs directory."""
        programs = {}
        
        # Look for compiled program files (legacy)
        compiled_dir = self.programs_dir / "compiled"
        if compiled_dir.exists():
            for json_file in compiled_dir.glob("*.json"):
                # Extract program name from filename (remove hash suffix)
                name = json_file.stem
                if '_' in name:
                    # Remove hash suffix (e.g., "program_aa_addition_default_31109abd" -> "program_aa_addition_default")
                    parts = name.split('_')
                    if len(parts[-1]) == 8:  # Hash is 8 characters
                        base_name = '_'.join(parts[:-1])
                        programs[base_name] = json_file
                    else:
                        programs[name] = json_file
                else:
                    programs[name] = json_file
        
        # Also discover enhanced CSV programs
        from ..programs.programs import get_enhanced_program_registry
        enhanced_registry = get_enhanced_program_registry()
        for program_name in enhanced_registry.list_programs():
            programs[program_name] = Path(f"enhanced:{program_name}")  # Mark as enhanced
        
        self.logger.info(f"Discovered {len(programs)} programs: {list(programs.keys())}")
        return programs
    
    def create_synthesis_schedule(self, params: SynthesisParameters) -> SynthesisSchedule:
        """Create a complete synthesis schedule from parameters."""
        self.logger.info(f"Creating synthesis schedule for {params.peptide_sequence}")
        
        # Parse peptide sequence
        peptide = self.sequence_parser.parse(params.peptide_sequence)
        
        # Calculate resin mass if not provided
        resin_mass_g = params.resin_mass_g
        if not resin_mass_g:
            resin_mass_g = SynthesisUtils.estimate_resin_mass(
                params.target_scale_mmol, params.resin_substitution_mmol_g
            )
        
        # Create synthesis schedule
        schedule = SynthesisSchedule(
            synthesis_id=self._generate_synthesis_id(peptide),
            peptide_sequence=params.peptide_sequence,
            target_scale_mmol=params.target_scale_mmol,
            resin_mass_g=resin_mass_g,
            created_at=datetime.now().isoformat()
        )
        
        # Build synthesis steps
        steps = []
        step_counter = 1
        
        # Step 1: Beginning program (if specified)
        if params.begin_program:
            begin_step = self._create_program_step(
                step_counter, None, params.begin_program, 
                params.target_scale_mmol, resin_mass_g,
                notes="Initial setup program"
            )
            if begin_step:
                steps.append(begin_step)
                step_counter += 1
        
        # Step 2-N: Amino acid addition cycles (C-terminus to N-terminus)
        synthesis_order = peptide.amino_acids[::-1]  # Reverse for SPPS
        
        for aa in synthesis_order:
            # Create AA addition step
            aa_step = self._create_aa_addition_step(
                step_counter, aa.code, params.aa_program,
                params.target_scale_mmol, resin_mass_g
            )
            
            if aa_step:
                steps.append(aa_step)
                step_counter += 1
            
            # Add double coupling for difficult amino acids
            if params.double_couple_difficult and self._is_difficult_coupling(aa.code):
                double_coupling_step = self._create_aa_addition_step(
                    step_counter, aa.code, params.aa_program,
                    params.target_scale_mmol, resin_mass_g,
                    notes=f"Double coupling for difficult AA: {aa.code}"
                )
                
                if double_coupling_step:
                    steps.append(double_coupling_step)
                    step_counter += 1
        
        # Final step: End program (if specified)
        if params.end_program:
            end_step = self._create_program_step(
                step_counter, None, params.end_program,
                params.target_scale_mmol, resin_mass_g,
                notes="Final cleavage/workup program"
            )
            if end_step:
                steps.append(end_step)
                step_counter += 1
        
        # Add steps to schedule
        schedule.steps = steps
        
        # Calculate totals
        schedule.total_estimated_time_minutes = sum(step.estimated_time_minutes for step in steps)
        schedule.total_reagent_consumption = self._sum_reagent_consumption(steps)
        
        self.logger.info(f"Created schedule with {len(steps)} steps, "
                        f"estimated time: {schedule.total_estimated_time_minutes:.1f} minutes")
        
        return schedule
    
    def generate_executable_program(self, step: SynthesisStep) -> Dict[str, Any]:
        """
        Generate an executable program with substituted parameters for a synthesis step.
        
        This is the key function that converts your v_1, v_2, v_3 placeholders 
        into actual calculated volumes.
        """
        # Check if this is an enhanced program
        from ..programs.programs import get_enhanced_program
        enhanced_program = get_enhanced_program(step.program_name)
        
        if enhanced_program:
            # Enhanced program - chemistry is already integrated in CSV
            self.logger.info(f"Using enhanced program {step.program_name} for step {step.step_number}")
            
            # Get the target scale from parameters
            target_mmol = step.parameters.get('resin_mmol', 0.1)
            
            # Compile the program for this scale
            compiled_program = enhanced_program.compile_for_scale(target_mmol)
            if not compiled_program:
                raise ValueError(f"Failed to compile enhanced program: {step.program_name}")
            
            # Add synthesis context
            compiled_program['synthesis_context'] = {
                'amino_acid': step.amino_acid,
                'step_number': step.step_number,
                'synthesis_notes': step.notes
            }
            
            self.logger.info(f"Generated executable enhanced program for step {step.step_number} "
                            f"({step.amino_acid}) with {len(compiled_program.get('steps', []))} steps")
            
            return compiled_program
        
        else:
            # Legacy program - file-based approach
            program_file = self.available_programs.get(step.program_name)
            if not program_file or not program_file.exists():
                raise ValueError(f"Program file not found: {step.program_name}")
            
            # Load the original program
            with open(program_file, 'r', encoding='utf-8') as f:
                program_data = json.load(f)
            
            # Create substitution mapping
            substitutions = {}
            
            # Map your volume placeholders to calculated values
            if 'v_1' in step.parameters:
                substitutions['v_1'] = step.parameters['v_1']
            if 'v_2' in step.parameters:
                substitutions['v_2'] = step.parameters['v_2']  
            if 'v_3' in step.parameters:
                substitutions['v_3'] = step.parameters['v_3']
            
            # Map time placeholders
            if 'coupling_time' in step.parameters:
                substitutions['coupling_time'] = step.parameters['coupling_time']
            
            # Add any other calculated parameters
            for key, value in step.parameters.items():
                if key not in ['amino_acid', 'aa_reagent']:  # Skip metadata
                    substitutions[key] = value
            
            # Substitute parameters in the program
            executable_program = self.parameter_substitution.substitute_program_parameters(
                program_data, substitutions
            )
            
            # Add synthesis context
            executable_program['synthesis_context'] = {
                'amino_acid': step.amino_acid,
                'step_number': step.step_number,
                'synthesis_notes': step.notes
            }
            
            self.logger.info(f"Generated executable program for step {step.step_number} "
                            f"({step.amino_acid}) with {len(substitutions)} substitutions")
            
            return executable_program
    
    def _create_aa_addition_step(self, step_number: int, aa_code: str, program_name: str,
                               target_mmol: float, resin_mass_g: float,
                               notes: Optional[str] = None) -> Optional[SynthesisStep]:
        """Create an amino acid addition step with program-specific chemistry."""
        
        if program_name not in self.available_programs:
            self.logger.warning(f"Program not found: {program_name}")
            return None
        
        # Check if this is an enhanced program
        from ..programs.programs import get_enhanced_program
        enhanced_program = get_enhanced_program(program_name)
        
        if enhanced_program:
            # Enhanced program - chemistry is integrated in CSV
            self.logger.info(f"Using enhanced program {program_name} with integrated chemistry")
            
            # Compile the program for this scale to get volume estimates
            compiled_program = enhanced_program.compile_for_scale(target_mmol)
            if not compiled_program:
                self.logger.error(f"Failed to compile enhanced program: {program_name}")
                return None
            
            # Create parameters for enhanced program
            parameters = {
                'amino_acid': aa_code,
                'resin_mmol': target_mmol,
                'program_type': 'enhanced_csv'
            }
            
            # Get duration from compiled program
            estimated_time = compiled_program.get('estimated_duration_minutes', 180.0)
            
            # Estimate reagent consumption from compiled steps
            reagents_consumed = self._estimate_reagent_consumption_from_steps(
                compiled_program.get('steps', []), aa_code
            )
            
            step_notes = notes or f"Enhanced cycle for {aa_code}"
            
            return SynthesisStep(
                step_number=step_number,
                amino_acid=aa_code,
                program_name=program_name,
                parameters=parameters,
                estimated_time_minutes=estimated_time,
                reagents_consumed=reagents_consumed,
                notes=step_notes
            )
        
        else:
            # Legacy program - use old stoichiometry system
            return self._create_legacy_aa_addition_step(
                step_number, aa_code, program_name, target_mmol, resin_mass_g, notes
            )
    
    def _create_legacy_aa_addition_step(self, step_number: int, aa_code: str, program_name: str,
                                      target_mmol: float, resin_mass_g: float,
                                      notes: Optional[str] = None) -> Optional[SynthesisStep]:
        """Create AA addition step using legacy stoichiometry system."""
        
        if program_name not in self.available_programs:
            self.logger.warning(f"Program not found: {program_name}")
            return None
        
        # Load program-specific stoichiometry
        program_stoich = self._load_program_stoichiometry(program_name)
        if not program_stoich:
            self.logger.error(f"Failed to load stoichiometry for program: {program_name}")
            return None
        
        # Get Fmoc-protected AA reagent name
        aa_reagent = self._get_fmoc_reagent_name(aa_code)
        
        # Calculate volumes using program-specific stoichiometry
        try:
            coupling_volumes = program_stoich.calculate_coupling_volumes(
                target_mmol, aa_reagent
            )
        except Exception as e:
            self.logger.error(f"Failed to calculate volumes for {aa_code}: {e}")
            return None
        
        # Calculate other volumes using program stoichiometry
        deprotection_vol = program_stoich.calculate_deprotection_volume(resin_mass_g, target_mmol)
        wash_vol = program_stoich.calculate_wash_volumes(resin_mass_g, 'DMF', target_mmol)
        
        # Get coupling time from program stoichiometry
        coupling_time = program_stoich.get_coupling_time(aa_code)
        
        # Create parameters with volume substitutions matching your CSV placeholders
        parameters = {
            'amino_acid': aa_code,
            'aa_reagent': aa_reagent,
            'v_1': deprotection_vol,         # Maps to v_1 in your CSV
            'v_2': coupling_volumes.get('coupling_volume', 0),   # Maps to v_2 in your CSV  
            'v_3': wash_vol,                 # Maps to v_3 in your CSV
            'coupling_time': coupling_time,  # Maps to coupling_time in your CSV
        }
        
        # Estimate time from program
        estimated_time = self._estimate_program_time(program_name)
        
        # Track reagent consumption
        reagents_consumed = {
            aa_reagent: coupling_volumes.get('coupling_volume', 0),
            'Deprotection': deprotection_vol,
            'DMF': wash_vol * 7,  # Multiple washes in your program
        }
        
        step_notes = notes or f"Couple {aa_code} ({aa_reagent})"
        
        return SynthesisStep(
            step_number=step_number,
            amino_acid=aa_code,
            program_name=program_name,
            parameters=parameters,
            estimated_time_minutes=estimated_time,
            reagents_consumed=reagents_consumed,
            notes=step_notes
        )
    
    def _create_program_step(self, step_number: int, aa_code: Optional[str], program_name: str,
                           target_mmol: float, resin_mass_g: float,
                           notes: Optional[str] = None) -> Optional[SynthesisStep]:
        """Create a generic program step (begin/end programs)."""
        
        if program_name not in self.available_programs:
            self.logger.warning(f"Program not found: {program_name}")
            return None
        
        # Basic parameters for non-AA programs
        parameters = {
            'target_mmol': target_mmol,
            'resin_mass_g': resin_mass_g
        }
        
        estimated_time = self._estimate_program_time(program_name)
        
        return SynthesisStep(
            step_number=step_number,
            amino_acid=aa_code,
            program_name=program_name,
            parameters=parameters,
            estimated_time_minutes=estimated_time,
            reagents_consumed={},
            notes=notes
        )
    
    def _get_fmoc_reagent_name(self, aa_code: str) -> str:
        """Get Fmoc-protected reagent name for amino acid."""
        # Standard side-chain protections
        protections = {
            'K': 'Fmoc-K(Boc)',
            'R': 'Fmoc-R(Pbf)', 
            'H': 'Fmoc-H(Trt)',
            'S': 'Fmoc-S(tBu)',
            'T': 'Fmoc-T(tBu)',
            'Y': 'Fmoc-Y(tBu)',
            'D': 'Fmoc-D(OtBu)',
            'E': 'Fmoc-E(OtBu)',
            'N': 'Fmoc-N(Trt)',
            'Q': 'Fmoc-Q(Trt)',
            'C': 'Fmoc-C(Trt)',
            'W': 'Fmoc-W(Boc)'
        }
        
        return protections.get(aa_code, f'Fmoc-{aa_code}')
    
    def _is_difficult_coupling(self, aa_code: str) -> bool:
        """Check if amino acid requires special coupling conditions."""
        difficult_aas = {'P', 'G', 'I', 'V'}  # Pro, Gly, Ile, Val
        return aa_code in difficult_aas
    
    def _estimate_program_time(self, program_name: str) -> float:
        """Estimate execution time for a program."""
        program_file = self.available_programs.get(program_name)
        if program_file and program_file.exists():
            try:
                with open(program_file, 'r', encoding='utf-8') as f:
                    program_data = json.load(f)
                
                return program_data.get('estimated_duration_minutes', 180.0)
                
            except Exception as e:
                self.logger.warning(f"Could not load program {program_name}: {e}")
        
        # Default estimate for AA addition
        return 180.0  # 3 hours
    
    def _sum_reagent_consumption(self, steps: List[SynthesisStep]) -> Dict[str, float]:
        """Sum total reagent consumption across all steps."""
        total_consumption = {}
        
        for step in steps:
            for reagent, amount in step.reagents_consumed.items():
                total_consumption[reagent] = total_consumption.get(reagent, 0) + amount
        
        return total_consumption
    
    def _load_program_stoichiometry(self, program_name: str) -> Optional[object]:
        """
        DEPRECATED: Enhanced CSV programs now handle their own chemistry.
        This method is kept for backwards compatibility with legacy programs.
        """
        # Check if this is an enhanced program first
        from ..programs.programs import get_enhanced_program
        enhanced_program = get_enhanced_program(program_name)
        if enhanced_program:
            self.logger.info(f"Using enhanced program {program_name} - chemistry integrated")
            return None  # Enhanced programs don't need separate stoichiometry
        
        # Fallback to legacy stoichiometry system
        try:
            # Map program names to stoichiometry files
            program_stoich_map = {
                'aa_oxyma_dic_v1': 'oxyma_dic.yaml',
                'aa_hbtu_dipea_v1': 'hbtu_dipea.yaml',
                'testing_cycle': 'testing.yaml',
                # Add more mappings as needed
            }
            
            stoich_file = program_stoich_map.get(program_name)
            if not stoich_file:
                # Try to infer from program name
                if 'oxyma' in program_name.lower():
                    stoich_file = 'oxyma_dic.yaml'
                elif 'hbtu' in program_name.lower():
                    stoich_file = 'hbtu_dipea.yaml'
                else:
                    self.logger.warning(f"No stoichiometry mapping for program: {program_name}")
                    return None
            
            stoich_path = self.programs_dir / "stoichiometry" / stoich_file
            if not stoich_path.exists():
                self.logger.error(f"Stoichiometry file not found: {stoich_path}")
                return None
            
            from .stoichiometry_deprecated import load_stoichiometry_file
            return load_stoichiometry_file(stoich_path)
            
        except Exception as e:
            self.logger.error(f"Failed to load stoichiometry for {program_name}: {e}")
            return None
    
    def _generate_synthesis_id(self, peptide: PeptideSequence) -> str:
        """Generate unique synthesis ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sequence_short = ''.join(aa.code for aa in peptide.amino_acids)
        if len(sequence_short) > 10:
            sequence_short = sequence_short[:10] + "..."
        
        return f"SYNTH_{sequence_short}_{timestamp}"
    
    def _estimate_reagent_consumption_from_steps(self, steps: List[Dict[str, Any]], 
                                                aa_code: str) -> Dict[str, float]:
        """Estimate reagent consumption from compiled program steps."""
        reagents_consumed = {}
        
        for step in steps:
            # Look for volume calculations
            if 'volume_calculation' in step:
                volume_calc = step['volume_calculation']
                calculated_volume = volume_calc.get('calculated_volume_ml', 0)
                
                # Try to identify reagent type from step
                params = step.get('params', {})
                source_port = params.get('source_port', '')
                comments = step.get('comments', '')
                
                # Map ports to reagent names (based on your CSV comments)
                port_reagent_map = {
                    'R1': f'Fmoc-{aa_code}',
                    'R2': 'Activator',  
                    'R3': 'Deprotection',
                    'R4': 'DMF',
                    'R5': 'Reactor',
                    'R6': 'Waste'
                }
                
                reagent_name = port_reagent_map.get(source_port, f'Port_{source_port}')
                if calculated_volume > 0:
                    reagents_consumed[reagent_name] = reagents_consumed.get(reagent_name, 0) + calculated_volume
        
        return reagents_consumed
    
    def save_schedule(self, schedule: SynthesisSchedule, output_path: Path):
        """Save synthesis schedule to JSON file."""
        # Convert dataclass to dictionary
        schedule_dict = {
            'synthesis_id': schedule.synthesis_id,
            'peptide_sequence': schedule.peptide_sequence,
            'target_scale_mmol': schedule.target_scale_mmol,
            'resin_mass_g': schedule.resin_mass_g,
            'total_estimated_time_minutes': schedule.total_estimated_time_minutes,
            'total_reagent_consumption': schedule.total_reagent_consumption,
            'created_at': schedule.created_at,
            'created_by': schedule.created_by,
            'steps': []
        }
        
        # Convert steps
        for step in schedule.steps:
            step_dict = {
                'step_number': step.step_number,
                'amino_acid': step.amino_acid,
                'program_name': step.program_name,
                'parameters': step.parameters,
                'estimated_time_minutes': step.estimated_time_minutes,
                'reagents_consumed': step.reagents_consumed,
                'notes': step.notes
            }
            schedule_dict['steps'].append(step_dict)
        
        # Write JSON file atomically (Windows-safe replace)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = output_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(schedule_dict, f, indent=2, sort_keys=False)
        temp_path.replace(output_path)
        
        self.logger.info(f"Saved synthesis schedule to {output_path}")


def create_synthesis_schedule(peptide_sequence: str, scale_mmol: float, 
                            stoichiometry_file: Optional[Path] = None,
                            programs_dir: Optional[Path] = None) -> SynthesisSchedule:
    """Convenience function to create a synthesis schedule."""
    
    if not programs_dir:
        programs_dir = Path(__file__).parent.parent / "programs"
    
    # Load stoichiometry calculator
    if stoichiometry_file and stoichiometry_file.exists():
        from .stoichiometry_deprecated import load_stoichiometry_file
        stoich_calc = load_stoichiometry_file(stoichiometry_file)
    else:
        from .stoichiometry_deprecated import StoichiometryCalculator
        stoich_calc = StoichiometryCalculator()
    
    # Create coordinator
    coordinator = SynthesisCoordinator(programs_dir)
    
    params = SynthesisParameters(
        peptide_sequence=peptide_sequence,
        target_scale_mmol=scale_mmol
    )
    
    return coordinator.create_synthesis_schedule(params)
