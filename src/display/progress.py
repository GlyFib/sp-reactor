#!/usr/bin/env python3
"""
Progress tracking and time estimation for peptide synthesis.
Provides real-time progress monitoring with time estimation.
"""

import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class ProgressStep:
    """Represents a single synthesis step for progress tracking."""
    step_number: int
    amino_acid: Optional[str]
    operation: str
    estimated_duration_minutes: float
    actual_start_time: Optional[datetime] = None
    actual_end_time: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, error
    error_message: Optional[str] = None


@dataclass
class SynthesisProgress:
    """Overall synthesis progress tracking."""
    sequence: str
    total_steps: int
    current_step: int = 0
    start_time: Optional[datetime] = None
    estimated_end_time: Optional[datetime] = None
    steps: List[ProgressStep] = field(default_factory=list)
    
    @property
    def progress_percent(self) -> float:
        """Calculate progress percentage."""
        if self.total_steps == 0:
            return 0.0
        return (self.current_step / self.total_steps) * 100
    
    @property
    def elapsed_time(self) -> timedelta:
        """Calculate elapsed time since start."""
        if not self.start_time:
            return timedelta(0)
        return datetime.now() - self.start_time
    
    @property
    def remaining_time(self) -> timedelta:
        """Estimate remaining time based on progress."""
        if not self.start_time or self.current_step == 0:
            return timedelta(0)
        
        elapsed = self.elapsed_time
        if self.current_step >= self.total_steps:
            return timedelta(0)
        
        # Calculate average time per step
        avg_time_per_step = elapsed.total_seconds() / self.current_step
        remaining_steps = self.total_steps - self.current_step
        
        return timedelta(seconds=avg_time_per_step * remaining_steps)


class ProgressTracker:
    """Real-time progress tracking for synthesis operations."""
    
    def __init__(self):
        self.current_progress: Optional[SynthesisProgress] = None
        self.speed_multiplier = 1.0  # For simulation speed control
        self.callbacks = []
        
    def add_callback(self, callback):
        """Add callback for progress updates."""
        self.callbacks.append(callback)
    
    def _notify_callbacks(self):
        """Notify all callbacks of progress update."""
        for callback in self.callbacks:
            try:
                callback(self.current_progress)
            except Exception as e:
                pass  # Ignore callback errors
    
    def start_synthesis(self, sequence: str, steps: List[ProgressStep]):
        """Initialize synthesis progress tracking."""
        self.current_progress = SynthesisProgress(
            sequence=sequence,
            total_steps=len(steps),
            steps=steps,
            start_time=datetime.now()
        )
        
        # Calculate estimated end time
        total_duration = sum(step.estimated_duration_minutes for step in steps)
        adjusted_duration = total_duration / self.speed_multiplier
        self.current_progress.estimated_end_time = (
            datetime.now() + timedelta(minutes=adjusted_duration)
        )
        
        self._notify_callbacks()
    
    def start_step(self, step_number: int):
        """Mark step as started."""
        if not self.current_progress or step_number >= len(self.current_progress.steps):
            return
        
        step = self.current_progress.steps[step_number]
        step.actual_start_time = datetime.now()
        step.status = "running"
        self.current_progress.current_step = step_number
        
        self._notify_callbacks()
    
    def complete_step(self, step_number: int, success: bool = True, error_message: str = None):
        """Mark step as completed."""
        if not self.current_progress or step_number >= len(self.current_progress.steps):
            return
        
        step = self.current_progress.steps[step_number]
        step.actual_end_time = datetime.now()
        step.status = "completed" if success else "error"
        if error_message:
            step.error_message = error_message
        
        if success:
            self.current_progress.current_step = step_number + 1
        
        self._notify_callbacks()
    
    def set_speed_multiplier(self, multiplier: float):
        """Set simulation speed multiplier."""
        self.speed_multiplier = max(0.1, min(10.0, multiplier))
        
        # Recalculate estimated end time
        if self.current_progress:
            remaining_steps = self.current_progress.steps[self.current_progress.current_step:]
            remaining_duration = sum(step.estimated_duration_minutes for step in remaining_steps)
            adjusted_duration = remaining_duration / self.speed_multiplier
            
            self.current_progress.estimated_end_time = (
                datetime.now() + timedelta(minutes=adjusted_duration)
            )
            
            self._notify_callbacks()
    
    def get_current_step_info(self) -> Optional[Dict[str, Any]]:
        """Get information about current step."""
        if not self.current_progress:
            return None
        
        if self.current_progress.current_step >= len(self.current_progress.steps):
            return None
        
        current_step = self.current_progress.steps[self.current_progress.current_step]
        
        # Calculate step progress if running
        step_progress = 0.0
        if current_step.status == "running" and current_step.actual_start_time:
            elapsed = (datetime.now() - current_step.actual_start_time).total_seconds() / 60
            estimated = current_step.estimated_duration_minutes / self.speed_multiplier
            step_progress = min(1.0, elapsed / estimated) if estimated > 0 else 0.0
        
        return {
            'step_number': current_step.step_number + 1,
            'amino_acid': current_step.amino_acid,
            'operation': current_step.operation,
            'status': current_step.status,
            'estimated_duration': current_step.estimated_duration_minutes,
            'step_progress': step_progress,
            'error_message': current_step.error_message
        }
    
    def get_synthesis_summary(self) -> Dict[str, Any]:
        """Get complete synthesis progress summary."""
        if not self.current_progress:
            return {}
        
        completed_steps = sum(1 for step in self.current_progress.steps if step.status == "completed")
        error_steps = sum(1 for step in self.current_progress.steps if step.status == "error")
        
        return {
            'sequence': self.current_progress.sequence,
            'progress_percent': self.current_progress.progress_percent,
            'current_step': self.current_progress.current_step + 1,
            'total_steps': self.current_progress.total_steps,
            'completed_steps': completed_steps,
            'error_steps': error_steps,
            'elapsed_time': str(self.current_progress.elapsed_time).split('.')[0],
            'remaining_time': str(self.current_progress.remaining_time).split('.')[0],
            'estimated_end_time': self.current_progress.estimated_end_time.strftime("%H:%M:%S") if self.current_progress.estimated_end_time else None,
            'speed_multiplier': self.speed_multiplier
        }
    
    def is_synthesis_running(self) -> bool:
        """Check if synthesis is currently running."""
        if not self.current_progress:
            return False
        
        return (self.current_progress.current_step < self.current_progress.total_steps and
                any(step.status == "running" for step in self.current_progress.steps))
    
    def is_synthesis_complete(self) -> bool:
        """Check if synthesis is complete."""
        if not self.current_progress:
            return False
        
        return self.current_progress.current_step >= self.current_progress.total_steps


def create_progress_steps_from_schedule(schedule) -> List[ProgressStep]:
    """Create progress steps from a synthesis schedule."""
    progress_steps = []
    
    for i, step in enumerate(schedule.steps):
        amino_acid = step.amino_acid if step.amino_acid else None
        operation = f"{step.program_name}"
        if amino_acid:
            operation = f"Couple {amino_acid}"
        elif "begin" in step.program_name.lower():
            operation = "Initial Setup"
        elif "end" in step.program_name.lower():
            operation = "Final Cleavage"
        
        progress_step = ProgressStep(
            step_number=i,
            amino_acid=amino_acid,
            operation=operation,
            estimated_duration_minutes=step.estimated_time_minutes
        )
        progress_steps.append(progress_step)
    
    return progress_steps