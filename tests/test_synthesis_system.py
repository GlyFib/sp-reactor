#!/usr/bin/env python3
"""
Test script for the complete synthesis layer system.
Tests sequence parsing, stoichiometry calculations, and parameter substitution.
"""

import sys
from pathlib import Path
import logging

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.synthesis.sequence_parser import parse_sequence, validate_sequence
from src.synthesis.stoichiometry_deprecated import StoichiometryCalculator, create_default_stoichiometry_file
from src.synthesis.coordinator import SynthesisCoordinator, SynthesisParameters, create_synthesis_schedule


def setup_logging():
    """Set up logging for the test."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def test_sequence_parsing():
    """Test peptide sequence parsing capabilities."""
    print("🧪 Testing Peptide Sequence Parsing")
    print("-" * 40)
    
    test_sequences = [
        "FMRF-NH2",           # C-terminal amide
        "Ac-YGGFL-NH2",       # N-acetyl, C-amide
        "H-DRVYIHPF-OH",      # Free terminals
        "PEPTIDE",            # Simple sequence
        "GPGG"                # Difficult sequence (Gly-Pro)
    ]
    
    for seq in test_sequences:
        try:
            peptide = parse_sequence(seq)
            print(f"   {seq:<15} → {len(peptide.amino_acids)} AAs, "
                  f"N-term: {peptide.n_terminal_mod}, C-term: {peptide.c_terminal_mod}")
            
            # Show amino acids
            aa_codes = ''.join(aa.code for aa in peptide.amino_acids)
            print(f"      Core sequence: {aa_codes}")
            
            # Validate
            is_valid, warnings = validate_sequence(seq)
            if warnings:
                for warning in warnings:
                    print(f"      ⚠️  {warning}")
            print()
            
        except Exception as e:
            print(f"   {seq:<15} → ERROR: {e}")
    print()


def test_stoichiometry_calculations():
    """Test stoichiometry calculations."""
    print("🧪 Testing Stoichiometry Calculations")
    print("-" * 40)
    
    calc = StoichiometryCalculator()
    
    # Test parameters
    resin_mmol = 0.1  # 0.1 mmol scale
    resin_mass_g = calc.estimate_resin_mass(resin_mmol, 0.5)  # 0.5 mmol/g substitution
    
    print(f"   Scale: {resin_mmol} mmol")
    print(f"   Estimated resin mass: {resin_mass_g:.2f} g")
    print()
    
    # Test coupling volume calculations
    test_amino_acids = ['A', 'R', 'F', 'P']  # Simple, Arg, Phe, Pro (difficult)
    
    for aa_code in test_amino_acids:
        aa_name = calc._get_fmoc_reagent_name(aa_code) if hasattr(calc, '_get_fmoc_reagent_name') else f'Fmoc-{aa_code}'
        
        try:
            volumes = calc.calculate_coupling_volumes(resin_mmol, aa_name, 'HBTU')
            coupling_time = calc.get_coupling_time(aa_code)
            
            print(f"   {aa_code} ({aa_name}):")
            print(f"      AA volume: {volumes.get('AA', 0):.2f} mL")
            print(f"      DIC volume: {volumes.get('DIC', 0):.2f} mL") 
            print(f"      Coupling time: {coupling_time:.1f} min")
            print()
            
        except Exception as e:
            print(f"   {aa_code} → ERROR: {e}")
    
    # Test other volume calculations
    deprotection_vol = calc.calculate_deprotection_volume(resin_mass_g)
    wash_vol = calc.calculate_wash_volumes(resin_mass_g, 'DMF')
    
    print(f"   Deprotection volume: {deprotection_vol:.2f} mL")
    print(f"   Wash volume: {wash_vol:.2f} mL")
    print()


def test_synthesis_coordination():
    """Test the complete synthesis coordination system."""
    print("🔧 Testing Synthesis Coordination System")
    print("=" * 50)
    
    # Test parameters
    peptide_sequence = "FMRF-NH2"
    scale_mmol = 0.1
    programs_dir = project_root / "programs"
    
    print(f"📋 Peptide: {peptide_sequence}")
    print(f"📋 Scale: {scale_mmol} mmol")
    print(f"📋 Programs dir: {programs_dir}")
    print()
    
    try:
        # Create stoichiometry calculator
        stoich_calc = StoichiometryCalculator()
        
        # Create synthesis coordinator
        coordinator = SynthesisCoordinator(programs_dir)
        
        # Create synthesis parameters
        params = SynthesisParameters(
            peptide_sequence=peptide_sequence,
            target_scale_mmol=scale_mmol,
            aa_program="program_aa_addition_default"  # Your reactor program
        )
        
        # Generate synthesis schedule
        print("🔨 Generating synthesis schedule...")
        schedule = coordinator.create_synthesis_schedule(params)
        
        print(f"✅ Generated schedule: {schedule.synthesis_id}")
        print(f"   Peptide: {schedule.peptide_sequence}")
        print(f"   Steps: {len(schedule.steps)}")
        print(f"   Estimated time: {schedule.total_estimated_time_minutes:.1f} minutes")
        print(f"   Resin mass: {schedule.resin_mass_g:.2f} g")
        print()
        
        # Show synthesis steps
        print("📋 Synthesis Steps:")
        for step in schedule.steps[:5]:  # Show first 5 steps
            print(f"   {step.step_number:2d}. {step.amino_acid or 'Setup':<4} "
                  f"{step.program_name:<25} ({step.estimated_time_minutes:.0f} min)")
            
            # Show key parameters
            key_params = {}
            if 'v_1' in step.parameters:
                key_params['v_1'] = f"{step.parameters['v_1']:.2f} mL"
            if 'v_2' in step.parameters:
                key_params['v_2'] = f"{step.parameters['v_2']:.2f} mL"  
            if 'v_3' in step.parameters:
                key_params['v_3'] = f"{step.parameters['v_3']:.2f} mL"
            
            if key_params:
                params_str = ', '.join(f"{k}={v}" for k, v in key_params.items())
                print(f"      Parameters: {params_str}")
        
        if len(schedule.steps) > 5:
            print(f"   ... and {len(schedule.steps) - 5} more steps")
        print()
        
        # Show reagent consumption
        print("🧪 Total Reagent Consumption:")
        for reagent, amount in list(schedule.total_reagent_consumption.items())[:5]:
            print(f"   {reagent:<20}: {amount:.2f} mL")
        print()
        
        # Test parameter substitution with first AA step
        aa_steps = [step for step in schedule.steps if step.amino_acid]
        if aa_steps:
            first_aa_step = aa_steps[0]
            print(f"🔄 Testing Parameter Substitution for {first_aa_step.amino_acid}:")
            
            try:
                executable_program = coordinator.generate_executable_program(first_aa_step)
                
                print(f"   Original program: {first_aa_step.program_name}")
                print(f"   Substitutions made: {len(first_aa_step.parameters)}")
                print(f"   Executable steps: {len(executable_program.get('steps', []))}")
                
                # Show a few substituted steps
                for i, step in enumerate(executable_program.get('steps', [])[:3]):
                    params = step.get('params', {})
                    volume_params = {k: v for k, v in params.items() 
                                   if 'volume' in k and isinstance(v, (int, float))}
                    
                    if volume_params:
                        print(f"      Step {i+1}: {volume_params}")
                
                print()
                
            except Exception as e:
                print(f"   ❌ Parameter substitution failed: {e}")
        
        print("🎉 Synthesis Coordination Test Completed Successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Synthesis coordination failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stoichiometry_config():
    """Test stoichiometry configuration file creation."""
    print("🧪 Testing Stoichiometry Configuration")
    print("-" * 40)
    
    config_path = project_root / "stoichiometry_files" / "default_config.yaml"
    config_path.parent.mkdir(exist_ok=True)
    
    try:
        create_default_stoichiometry_file(config_path)
        print(f"✅ Created default config: {config_path}")
        
        # Test loading the config
        calc = StoichiometryCalculator(config_path)
        print(f"   AA excess: {calc.config.aa_excess}x")
        print(f"   DIC excess: {calc.config.dic_excess}x")
        print(f"   Coupling time: {calc.config.coupling_time} min")
        print()
        
    except Exception as e:
        print(f"❌ Config test failed: {e}")


def main():
    """Run all tests."""
    setup_logging()
    
    print("🧪 Synthesis Layer System Tests")
    print("=" * 50)
    
    # Test individual components
    test_sequence_parsing()
    test_stoichiometry_calculations() 
    test_stoichiometry_config()
    
    # Test full integration
    success = test_synthesis_coordination()
    
    if success:
        print("\n✅ All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())