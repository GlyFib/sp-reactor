from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import logging
from datetime import datetime, timedelta
import threading
import time


class SynthesisStatus(Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"
    ABORTED = "aborted"


class SynthesisScheduler:
    """Main coordination class for peptide synthesis execution."""
    
    def __init__(self, device_manager=None):
        self.device_manager = device_manager
        self.status = SynthesisStatus.IDLE
        self.current_sequence = None
        self.current_program = None
        self.synthesis_thread = None
        self.pause_event = threading.Event()
        self.abort_flag = threading.Event()
        
        # Synthesis tracking
        self.start_time = None
        self.estimated_end_time = None
        self.current_amino_acid = 0
        self.total_amino_acids = 0
        self.synthesis_log = []
        self.error_message = None
        
        # Callbacks for UI updates
        self.status_callbacks = []
        self.progress_callbacks = []
        
        self.logger = logging.getLogger("synthesis.scheduler")
        
    def add_status_callback(self, callback: Callable[[SynthesisStatus, str], None]):
        """Add callback for status updates."""
        self.status_callbacks.append(callback)
        
    def add_progress_callback(self, callback: Callable[[int, int, float], None]):
        """Add callback for progress updates (current_aa, total_aa, percent)."""
        self.progress_callbacks.append(callback)
        
    def set_status(self, status: SynthesisStatus, message: str = ""):
        """Update synthesis status and notify callbacks."""
        self.status = status
        if status == SynthesisStatus.ERROR:
            self.error_message = message
            self.logger.error(f"Synthesis error: {message}")
        else:
            self.logger.info(f"Status: {status.value} - {message}")
            
        for callback in self.status_callbacks:
            try:
                callback(status, message)
            except Exception as e:
                self.logger.error(f"Status callback error: {e}")
                
    def update_progress(self, current_aa: int, total_aa: int):
        """Update synthesis progress and notify callbacks."""
        self.current_amino_acid = current_aa
        self.total_amino_acids = total_aa
        progress_percent = (current_aa / total_aa * 100) if total_aa > 0 else 0
        
        for callback in self.progress_callbacks:
            try:
                callback(current_aa, total_aa, progress_percent)
            except Exception as e:
                self.logger.error(f"Progress callback error: {e}")
                
    def validate_sequence(self, sequence: str) -> bool:
        """Validate peptide sequence format and amino acid codes."""
        if not sequence:
            self.set_status(SynthesisStatus.ERROR, "Empty sequence provided")
            return False
            
        valid_aa_codes = set("ACDEFGHIKLMNPQRSTVWY")
        invalid_codes = set(sequence.upper()) - valid_aa_codes
        
        if invalid_codes:
            self.set_status(SynthesisStatus.ERROR, f"Invalid amino acid codes: {invalid_codes}")
            return False
            
        self.logger.info(f"Sequence validated: {sequence} ({len(sequence)} amino acids)")
        return True
        
    def validate_devices(self, required_devices: List[str]) -> bool:
        """Validate that all required devices are available and ready."""
        if not self.device_manager:
            self.set_status(SynthesisStatus.ERROR, "No device manager available")
            return False
            
        for device_id in required_devices:
            device = self.device_manager.get_device(device_id)
            if not device:
                self.set_status(SynthesisStatus.ERROR, f"Required device not found: {device_id}")
                return False
                
            if not device.is_ready():
                self.set_status(SynthesisStatus.ERROR, f"Device not ready: {device_id}")
                return False
                
        self.logger.info(f"All required devices validated: {required_devices}")
        return True
        
    def estimate_total_time(self, sequence: str, program: Any, parameters: Dict[str, Any]) -> float:
        """Estimate total synthesis time in minutes."""
        if not sequence or not program:
            return 0.0
            
        aa_count = len(sequence)
        time_per_aa = program.estimate_execution_time(parameters)
        total_time = aa_count * time_per_aa
        
        self.logger.info(f"Estimated synthesis time: {total_time:.1f} minutes for {aa_count} amino acids")
        return total_time
        
    def prepare_synthesis(self, sequence: str, program: Any, parameters: Dict[str, Any]) -> bool:
        """Prepare synthesis by validating inputs and devices."""
        self.set_status(SynthesisStatus.PREPARING, "Validating synthesis parameters")
        
        if not self.validate_sequence(sequence):
            return False
            
        if not program.validate_parameters(parameters):
            self.set_status(SynthesisStatus.ERROR, "Invalid program parameters")
            return False
            
        required_devices = program.get_required_devices()
        if not self.validate_devices(required_devices):
            return False
            
        # Store synthesis parameters
        self.current_sequence = sequence.upper()
        self.current_program = program
        self.total_amino_acids = len(sequence)
        self.current_amino_acid = 0
        
        # Estimate timing
        estimated_duration = self.estimate_total_time(sequence, program, parameters)
        self.estimated_end_time = datetime.now() + timedelta(minutes=estimated_duration)
        
        self.set_status(SynthesisStatus.IDLE, "Ready to start synthesis")
        return True
        
    def start_synthesis(self, sequence: str, program: Any, parameters: Dict[str, Any]) -> bool:
        """Start peptide synthesis in background thread."""
        if self.status == SynthesisStatus.RUNNING:
            self.set_status(SynthesisStatus.ERROR, "Synthesis already running")
            return False
            
        if not self.prepare_synthesis(sequence, program, parameters):
            return False
            
        # Reset control flags
        self.pause_event.clear()
        self.abort_flag.clear()
        
        # Start synthesis thread
        self.synthesis_thread = threading.Thread(
            target=self._synthesis_worker,
            args=(parameters,),
            daemon=True
        )
        self.synthesis_thread.start()
        
        self.start_time = datetime.now()
        self.set_status(SynthesisStatus.RUNNING, f"Starting synthesis of {self.current_sequence}")
        return True
        
    def _synthesis_worker(self, parameters: Dict[str, Any]):
        """Background worker for synthesis execution."""
        try:
            sequence = self.current_sequence
            program = self.current_program
            
            for i, amino_acid in enumerate(sequence):
                if self.abort_flag.is_set():
                    self.set_status(SynthesisStatus.ABORTED, "Synthesis aborted by user")
                    return
                    
                # Handle pause
                if self.pause_event.is_set():
                    self.set_status(SynthesisStatus.PAUSED, f"Paused at amino acid {i+1}")
                    self.pause_event.wait()  # Wait until resumed
                    self.set_status(SynthesisStatus.RUNNING, f"Resumed at amino acid {i+1}")
                    
                self.update_progress(i, len(sequence))
                self.set_status(SynthesisStatus.RUNNING, f"Coupling amino acid {i+1}: {amino_acid}")
                
                # Execute program for this amino acid
                aa_parameters = parameters.copy()
                aa_parameters['amino_acid'] = amino_acid
                aa_parameters['position'] = i + 1
                
                success = program.execute(aa_parameters, self.device_manager)
                if not success:
                    self.set_status(SynthesisStatus.ERROR, f"Failed at amino acid {i+1}: {amino_acid}")
                    return
                    
                self.synthesis_log.append({
                    'timestamp': datetime.now(),
                    'amino_acid': amino_acid,
                    'position': i + 1,
                    'status': 'completed'
                })
                
            # Synthesis completed successfully
            self.update_progress(len(sequence), len(sequence))
            self.set_status(SynthesisStatus.COMPLETED, "Synthesis completed successfully")
            
        except Exception as e:
            self.set_status(SynthesisStatus.ERROR, f"Synthesis failed: {str(e)}")
            
    def pause_synthesis(self) -> bool:
        """Pause current synthesis."""
        if self.status != SynthesisStatus.RUNNING:
            return False
            
        self.pause_event.set()
        return True
        
    def resume_synthesis(self) -> bool:
        """Resume paused synthesis."""
        if self.status != SynthesisStatus.PAUSED:
            return False
            
        self.pause_event.clear()
        return True
        
    def abort_synthesis(self) -> bool:
        """Abort current synthesis."""
        if self.status not in [SynthesisStatus.RUNNING, SynthesisStatus.PAUSED]:
            return False
            
        self.abort_flag.set()
        self.pause_event.clear()  # Clear pause if paused
        return True
        
    def get_synthesis_status(self) -> Dict[str, Any]:
        """Get comprehensive synthesis status information."""
        elapsed_time = 0
        remaining_time = 0
        
        if self.start_time:
            elapsed_time = (datetime.now() - self.start_time).total_seconds() / 60
            
        if self.estimated_end_time:
            remaining_time = max(0, (self.estimated_end_time - datetime.now()).total_seconds() / 60)
            
        return {
            'status': self.status.value,
            'sequence': self.current_sequence,
            'current_amino_acid': self.current_amino_acid,
            'total_amino_acids': self.total_amino_acids,
            'progress_percent': (self.current_amino_acid / self.total_amino_acids * 100) if self.total_amino_acids > 0 else 0,
            'elapsed_time_minutes': elapsed_time,
            'remaining_time_minutes': remaining_time,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'estimated_end_time': self.estimated_end_time.isoformat() if self.estimated_end_time else None,
            'error_message': self.error_message,
            'synthesis_log': self.synthesis_log
        }
    
    def export_schedule(self, format_type: str = "dict") -> Any:
        """Export synthesis schedule in specified format."""
        if format_type == "dict":
            return {
                "schedule_info": self.get_synthesis_status(),
                "sequence": self.current_sequence,
                "total_amino_acids": self.total_amino_acids,
                "current_amino_acid": self.current_amino_acid,
                "synthesis_log": self.synthesis_log
            }
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def get_schedule_summary(self) -> Dict[str, Any]:
        """Get summary of synthesis schedule - alias for get_synthesis_status for compatibility."""
        return self.get_synthesis_status()