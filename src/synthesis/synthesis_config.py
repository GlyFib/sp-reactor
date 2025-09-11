"""
Synthesis configuration parser and data classes.
Handles chemistry-agnostic synthesis parameters.
"""

import yaml
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional


@dataclass
class SynthesisScale:
    """Synthesis scale parameters."""
    target_mmol: float
    loading_mmol_g: float = 0.5  # Default resin substitution


@dataclass
class SynthesisConfig:
    """Complete synthesis configuration."""
    sequence: str
    scale: SynthesisScale
    default_aa_program: str
    start_program: Optional[str] = None
    end_program: Optional[str] = None
    per_aa_overrides: Dict[int, str] = None
    
    # Synthesis options
    double_couple_difficult: bool = True
    perform_capping: bool = True
    monitor_coupling: bool = False
    save_sample_each_cycle: bool = False
    
    def __post_init__(self):
        if self.per_aa_overrides is None:
            self.per_aa_overrides = {}


def load_synthesis_config(config_path: Path) -> SynthesisConfig:
    """Load synthesis configuration from YAML file."""
    with open(config_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    # Parse scale - handle both nested 'scale' object and direct fields
    if 'scale' in data and isinstance(data['scale'], dict):
        scale_data = data['scale']
    else:
        # Handle direct scale fields
        scale_data = {
            'target_mmol': data.get('target_scale_mmol', 0.1),
            'loading_mmol_g': data.get('resin_substitution_mmol_g', 0.5)
        }
    
    scale = SynthesisScale(
        target_mmol=scale_data.get('target_mmol', 0.1),
        loading_mmol_g=scale_data.get('loading_mmol_g', 0.5)
    )
    
    # Create config
    config = SynthesisConfig(
        sequence=data.get('sequence') or data.get('peptide_sequence', ''),
        scale=scale,
        default_aa_program=data.get('default_aa_program') or data.get('aa_program', 'aa_oxyma_dic_v1'),
        start_program=data.get('start_program'),
        end_program=data.get('end_program'),
        per_aa_overrides=data.get('per_aa_overrides', {}),
        double_couple_difficult=data.get('double_couple_difficult', True),
        perform_capping=data.get('perform_capping', True),
        monitor_coupling=data.get('monitor_coupling', False),
        save_sample_each_cycle=data.get('save_sample_each_cycle', False)
    )
    
    return config


def create_default_synthesis_config(output_path: Path, sequence: str = "FMRF", scale_mmol: float = 0.1) -> bool:
    """Create a default synthesis configuration file."""
    try:
        config_data = {
            'sequence': sequence,
            'scale': {
                'target_mmol': scale_mmol,
                'loading_mmol_g': 0.5
            },
            'default_aa_program': 'aa_oxyma_dic_v1',
            'start_program': None,
            'end_program': None,
            'per_aa_overrides': {},
            'double_couple_difficult': True,
            'perform_capping': True,
            'monitor_coupling': False,
            'save_sample_each_cycle': False
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)
        
        return True
        
    except Exception as e:
        print(f"Failed to create synthesis config: {e}")
        return False