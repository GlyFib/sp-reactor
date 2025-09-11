import json
import yaml
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class ReagentInfo:
    """Information about a reagent for stoichiometry calculations."""
    name: str
    type: str  # 'solution', 'pure_liquid', 'solid'
    concentration_mM: Optional[float] = None  # For solutions
    density_g_ml: Optional[float] = None      # For pure liquids
    molecular_weight: Optional[float] = None  # For pure liquids/solids
    purity: float = 1.0                       # Fraction (0.0-1.0)
    storage_temp: Optional[str] = None        # Storage conditions
    notes: Optional[str] = None


@dataclass
class StoichiometryConfig:
    """Configuration for stoichiometry calculations."""
    # Molar excess ratios (relative to resin)
    aa_excess: float = 3.0          # Amino acid excess
    activator_excess: float = 3.0   # Activator (HBTU/PyBOP) excess  
    dic_excess: float = 4.0         # DIC excess
    base_excess: float = 6.0        # Base (DIPEA) excess
    
    # Standard volumes (mL per gram of resin)
    deprotection_volume_per_g: float = 10.0    # Piperidine/DMF
    capping_volume_per_g: float = 8.0          # Ac2O/DIPEA/DMF
    wash_volume_per_g: float = 6.0             # DMF/DCM wash volumes
    
    # Alternative volumes (mL per mmol of resin) - for direct mmol-based protocols
    deprotection_volume_per_mmol: Optional[float] = None    # Override per_g if specified
    capping_volume_per_mmol: Optional[float] = None         # Override per_g if specified  
    wash_volume_per_mmol: Optional[float] = None            # Override per_g if specified
    coupling_volume_per_mmol: Optional[float] = None        # Total coupling solution volume
    
    # Standard reaction times (minutes)
    deprotection_time: float = 3.0             # First deprotection
    deprotection_time_2: float = 20.0          # Second deprotection  
    coupling_time: float = 60.0                # Standard coupling
    coupling_time_difficult: float = 120.0     # Difficult couplings (Pro, etc.)
    capping_time: float = 5.0                  # Capping reaction
    wash_time: Optional[float] = 2.0           # Wash time parameter
    wash_cycles_dmf: int = 4                   # DMF wash cycles after deprotection
    wash_cycles_dmf_after_depro: Optional[int] = None   # DMF wash cycles after deprotection (override)
    wash_cycles_dmf_after_coupling: Optional[int] = None  # DMF wash cycles after coupling
    wash_cycles_dcm: int = 3                   # DCM wash cycles
    
    # Safety factors
    volume_safety_factor: float = 1.1          # 10% extra volume
    min_transfer_volume: float = 0.1           # Minimum transfer (mL)
    max_transfer_volume: float = 20.0          # Maximum transfer (mL)


class StoichiometryCalculator:
    """Calculates reagent volumes and masses for peptide synthesis."""
    
    def __init__(self, config_file: Optional[Path] = None):
        self.logger = logging.getLogger("stoichiometry_calculator")
        
        # Load configuration
        if config_file and config_file.exists():
            self.config = self._load_config(config_file)
        else:
            self.config = StoichiometryConfig()
        
        # Reagent database
        self.reagents: Dict[str, ReagentInfo] = {}
        
        # Load standard reagents
        self._load_standard_reagents()
    
    def _load_config(self, config_file: Path) -> StoichiometryConfig:
        """Load configuration from YAML file."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            # Create config object from loaded data
            return StoichiometryConfig(**data)
            
        except Exception as e:
            self.logger.warning(f"Could not load config from {config_file}: {e}")
            return StoichiometryConfig()
    
    def _load_standard_reagents(self):
        """Load standard reagents used in SPPS."""
        # Standard amino acids (typical concentrations)
        standard_aas = [
            'Fmoc-A', 'Fmoc-R(Pbf)', 'Fmoc-N(Trt)', 'Fmoc-D(OtBu)', 
            'Fmoc-C(Trt)', 'Fmoc-E(OtBu)', 'Fmoc-Q(Trt)', 'Fmoc-G',
            'Fmoc-H(Trt)', 'Fmoc-I', 'Fmoc-L', 'Fmoc-K(Boc)', 'Fmoc-M',
            'Fmoc-F', 'Fmoc-P', 'Fmoc-S(tBu)', 'Fmoc-T(tBu)', 'Fmoc-W(Boc)',
            'Fmoc-Y(tBu)', 'Fmoc-V'
        ]
        
        for aa in standard_aas:
            self.reagents[aa] = ReagentInfo(
                name=aa,
                type='solution',
                concentration_mM=200.0,  # Standard 0.2 M in DMF
                storage_temp='-20°C'
            )
        
        # Coupling reagents
        self.reagents.update({
            'HBTU': ReagentInfo(
                name='HBTU',
                type='solution', 
                concentration_mM=200.0,
                molecular_weight=379.24,
                storage_temp='-20°C'
            ),
            'PyBOP': ReagentInfo(
                name='PyBOP',
                type='solution',
                concentration_mM=200.0, 
                molecular_weight=520.36,
                storage_temp='-20°C'
            ),
            'DIC': ReagentInfo(
                name='DIC',
                type='pure_liquid',
                density_g_ml=0.815,
                molecular_weight=126.2,
                purity=0.99,
                storage_temp='4°C'
            ),
            'DIPEA': ReagentInfo(
                name='DIPEA',
                type='pure_liquid',
                density_g_ml=0.742,
                molecular_weight=129.24,
                purity=0.99,
                storage_temp='RT'
            )
        })
        
        # Solvents and other reagents
        self.reagents.update({
            'Deprotection': ReagentInfo(
                name='20% Piperidine in DMF',
                type='solution',
                notes='Pre-made deprotection solution'
            ),
            'Capping_A': ReagentInfo(
                name='Ac2O/DIPEA/DMF (5:6:89)',
                type='solution', 
                notes='Pre-made capping solution A'
            ),
            'Capping_B': ReagentInfo(
                name='Ac2O/Pyridine/DMF (5:6:89)',
                type='solution',
                notes='Pre-made capping solution B'
            ),
            'DMF': ReagentInfo(
                name='DMF',
                type='pure_liquid',
                density_g_ml=0.944,
                molecular_weight=73.09
            ),
            'DCM': ReagentInfo(
                name='DCM', 
                type='pure_liquid',
                density_g_ml=1.326,
                molecular_weight=84.93
            )
        })
    
    def add_reagent(self, reagent_info: ReagentInfo):
        """Add or update a reagent in the database."""
        self.reagents[reagent_info.name] = reagent_info
        self.logger.debug(f"Added reagent: {reagent_info.name}")
    
    def calculate_coupling_volumes_legacy(self, resin_mmol: float, aa_name: str, 
                                 activator: str = 'HBTU') -> Dict[str, float]:
        """
        Calculate volumes for amino acid coupling.
        
        Args:
            resin_mmol: Amount of resin in mmol
            aa_name: Amino acid reagent name (e.g., 'Fmoc-A')
            activator: Activator reagent name
        
        Returns:
            Dictionary with reagent volumes in mL
        """
        volumes = {}
        
        # Get reagent info
        aa_reagent = self.reagents.get(aa_name)
        activator_reagent = self.reagents.get(activator)
        dic_reagent = self.reagents.get('DIC')
        dipea_reagent = self.reagents.get('DIPEA')
        
        if not aa_reagent:
            raise ValueError(f"Unknown amino acid reagent: {aa_name}")
        
        # Calculate amino acid volume
        if aa_reagent.type == 'solution' and aa_reagent.concentration_mM:
            aa_mmol_needed = resin_mmol * self.config.aa_excess
            volumes['AA'] = (aa_mmol_needed * 1000) / aa_reagent.concentration_mM
        else:
            raise ValueError(f"Cannot calculate volume for {aa_name} - missing concentration")
        
        # Calculate activator volume
        if activator_reagent and activator_reagent.concentration_mM:
            activator_mmol_needed = resin_mmol * self.config.activator_excess
            volumes['Activator'] = (activator_mmol_needed * 1000) / activator_reagent.concentration_mM
        else:
            # Default: same volume as AA
            volumes['Activator'] = volumes['AA']
        
        # Calculate DIC volume (pure liquid)
        if dic_reagent:
            dic_mmol_needed = resin_mmol * self.config.dic_excess
            dic_mass_mg = dic_mmol_needed * dic_reagent.molecular_weight
            dic_volume_ml = (dic_mass_mg / 1000) / dic_reagent.density_g_ml
            volumes['DIC'] = dic_volume_ml / dic_reagent.purity
        else:
            raise ValueError("DIC reagent not found")
        
        # Calculate base volume (DIPEA) - only for activators that need base
        if dipea_reagent and self._activator_needs_base(activator):
            dipea_mmol_needed = resin_mmol * self.config.base_excess
            dipea_mass_mg = dipea_mmol_needed * dipea_reagent.molecular_weight
            dipea_volume_ml = (dipea_mass_mg / 1000) / dipea_reagent.density_g_ml
            volumes['DIPEA'] = dipea_volume_ml / dipea_reagent.purity
        elif self._activator_needs_base(activator):
            raise ValueError(f"Activator {activator} requires DIPEA base but DIPEA reagent not found")
        
        # Apply safety factor and constraints
        for reagent, volume in volumes.items():
            volume_safe = volume * self.config.volume_safety_factor
            volume_constrained = max(self.config.min_transfer_volume,
                                   min(volume_safe, self.config.max_transfer_volume))
            volumes[reagent] = self._round_volume(volume_constrained)
        
        return volumes
    
    def calculate_wash_volumes(self, resin_grams: float, solvent: str = 'DMF', resin_mmol: Optional[float] = None) -> float:
        """Calculate wash volume based on resin mass or mmol."""
        if self.config.wash_volume_per_mmol is not None and resin_mmol is not None:
            # Use per_mmol calculation for user's current protocol
            volume_ml = resin_mmol * self.config.wash_volume_per_mmol
        else:
            # Use per_g calculation (legacy)
            volume_ml = resin_grams * self.config.wash_volume_per_g
        return self._round_volume(volume_ml)
    
    def calculate_deprotection_volume(self, resin_grams: float, resin_mmol: Optional[float] = None) -> float:
        """Calculate deprotection solution volume."""
        if self.config.deprotection_volume_per_mmol is not None and resin_mmol is not None:
            # Use per_mmol calculation for user's current protocol
            volume_ml = resin_mmol * self.config.deprotection_volume_per_mmol
        else:
            # Use per_g calculation (legacy)
            volume_ml = resin_grams * self.config.deprotection_volume_per_g
        return self._round_volume(volume_ml)
    
    def calculate_capping_volume(self, resin_grams: float, resin_mmol: Optional[float] = None) -> float:
        """Calculate capping solution volume."""
        if self.config.capping_volume_per_mmol is not None and resin_mmol is not None:
            # Use per_mmol calculation for user's current protocol
            volume_ml = resin_mmol * self.config.capping_volume_per_mmol
        else:
            # Use per_g calculation (legacy)
            volume_ml = resin_grams * self.config.capping_volume_per_g
        return self._round_volume(volume_ml)
    
    def calculate_coupling_volumes(self, resin_mmol: float, aa_name: str) -> Dict[str, float]:
        """Calculate coupling solution volumes using simplified program-specific approach."""
        volumes = {}
        
        if self.config.coupling_volume_per_mmol is not None:
            # Use program-specific coupling volume (your new approach)
            coupling_volume = resin_mmol * self.config.coupling_volume_per_mmol
            volumes['coupling_volume'] = self._round_volume(coupling_volume)
        else:
            # Fallback to legacy calculation
            volumes = self.calculate_coupling_volumes_legacy(resin_mmol, aa_name, "HBTU")
            
        return volumes
    
    def get_coupling_time(self, aa_code: str) -> float:
        """Get coupling time based on amino acid difficulty."""
        difficult_aas = {'P', 'G'}  # Proline, Glycine
        
        if aa_code in difficult_aas:
            return self.config.coupling_time_difficult
        else:
            return self.config.coupling_time
    
    def estimate_resin_mass(self, resin_mmol: float, substitution: float = 0.5) -> float:
        """
        Estimate resin mass from mmol loading.
        
        Args:
            resin_mmol: Desired mmol of peptide
            substitution: Resin substitution in mmol/g (typical: 0.3-0.8)
        
        Returns:
            Estimated resin mass in grams
        """
        return resin_mmol / substitution
    
    def _round_volume(self, volume: float, precision: int = 1) -> float:
        """Round volume to specified decimal places."""
        if volume < 1.0:
            precision = 2  # More precision for small volumes
        
        return float(Decimal(str(volume)).quantize(
            Decimal(f"0.{'0' * precision}"), 
            rounding=ROUND_HALF_UP
        ))
    
    def _activator_needs_base(self, activator: str) -> bool:
        """
        Determine if an activator requires base (DIPEA) for coupling.
        
        Chemistry rules:
        - Oxyma/DIC: No base needed (DIC is already a base)
        - HBTU, HATU, PyBOP: Need DIPEA base
        """
        activators_needing_base = {
            'HBTU', 'HATU', 'PYBOP', 'TBTU', 'COMU', 'TATU'
        }
        activators_no_base = {
            'OXYMA', 'HOBT'  # When used with DIC
        }
        
        activator_upper = activator.upper()
        
        if activator_upper in activators_needing_base:
            return True
        elif activator_upper in activators_no_base:
            return False
        else:
            # For current user's protocol: AA:Oxyma:DIC = 4:4:4, no base needed
            # Default to no base for unknown activators based on current setup
            self.logger.info(f"Unknown activator {activator}, using current protocol (no base)")
            return False
    
    def get_reagent_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of all available reagents."""
        summary = {}
        for name, reagent in self.reagents.items():
            summary[name] = {
                'type': reagent.type,
                'concentration_mM': reagent.concentration_mM,
                'density_g_ml': reagent.density_g_ml,
                'storage_temp': reagent.storage_temp,
                'notes': reagent.notes
            }
        return summary


def load_stoichiometry_file(file_path: Path) -> StoichiometryCalculator:
    """Load stoichiometry configuration from file."""
    if file_path.suffix.lower() in ['.yaml', '.yml']:
        return StoichiometryCalculator(file_path)
    elif file_path.suffix.lower() == '.json':
        # Handle JSON format
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        calc = StoichiometryCalculator()
        
        # Load reagents if present
        if 'reagents' in data:
            for reagent_data in data['reagents']:
                reagent = ReagentInfo(**reagent_data)
                calc.add_reagent(reagent)
        
        return calc
    else:
        raise ValueError(f"Unsupported file format: {file_path.suffix}")


def create_default_stoichiometry_file(output_path: Path):
    """Create a default stoichiometry configuration file."""
    config = StoichiometryConfig()
    
    config_dict = {
        'aa_excess': config.aa_excess,
        'activator_excess': config.activator_excess,
        'dic_excess': config.dic_excess,
        'base_excess': config.base_excess,
        'deprotection_volume_per_g': config.deprotection_volume_per_g,
        'capping_volume_per_g': config.capping_volume_per_g,
        'wash_volume_per_g': config.wash_volume_per_g,
        'deprotection_time': config.deprotection_time,
        'deprotection_time_2': config.deprotection_time_2,
        'coupling_time': config.coupling_time,
        'coupling_time_difficult': config.coupling_time_difficult,
        'capping_time': config.capping_time,
        'wash_cycles_dmf': config.wash_cycles_dmf,
        'wash_cycles_dcm': config.wash_cycles_dcm,
        'volume_safety_factor': config.volume_safety_factor,
        'min_transfer_volume': config.min_transfer_volume,
        'max_transfer_volume': config.max_transfer_volume
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f, default_flow_style=False, sort_keys=False)