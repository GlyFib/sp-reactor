import re
import logging
import yaml
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AminoAcid:
    """Represents a single amino acid in a peptide sequence."""
    position: int
    code: str
    three_letter: str
    full_name: str
    reagent: str
    n_terminal: bool = False
    c_terminal: bool = False
    modification: Optional[str] = None
    is_building_block: bool = False
    cas_number: Optional[str] = None
    molecular_weight: Optional[float] = None


@dataclass 
class PeptideSequence:
    """Represents a complete peptide sequence with modifications."""
    sequence: str
    amino_acids: List[AminoAcid]
    n_terminal_mod: Optional[str] = None
    c_terminal_mod: Optional[str] = None
    length: int = 0
    
    def __post_init__(self):
        self.length = len(self.amino_acids)


class PeptideSequenceParser:
    """Parses peptide sequences in various formats."""
    
    def __init__(self, config_path: Optional[str] = None):
        self.logger = logging.getLogger("peptide_sequence_parser")
        
        # Load configuration
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "data" / "amino_acids_config.yml"
        
        self.config = self._load_config(config_path)
        
        # Standard amino acid mapping (backwards compatibility)
        self.aa_mapping = {}
        for code, data in self.config.get('canonical_amino_acids', {}).items():
            self.aa_mapping[code] = (data['three_letter'], data['full_name'])
    
    def _load_config(self, config_path: Path) -> Dict[str, Any]:
        """Load amino acid configuration from YAML file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return self._get_default_config()
        except Exception as e:
            self.logger.error(f"Error loading config: {e}. Using defaults.")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Fallback default configuration."""
        return {
            'canonical_amino_acids': {
                'A': {'three_letter': 'Ala', 'full_name': 'Alanine', 'default_reagent': 'Fmoc-A'},
                'R': {'three_letter': 'Arg', 'full_name': 'Arginine', 'default_reagent': 'Fmoc-R(Pbf)'},
                'N': {'three_letter': 'Asn', 'full_name': 'Asparagine', 'default_reagent': 'Fmoc-N(Trt)'},
                'D': {'three_letter': 'Asp', 'full_name': 'Aspartic acid', 'default_reagent': 'Fmoc-D(OtBu)'},
                'C': {'three_letter': 'Cys', 'full_name': 'Cysteine', 'default_reagent': 'Fmoc-C(Trt)'},
                'E': {'three_letter': 'Glu', 'full_name': 'Glutamic acid', 'default_reagent': 'Fmoc-E(OtBu)'},
                'Q': {'three_letter': 'Gln', 'full_name': 'Glutamine', 'default_reagent': 'Fmoc-Q(Trt)'},
                'G': {'three_letter': 'Gly', 'full_name': 'Glycine', 'default_reagent': 'Fmoc-G'},
                'H': {'three_letter': 'His', 'full_name': 'Histidine', 'default_reagent': 'Fmoc-H(Trt)'},
                'I': {'three_letter': 'Ile', 'full_name': 'Isoleucine', 'default_reagent': 'Fmoc-I'},
                'L': {'three_letter': 'Leu', 'full_name': 'Leucine', 'default_reagent': 'Fmoc-L'},
                'K': {'three_letter': 'Lys', 'full_name': 'Lysine', 'default_reagent': 'Fmoc-K(Boc)'},
                'M': {'three_letter': 'Met', 'full_name': 'Methionine', 'default_reagent': 'Fmoc-M'},
                'F': {'three_letter': 'Phe', 'full_name': 'Phenylalanine', 'default_reagent': 'Fmoc-F'},
                'P': {'three_letter': 'Pro', 'full_name': 'Proline', 'default_reagent': 'Fmoc-P'},
                'S': {'three_letter': 'Ser', 'full_name': 'Serine', 'default_reagent': 'Fmoc-S(tBu)'},
                'T': {'three_letter': 'Thr', 'full_name': 'Threonine', 'default_reagent': 'Fmoc-T(tBu)'},
                'W': {'three_letter': 'Trp', 'full_name': 'Tryptophan', 'default_reagent': 'Fmoc-W(Boc)'},
                'Y': {'three_letter': 'Tyr', 'full_name': 'Tyrosine', 'default_reagent': 'Fmoc-Y(tBu)'},
                'V': {'three_letter': 'Val', 'full_name': 'Valine', 'default_reagent': 'Fmoc-V'}
            },
            'custom_protections': {},
            'building_blocks': {}
        }
    
    def parse(self, sequence: str) -> PeptideSequence:
        """
        Parse peptide sequence in various formats:
        - FMRF-NH2 (C-terminal amide)
        - Ac-YGGFL-NH2 (N-terminal acetyl, C-terminal amide)
        - H-DRVYIHPF-OH (Free amino and carboxyl)
        - PEPTIDE (no modifications)
        """
        if not sequence or not isinstance(sequence, str):
            raise ValueError("Invalid peptide sequence")
        
        sequence = sequence.strip().upper()
        self.logger.info(f"Parsing peptide sequence: {sequence}")
        
        # Parse N-terminal modification
        n_terminal_mod = None
        if sequence.startswith('AC-'):
            n_terminal_mod = 'Acetyl'
            sequence = sequence[3:]
        elif sequence.startswith('H-'):
            n_terminal_mod = 'Free'  # Free N-terminus
            sequence = sequence[2:]
        elif '-' in sequence and not sequence.endswith('-NH2') and not sequence.endswith('-OH'):
            # Look for other N-terminal modifications
            parts = sequence.split('-', 1)
            if len(parts[0]) <= 4:  # Likely a modification
                n_terminal_mod = parts[0]
                sequence = parts[1]
        
        # Parse C-terminal modification  
        c_terminal_mod = None
        if sequence.endswith('-NH2'):
            c_terminal_mod = 'Amide'
            sequence = sequence[:-4]
        elif sequence.endswith('-OH'):
            c_terminal_mod = 'Free'  # Free C-terminus
            sequence = sequence[:-3]
        elif '-' in sequence:
            # Look for other C-terminal modifications
            parts = sequence.rsplit('-', 1)
            if len(parts[1]) <= 4:  # Likely a modification
                c_terminal_mod = parts[1]
                sequence = parts[0]
        
        # Parse core amino acid sequence
        amino_acids = self._parse_core_sequence(sequence)
        
        # Mark terminal positions
        if amino_acids:
            amino_acids[0].n_terminal = True
            amino_acids[-1].c_terminal = True
        
        return PeptideSequence(
            sequence=sequence,
            amino_acids=amino_acids,
            n_terminal_mod=n_terminal_mod,
            c_terminal_mod=c_terminal_mod
        )
    
    def _parse_core_sequence(self, sequence: str) -> List[AminoAcid]:
        """Parse the core amino acid sequence with support for custom protections and building blocks."""
        amino_acids = []
        position = 1
        i = 0
        
        while i < len(sequence):
            # Check for building blocks [NAME]
            if sequence[i] == '[':
                end_bracket = sequence.find(']', i)
                if end_bracket == -1:
                    raise ValueError(f"Unclosed bracket at position {i}")
                
                building_block = sequence[i:end_bracket + 1]
                aa_info = self._parse_building_block(building_block, position)
                amino_acids.append(aa_info)
                position += 1
                i = end_bracket + 1
                continue
            
            # Check for custom protected amino acids (e.g., K*, K**)
            if i + 1 < len(sequence) and sequence[i + 1] == '*':
                # Count consecutive asterisks
                asterisk_count = 0
                j = i + 1
                while j < len(sequence) and sequence[j] == '*':
                    asterisk_count += 1
                    j += 1
                
                custom_code = sequence[i] + ('*' * asterisk_count)
                aa_info = self._parse_custom_protection(custom_code, position)
                amino_acids.append(aa_info)
                position += 1
                i = j
                continue
            
            # Regular single letter amino acid
            code = sequence[i]
            if code in self.aa_mapping:
                aa_info = self._parse_canonical_amino_acid(code, position)
                amino_acids.append(aa_info)
                position += 1
                i += 1
            else:
                raise ValueError(f"Unknown amino acid code: {code} at position {i}")
        
        return amino_acids
    
    def _parse_canonical_amino_acid(self, code: str, position: int) -> AminoAcid:
        """Parse a canonical amino acid."""
        config_data = self.config['canonical_amino_acids'][code]
        return AminoAcid(
            position=position,
            code=code,
            three_letter=config_data['three_letter'],
            full_name=config_data['full_name'],
            reagent=config_data['default_reagent']
        )
    
    def _parse_custom_protection(self, custom_code: str, position: int) -> AminoAcid:
        """Parse a custom protected amino acid (e.g., K*, K**)."""
        custom_protections = self.config.get('custom_protections', {})
        
        if custom_code not in custom_protections:
            raise ValueError(f"Unknown custom protection: {custom_code}")
        
        protection_data = custom_protections[custom_code]
        base_code = protection_data['base_amino_acid']
        canonical_data = self.config['canonical_amino_acids'][base_code]
        
        return AminoAcid(
            position=position,
            code=custom_code,
            three_letter=f"{canonical_data['three_letter']}({protection_data['protection_name']})",
            full_name=protection_data['description'],
            reagent=protection_data['reagent'],
            modification=protection_data['protection_name']
        )
    
    def _parse_building_block(self, block_name: str, position: int) -> AminoAcid:
        """Parse a building block [NAME]."""
        building_blocks = self.config.get('building_blocks', {})
        
        # Try exact match first
        if block_name in building_blocks:
            block_data = building_blocks[block_name]
        else:
            # Try case-insensitive match
            block_name_upper = block_name.upper()
            matched_key = None
            for key in building_blocks:
                if key.upper() == block_name_upper:
                    matched_key = key
                    break
            
            if matched_key:
                block_data = building_blocks[matched_key]
                block_name = matched_key  # Use the correct case
            else:
                raise ValueError(f"Unknown building block: {block_name}")
        
        return AminoAcid(
            position=position,
            code=block_name,
            three_letter=block_name.strip('[]'),
            full_name=block_data['full_name'],
            reagent=block_data['reagent'],
            is_building_block=True,
            cas_number=block_data.get('cas_number'),
            molecular_weight=block_data.get('molecular_weight')
        )
    
    def to_fmoc_reagents(self, peptide: PeptideSequence) -> List[str]:
        """Convert peptide sequence to list of reagents needed."""
        reagents = []
        
        for aa in peptide.amino_acids:
            reagents.append(aa.reagent)
        
        return reagents
    
    def get_synthesis_order(self, peptide: PeptideSequence) -> List[AminoAcid]:
        """
        Get amino acids in synthesis order (C-terminus to N-terminus).
        In SPPS, synthesis proceeds from C-terminal to N-terminal.
        """
        return list(reversed(peptide.amino_acids))


class SequenceValidator:
    """Validates peptide sequences for synthesis compatibility."""
    
    def __init__(self):
        self.logger = logging.getLogger("sequence_validator")
        
        # Load synthesis notes from config if available
        config_path = Path(__file__).parent.parent.parent / "data" / "amino_acids_config.yml"
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                synthesis_notes = config.get('synthesis_notes', {})
                self.difficult_sequences = synthesis_notes.get('difficult_sequences', {
                    'PP': 'Proline-Proline dipeptide - difficult coupling',
                    'GP': 'Glycine-Proline - potential aggregation', 
                    'PG': 'Proline-Glycine - potential aggregation'
                })
                self.difficult_amino_acids = synthesis_notes.get('sensitive_residues', {
                    'P': 'Proline - secondary amine, difficult coupling',
                    'C': 'Cysteine - oxidation sensitive',
                    'M': 'Methionine - oxidation sensitive',
                    'W': 'Tryptophan - UV sensitive, can racemize'
                })
        except:
            # Fallback to defaults
            self.difficult_sequences = {
                'PP': 'Proline-Proline dipeptide - difficult coupling',
                'GP': 'Glycine-Proline - potential aggregation', 
                'PG': 'Proline-Glycine - potential aggregation'
            }
            self.difficult_amino_acids = {
                'P': 'Proline - secondary amine, difficult coupling',
                'C': 'Cysteine - oxidation sensitive',
                'M': 'Methionine - oxidation sensitive',
                'W': 'Tryptophan - UV sensitive, can racemize'
            }
    
    def validate(self, peptide: PeptideSequence) -> Tuple[bool, List[str]]:
        """
        Validate peptide sequence for synthesis.
        Returns (is_valid, list_of_warnings)
        """
        warnings = []
        
        # Check sequence length
        if peptide.length > 50:
            warnings.append(f"Long peptide ({peptide.length} residues) - synthesis may be challenging")
        elif peptide.length < 2:
            warnings.append("Very short peptide - consider direct synthesis")
        
        # Check for difficult amino acids
        for aa in peptide.amino_acids:
            # Check single letter codes for canonical amino acids
            base_code = aa.code.rstrip('*') if '*' in aa.code else aa.code
            if base_code in self.difficult_amino_acids:
                warnings.append(f"Position {aa.position} ({aa.code}): {self.difficult_amino_acids[base_code]}")
            
            # Special warnings for building blocks
            if aa.is_building_block:
                warnings.append(f"Position {aa.position}: Non-canonical building block {aa.code} - verify compatibility")
        
        # Check for difficult sequences (only for canonical amino acids)
        canonical_sequence = ''.join(
            aa.code.rstrip('*') if '*' in aa.code else aa.code 
            for aa in peptide.amino_acids 
            if not aa.is_building_block
        )
        for difficult_seq, reason in self.difficult_sequences.items():
            if difficult_seq in canonical_sequence:
                pos = canonical_sequence.find(difficult_seq)
                warnings.append(f"Difficult sequence ({difficult_seq}): {reason}")
        
        # Check for repetitive sequences
        if len(set(aa.code for aa in peptide.amino_acids)) <= 2:
            warnings.append("Highly repetitive sequence - may cause aggregation")
        
        # Check terminal modifications
        if peptide.n_terminal_mod and peptide.n_terminal_mod not in ['Acetyl', 'Free']:
            warnings.append(f"Unusual N-terminal modification: {peptide.n_terminal_mod}")
        
        if peptide.c_terminal_mod and peptide.c_terminal_mod not in ['Amide', 'Free']:
            warnings.append(f"Unusual C-terminal modification: {peptide.c_terminal_mod}")
        
        # Sequence is valid if no critical errors (warnings are OK)
        is_valid = True  # We don't reject sequences, just warn
        
        return is_valid, warnings


def parse_peptide_file(file_path: Path) -> List[PeptideSequence]:
    """
    Parse a file containing peptide sequences.
    Supports formats:
    - One sequence per line
    - CSV with headers
    - Comments starting with #
    """
    parser = PeptideSequenceParser()
    sequences = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith('#'):
            continue
        
        # Handle CSV format (assume sequence in first column)
        if ',' in line and not line_num == 1:  # Skip header if CSV
            sequence_str = line.split(',')[0].strip()
        else:
            sequence_str = line
        
        try:
            peptide = parser.parse(sequence_str)
            sequences.append(peptide)
        except Exception as e:
            logging.warning(f"Could not parse line {line_num}: '{line}' - {e}")
    
    return sequences


# Convenience functions for testing
def parse_sequence(sequence: str, config_path: Optional[str] = None) -> PeptideSequence:
    """Parse a single peptide sequence."""
    parser = PeptideSequenceParser(config_path)
    return parser.parse(sequence)


def validate_sequence(sequence: str) -> Tuple[bool, List[str]]:
    """Parse and validate a peptide sequence."""
    peptide = parse_sequence(sequence)
    validator = SequenceValidator()
    return validator.validate(peptide)