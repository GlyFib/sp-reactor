#!/usr/bin/env python3
"""
Configuration and file I/O management for the Virtual Peptide Reactor.
Handles YAML configuration files, CSV sequence files, and output generation.
"""

import yaml
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import logging


class ConfigManager:
    """Manages YAML configuration files for synthesis parameters."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self.config = {}
        self.logger = logging.getLogger("config_manager")
        
        if config_path and config_path.exists():
            self.load_config()
    
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path:
            self.config_path = config_path
        
        if not self.config_path or not self.config_path.exists():
            self.logger.warning(f"Config file not found: {self.config_path}")
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f)
            
            self.logger.info(f"Loaded configuration from {self.config_path}")
            return self.config
            
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return self._get_default_config()
    
    def save_config(self, config_path: Optional[Path] = None) -> bool:
        """Save current configuration to YAML file."""
        if config_path:
            self.config_path = config_path
        
        if not self.config_path:
            self.logger.error("No config path specified")
            return False
        
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2)
            
            self.logger.info(f"Saved configuration to {self.config_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with dot notation support."""
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value with dot notation support."""
        keys = key.split('.')
        target = self.config
        
        # Navigate to the parent dictionary
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        # Set the value
        target[keys[-1]] = value
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            'synthesis': {
                'default_scale_mmol': 0.1,
                'default_resin_substitution': 0.5,
                'speed_multiplier': 1.0,
                'auto_save_logs': True
            },
            'reagents': {
                'aa_excess': 3.0,
                'dic_excess': 4.0,
                'dipea_excess': 6.0,
                'coupling_time_minutes': 60.0,
                'deprotection_time_minutes': 5.0
            },
            'hardware': {
                'simulation_mode': True,
                'flow_rate_ml_min': 2.0,
                'wash_volume_per_gram': 6.0
            },
            'display': {
                'update_interval_seconds': 1.0,
                'progress_bar_width': 40,
                'show_details_default': False
            },
            'output': {
                'recipe_format': 'csv',
                'log_format': 'txt',
                'include_timestamps': True,
                'output_directory': 'output'
            }
        }


class SequenceFileManager:
    """Manages peptide sequence files in various formats."""
    
    def __init__(self):
        self.logger = logging.getLogger("sequence_manager")
    
    def load_sequence_file(self, file_path: Path) -> Dict[str, Any]:
        """Load peptide sequence from file (TXT or CSV format)."""
        if not file_path.exists():
            raise FileNotFoundError(f"Sequence file not found: {file_path}")
        
        if file_path.suffix.lower() == '.txt':
            return self._load_txt_sequence(file_path)
        elif file_path.suffix.lower() == '.csv':
            return self._load_csv_sequence(file_path)
        else:
            raise ValueError(f"Unsupported sequence file format: {file_path.suffix}")
    
    def _load_txt_sequence(self, file_path: Path) -> Dict[str, Any]:
        """Load sequence from simple text file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        sequence = None
        comments = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                comments.append(line[1:].strip())
            elif line and not sequence:  # First non-comment line
                sequence = line
        
        if not sequence:
            raise ValueError("No valid sequence found in file")
        
        return {
            'sequence': sequence,
            'comments': comments,
            'format': 'txt',
            'source_file': str(file_path)
        }
    
    def _load_csv_sequence(self, file_path: Path) -> Dict[str, Any]:
        """Load sequence from CSV file with optional per-residue parameters."""
        sequence_data = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'amino_acid' in row or 'aa' in row:
                    aa_code = row.get('amino_acid', row.get('aa', '')).strip().upper()
                    if aa_code:
                        entry = {'amino_acid': aa_code}
                        
                        # Optional parameters
                        if 'coupling_time' in row and row['coupling_time']:
                            entry['coupling_time'] = float(row['coupling_time'])
                        
                        if 'position' in row and row['position']:
                            entry['position'] = int(row['position'])
                        
                        sequence_data.append(entry)
        
        if not sequence_data:
            raise ValueError("No valid sequence data found in CSV file")
        
        # Build sequence string
        sequence = ''.join(entry['amino_acid'] for entry in sequence_data)
        
        return {
            'sequence': sequence,
            'sequence_data': sequence_data,
            'format': 'csv',
            'source_file': str(file_path)
        }


class OutputManager:
    """Manages output file generation for synthesis results."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("output_manager")
    
    def generate_recipe_file(self, schedule, format: str = 'csv') -> Path:
        """Generate synthesis recipe file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sequence_short = schedule.peptide_sequence[:6] if len(schedule.peptide_sequence) > 6 else schedule.peptide_sequence
        
        if format.lower() == 'csv':
            filename = f"synthesis_recipe_{sequence_short}_{timestamp}.csv"
            return self._generate_csv_recipe(schedule, filename)
        elif format.lower() == 'json':
            filename = f"synthesis_recipe_{sequence_short}_{timestamp}.json"
            return self._generate_json_recipe(schedule, filename)
        elif format.lower() == 'yaml':
            filename = f"synthesis_recipe_{sequence_short}_{timestamp}.yaml"
            return self._generate_yaml_recipe(schedule, filename)
        else:
            raise ValueError(f"Unsupported recipe format: {format}")
    
    def _generate_csv_recipe(self, schedule, filename: str) -> Path:
        """Generate CSV recipe file."""
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                'Step', 'Amino_Acid', 'Program', 'Operation', 
                'Volume_mL', 'Time_min', 'Notes'
            ])
            
            # Steps
            for step in schedule.steps:
                aa = step.amino_acid or 'N/A'
                program = step.program_name
                
                # Extract key volumes
                v1 = step.parameters.get('v_1', '')
                v2 = step.parameters.get('v_2', '')
                v3 = step.parameters.get('v_3', '')
                volumes = f"v1:{v1} v2:{v2} v3:{v3}" if any([v1, v2, v3]) else ''
                
                writer.writerow([
                    step.step_number,
                    aa,
                    program,
                    step.notes or 'Synthesis step',
                    volumes,
                    f"{step.estimated_time_minutes:.1f}",
                    step.notes or ''
                ])
        
        self.logger.info(f"Generated CSV recipe: {output_path}")
        return output_path
    
    def _generate_json_recipe(self, schedule, filename: str) -> Path:
        """Generate JSON recipe file."""
        output_path = self.output_dir / filename
        
        recipe_data = {
            'synthesis_id': schedule.synthesis_id,
            'peptide_sequence': schedule.peptide_sequence,
            'target_scale_mmol': schedule.target_scale_mmol,
            'resin_mass_g': schedule.resin_mass_g,
            'total_estimated_time_minutes': schedule.total_estimated_time_minutes,
            'created_at': schedule.created_at,
            'steps': []
        }
        
        for step in schedule.steps:
            step_data = {
                'step_number': step.step_number,
                'amino_acid': step.amino_acid,
                'program_name': step.program_name,
                'parameters': step.parameters,
                'estimated_time_minutes': step.estimated_time_minutes,
                'reagents_consumed': step.reagents_consumed,
                'notes': step.notes
            }
            recipe_data['steps'].append(step_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(recipe_data, f, indent=2, sort_keys=False)
        
        self.logger.info(f"Generated JSON recipe: {output_path}")
        return output_path
    
    def _generate_yaml_recipe(self, schedule, filename: str) -> Path:
        """Generate YAML recipe file."""
        output_path = self.output_dir / filename
        
        recipe_data = {
            'synthesis_info': {
                'synthesis_id': schedule.synthesis_id,
                'peptide_sequence': schedule.peptide_sequence,
                'target_scale_mmol': schedule.target_scale_mmol,
                'resin_mass_g': schedule.resin_mass_g,
                'total_estimated_time_minutes': schedule.total_estimated_time_minutes,
                'created_at': schedule.created_at
            },
            'steps': []
        }
        
        for step in schedule.steps:
            step_data = {
                'step_number': step.step_number,
                'amino_acid': step.amino_acid,
                'program_name': step.program_name,
                'parameters': step.parameters,
                'estimated_time_minutes': step.estimated_time_minutes,
                'notes': step.notes
            }
            recipe_data['steps'].append(step_data)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(recipe_data, f, default_flow_style=False, indent=2)
        
        self.logger.info(f"Generated YAML recipe: {output_path}")
        return output_path
    
    def generate_log_file(self, synthesis_log: List[Dict[str, Any]], 
                         sequence: str, format: str = 'txt') -> Path:
        """Generate synthesis execution log."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        sequence_short = sequence[:6] if len(sequence) > 6 else sequence
        
        if format.lower() == 'txt':
            filename = f"synthesis_log_{sequence_short}_{timestamp}.txt"
            return self._generate_txt_log(synthesis_log, sequence, filename)
        elif format.lower() == 'json':
            filename = f"synthesis_log_{sequence_short}_{timestamp}.json"
            return self._generate_json_log(synthesis_log, sequence, filename)
        else:
            raise ValueError(f"Unsupported log format: {format}")
    
    def _generate_txt_log(self, synthesis_log: List[Dict[str, Any]], 
                         sequence: str, filename: str) -> Path:
        """Generate text log file."""
        output_path = self.output_dir / filename
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("🧪 Virtual Peptide Reactor - Synthesis Log\n")
            f.write("=" * 50 + "\n")
            f.write(f"Peptide Sequence: {sequence}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for entry in synthesis_log:
                timestamp = entry.get('timestamp', 'Unknown')
                step = entry.get('step_number', 'N/A')
                aa = entry.get('amino_acid', 'N/A')
                status = entry.get('status', 'Unknown')
                operation = entry.get('operation', 'Unknown')
                
                f.write(f"[{timestamp}] Step {step} ({aa}): {operation} - {status.upper()}\n")
                
                if entry.get('error_message'):
                    f.write(f"    ERROR: {entry['error_message']}\n")
        
        self.logger.info(f"Generated text log: {output_path}")
        return output_path
    
    def _generate_json_log(self, synthesis_log: List[Dict[str, Any]], 
                          sequence: str, filename: str) -> Path:
        """Generate JSON log file."""
        output_path = self.output_dir / filename
        
        log_data = {
            'synthesis_info': {
                'peptide_sequence': sequence,
                'log_generated': datetime.now().isoformat(),
                'total_entries': len(synthesis_log)
            },
            'log_entries': synthesis_log
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, default=str)
        
        self.logger.info(f"Generated JSON log: {output_path}")
        return output_path


def create_default_config_file(config_path: Path) -> bool:
    """Create a default configuration file."""
    config_manager = ConfigManager()
    config_manager.config = config_manager._get_default_config()
    return config_manager.save_config(config_path)