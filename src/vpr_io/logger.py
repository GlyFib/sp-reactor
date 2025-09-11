#!/usr/bin/env python3
"""
Logger module for synthesis operations and reagent consumption tracking.
Provides structured logging for synthesis execution and analysis.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class SynthesisLogger:
    """Specialized logger for peptide synthesis operations."""
    
    def __init__(self, log_name: str = "synthesis", output_dir: Optional[Path] = None):
        self.log_name = log_name
        self.output_dir = Path(output_dir) if output_dir else Path("logs")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Internal log storage
        self.synthesis_events = []
        self.reagent_usage = {}
        self.timing_data = {}
        
        # Setup Python logger
        self.logger = logging.getLogger(f"synthesis.{log_name}")
        self.logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        self.logger.handlers = []
        
        # Setup file handler
        log_file = self.output_dir / f"{log_name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # Setup console handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def log_synthesis_start(self, sequence: str, scale_mmol: float, schedule_info: Dict[str, Any]):
        """Log the start of synthesis."""
        event = {
            'event_type': 'synthesis_start',
            'timestamp': datetime.now().isoformat(),
            'sequence': sequence,
            'scale_mmol': scale_mmol,
            'total_steps': schedule_info.get('total_steps', 0),
            'estimated_time_minutes': schedule_info.get('estimated_time_minutes', 0),
            'resin_mass_g': schedule_info.get('resin_mass_g', 0)
        }
        
        self.synthesis_events.append(event)
        self.logger.info(f"🚀 Starting synthesis of {sequence} at {scale_mmol} mmol scale")
        self.logger.info(f"   Total steps: {schedule_info.get('total_steps', 0)}")
        self.logger.info(f"   Estimated time: {schedule_info.get('estimated_time_minutes', 0):.1f} minutes")
    
    def log_step_start(self, step_number: int, amino_acid: Optional[str], 
                      operation: str, parameters: Dict[str, Any]):
        """Log the start of a synthesis step."""
        event = {
            'event_type': 'step_start',
            'timestamp': datetime.now().isoformat(),
            'step_number': step_number,
            'amino_acid': amino_acid,
            'operation': operation,
            'parameters': parameters
        }
        
        self.synthesis_events.append(event)
        self.timing_data[f"step_{step_number}_start"] = datetime.now()
        
        aa_info = f" ({amino_acid})" if amino_acid else ""
        self.logger.info(f"🔄 Step {step_number}{aa_info}: {operation}")
        
        # Log key parameters
        key_params = {}
        for param in ['v_1', 'v_2', 'v_3', 'coupling_time']:
            if param in parameters:
                key_params[param] = parameters[param]
        
        if key_params:
            params_str = ', '.join(f"{k}={v}" for k, v in key_params.items())
            self.logger.debug(f"   Parameters: {params_str}")
    
    def log_step_complete(self, step_number: int, success: bool = True, 
                         error_message: Optional[str] = None, 
                         reagents_consumed: Optional[Dict[str, float]] = None):
        """Log the completion of a synthesis step."""
        # Calculate step duration
        start_key = f"step_{step_number}_start"
        duration_minutes = 0.0
        if start_key in self.timing_data:
            duration = datetime.now() - self.timing_data[start_key]
            duration_minutes = duration.total_seconds() / 60
        
        event = {
            'event_type': 'step_complete',
            'timestamp': datetime.now().isoformat(),
            'step_number': step_number,
            'success': success,
            'duration_minutes': duration_minutes,
            'error_message': error_message,
            'reagents_consumed': reagents_consumed or {}
        }
        
        self.synthesis_events.append(event)
        
        # Update reagent usage tracking
        if reagents_consumed:
            for reagent, amount in reagents_consumed.items():
                self.reagent_usage[reagent] = self.reagent_usage.get(reagent, 0) + amount
        
        # Log completion
        status = "✅ Completed" if success else "❌ Failed"
        self.logger.info(f"{status} step {step_number} in {duration_minutes:.1f} minutes")
        
        if error_message:
            self.logger.error(f"   Error: {error_message}")
        
        if reagents_consumed:
            reagent_str = ', '.join(f"{k}:{v:.2f}mL" for k, v in reagents_consumed.items() if v > 0)
            if reagent_str:
                self.logger.debug(f"   Reagents used: {reagent_str}")
    
    def log_reagent_consumption(self, reagent_name: str, volume_ml: float, 
                               operation: str, step_number: Optional[int] = None):
        """Log individual reagent consumption."""
        event = {
            'event_type': 'reagent_consumption',
            'timestamp': datetime.now().isoformat(),
            'reagent_name': reagent_name,
            'volume_ml': volume_ml,
            'operation': operation,
            'step_number': step_number
        }
        
        self.synthesis_events.append(event)
        self.reagent_usage[reagent_name] = self.reagent_usage.get(reagent_name, 0) + volume_ml
        
        step_info = f" (Step {step_number})" if step_number else ""
        self.logger.debug(f"🧪 {reagent_name}: {volume_ml:.2f} mL - {operation}{step_info}")
    
    def log_synthesis_complete(self, success: bool = True, final_message: str = ""):
        """Log synthesis completion."""
        total_duration = 0.0
        start_events = [e for e in self.synthesis_events if e['event_type'] == 'synthesis_start']
        if start_events:
            start_time = datetime.fromisoformat(start_events[0]['timestamp'])
            total_duration = (datetime.now() - start_time).total_seconds() / 60
        
        event = {
            'event_type': 'synthesis_complete',
            'timestamp': datetime.now().isoformat(),
            'success': success,
            'total_duration_minutes': total_duration,
            'final_message': final_message,
            'total_reagent_consumption': self.reagent_usage.copy()
        }
        
        self.synthesis_events.append(event)
        
        status = "🎉 Synthesis completed successfully" if success else "💥 Synthesis failed"
        self.logger.info(f"{status} in {total_duration:.1f} minutes")
        
        if final_message:
            self.logger.info(f"   {final_message}")
        
        # Log reagent summary
        if self.reagent_usage:
            self.logger.info("📊 Total reagent consumption:")
            for reagent, total_volume in sorted(self.reagent_usage.items()):
                self.logger.info(f"   {reagent:<20}: {total_volume:.2f} mL")
    
    def log_pause_resume(self, action: str, step_number: Optional[int] = None):
        """Log synthesis pause/resume events."""
        event = {
            'event_type': 'pause_resume',
            'timestamp': datetime.now().isoformat(),
            'action': action,  # 'pause' or 'resume'
            'step_number': step_number
        }
        
        self.synthesis_events.append(event)
        
        action_emoji = "⏸️" if action == 'pause' else "▶️"
        step_info = f" at step {step_number}" if step_number else ""
        self.logger.info(f"{action_emoji} Synthesis {action}d{step_info}")
    
    def log_error(self, error_type: str, error_message: str, 
                 step_number: Optional[int] = None, context: Optional[Dict[str, Any]] = None):
        """Log synthesis errors."""
        event = {
            'event_type': 'error',
            'timestamp': datetime.now().isoformat(),
            'error_type': error_type,
            'error_message': error_message,
            'step_number': step_number,
            'context': context or {}
        }
        
        self.synthesis_events.append(event)
        
        step_info = f" (Step {step_number})" if step_number else ""
        self.logger.error(f"💥 {error_type}{step_info}: {error_message}")
        
        if context:
            for key, value in context.items():
                self.logger.error(f"   {key}: {value}")
    
    def get_synthesis_summary(self) -> Dict[str, Any]:
        """Get complete synthesis summary."""
        start_events = [e for e in self.synthesis_events if e['event_type'] == 'synthesis_start']
        complete_events = [e for e in self.synthesis_events if e['event_type'] == 'synthesis_complete']
        step_events = [e for e in self.synthesis_events if e['event_type'] == 'step_complete']
        error_events = [e for e in self.synthesis_events if e['event_type'] == 'error']
        
        successful_steps = sum(1 for e in step_events if e.get('success', False))
        failed_steps = sum(1 for e in step_events if not e.get('success', True))
        
        summary = {
            'synthesis_started': len(start_events) > 0,
            'synthesis_completed': len(complete_events) > 0,
            'total_steps': len(step_events),
            'successful_steps': successful_steps,
            'failed_steps': failed_steps,
            'error_count': len(error_events),
            'total_reagent_consumption': self.reagent_usage.copy(),
            'event_count': len(self.synthesis_events)
        }
        
        if start_events:
            summary['start_time'] = start_events[0]['timestamp']
            summary['sequence'] = start_events[0]['sequence']
            summary['scale_mmol'] = start_events[0]['scale_mmol']
        
        if complete_events:
            summary['end_time'] = complete_events[0]['timestamp']
            summary['total_duration_minutes'] = complete_events[0]['total_duration_minutes']
            summary['final_success'] = complete_events[0]['success']
        
        return summary
    
    def export_events_json(self, output_path: Optional[Path] = None) -> Path:
        """Export all synthesis events to JSON file."""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"{self.log_name}_events_{timestamp}.json"
        
        export_data = {
            'export_info': {
                'log_name': self.log_name,
                'export_timestamp': datetime.now().isoformat(),
                'event_count': len(self.synthesis_events)
            },
            'synthesis_summary': self.get_synthesis_summary(),
            'events': self.synthesis_events
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, sort_keys=False)
        
        self.logger.info(f"📄 Exported {len(self.synthesis_events)} events to {output_path}")
        return output_path
    
    def clear_logs(self):
        """Clear all logged events and reset counters."""
        self.synthesis_events = []
        self.reagent_usage = {}
        self.timing_data = {}
        self.logger.info("🗑️ Cleared all synthesis logs")