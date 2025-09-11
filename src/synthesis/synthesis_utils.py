"""
Minimal utilities for synthesis calculations.
Replaces the complex StoichiometryCalculator with simple utility functions.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class SynthesisUtils:
    """Minimal utilities for synthesis calculations."""

    @staticmethod
    def estimate_resin_mass(resin_mmol: float, substitution: float = 0.5) -> float:
        """
        Estimate resin mass from mmol loading.
        
        Args:
            resin_mmol: Target resin loading in mmol
            substitution: Resin substitution in mmol/g (default 0.5)
            
        Returns:
            Estimated resin mass in grams
        """
        if substitution <= 0:
            raise ValueError("Resin substitution must be positive")
        
        mass = resin_mmol / substitution
        logger.debug(f"Estimated resin mass: {mass:.3f}g for {resin_mmol:.3f} mmol at {substitution} mmol/g")
        return mass

    @staticmethod  
    def get_coupling_time_default(aa_code: str) -> float:
        """
        Default coupling times - typically overridden by CSV programs.
        
        Args:
            aa_code: Single letter amino acid code
            
        Returns:
            Coupling time in minutes
        """
        difficult_aas = {'P', 'G'}  # Proline, Glycine
        time_minutes = 120.0 if aa_code in difficult_aas else 60.0
        logger.debug(f"Default coupling time for {aa_code}: {time_minutes} minutes")
        return time_minutes

    @staticmethod
    def get_basic_volumes(scale_mmol: float) -> Dict[str, float]:
        """
        Basic volume calculations for simple programs.
        Most programs should specify volume_per_mmol in CSV instead.
        
        Args:
            scale_mmol: Synthesis scale in mmol
            
        Returns:
            Dictionary of basic volumes in mL
        """
        volumes = {
            'deprotection': 16.0 * scale_mmol,  # 16 mL/mmol piperidine
            'coupling_aa': 8.0 * scale_mmol,    # 8 mL/mmol amino acid
            'coupling_activator': 8.0 * scale_mmol,  # 8 mL/mmol activator
            'wash_dmf': 10.0 * scale_mmol,      # 10 mL/mmol DMF wash
            'wash_dcm': 10.0 * scale_mmol       # 10 mL/mmol DCM wash
        }
        
        logger.debug(f"Basic volumes for {scale_mmol} mmol: {volumes}")
        return volumes

    @staticmethod
    def validate_synthesis_params(params: Dict[str, Any]) -> bool:
        """
        Validate basic synthesis parameters.
        
        Args:
            params: Dictionary of synthesis parameters
            
        Returns:
            True if parameters are valid
            
        Raises:
            ValueError: If parameters are invalid
        """
        required_params = ['target_scale_mmol']
        
        for param in required_params:
            if param not in params:
                raise ValueError(f"Missing required parameter: {param}")
        
        scale = params['target_scale_mmol']
        if scale <= 0:
            raise ValueError(f"Scale must be positive, got {scale}")
            
        if scale > 10.0:  # Safety limit
            logger.warning(f"Large scale synthesis: {scale} mmol")
            
        return True