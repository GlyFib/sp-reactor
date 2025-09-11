#!/usr/bin/env python3
"""
Test script for the enhanced sequence parser.
Demonstrates support for custom protecting groups and building blocks.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from synthesis.sequence_parser import parse_sequence, PeptideSequenceParser

def test_enhanced_parser():
    """Test the enhanced sequence parser with various sequence formats."""
    
    # Test sequences with different features
    test_sequences = [
        # Standard sequences
        "PEPTIDE",
        "Ac-YGGFL-NH2",
        
        # Custom protecting groups
        "PEK*TIDE",  # K with TFA protection
        "PEK**TIDE", # K with Mtt protection
        "E*PTIDE",   # E with All protection
        "C*YSTEINE", # C with Asm protection
        
        # Building blocks
        "[AEEA]PEPTIDE",
        "PEPTIDE[Fmoc-AEEA]",
        "[5-FAM]PEPTIDE[TAMRA]",
        
        # Complex sequences
        "Ac-FK*[AEEA]GE*L-NH2",  # Mixed custom protections and building blocks
        "[Biotin]GGK**PEPTIDE[5-FAM]",  # Multiple building blocks
        
        # Edge cases
        "K*K**K",  # Multiple custom protections
        "[PEG4]",  # Single building block
    ]
    
    parser = PeptideSequenceParser()
    
    print("Enhanced Sequence Parser Test")
    print("=" * 50)
    
    for i, sequence in enumerate(test_sequences, 1):
        print(f"\nTest {i}: {sequence}")
        print("-" * 30)
        
        try:
            peptide = parse_sequence(sequence)
            
            print(f"Parsed sequence: {peptide.sequence}")
            print(f"Length: {peptide.length}")
            print(f"N-terminal: {peptide.n_terminal_mod}")
            print(f"C-terminal: {peptide.c_terminal_mod}")
            
            print("Amino acids:")
            for aa in peptide.amino_acids:
                protection_info = f" ({aa.modification})" if aa.modification else ""
                building_block_info = " [Building Block]" if aa.is_building_block else ""
                cas_info = f" (CAS: {aa.cas_number})" if aa.cas_number else ""
                
                print(f"  {aa.position}: {aa.code} -> {aa.reagent}{protection_info}{building_block_info}{cas_info}")
            
            print("Reagents needed:")
            reagents = parser.to_fmoc_reagents(peptide)
            for j, reagent in enumerate(reagents, 1):
                print(f"  {j}. {reagent}")
                
        except Exception as e:
            print(f"ERROR: {e}")
        
        print()

def test_config_features():
    """Test configuration-based features."""
    print("Configuration Features Test")
    print("=" * 50)
    
    parser = PeptideSequenceParser()
    
    # Test configuration loading
    print("Loaded configuration:")
    print(f"- Canonical amino acids: {len(parser.config.get('canonical_amino_acids', {}))}")
    print(f"- Custom protections: {len(parser.config.get('custom_protections', {}))}")
    print(f"- Building blocks: {len(parser.config.get('building_blocks', {}))}")
    
    # Test adding new custom protections
    print("\nAvailable custom protections:")
    for code, data in parser.config.get('custom_protections', {}).items():
        print(f"  {code}: {data['reagent']} - {data['description']}")
    
    print("\nAvailable building blocks:")
    for block, data in parser.config.get('building_blocks', {}).items():
        print(f"  {block}: {data['reagent']} - {data['description']}")

def main():
    """Run all tests."""
    test_enhanced_parser()
    print("\n" + "=" * 70 + "\n")
    test_config_features()

if __name__ == "__main__":
    main()