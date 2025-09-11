#!/usr/bin/env python3
"""
Pure hardware execution system without simulation dependencies.
Executes synthesis steps directly on real hardware devices.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from ..synthesis.coordinator import SynthesisCoordinator
from ..functions.command_exporter import CommandTrackingExecutor
from ..functions.composite_functions import get_composite_function


class HardwareExecutionResult:
    """Result of hardware execution step."""
    
    def __init__(self, step_number: int, success: bool, error_message: str = None):
        self.step_number = step_number
        self.success = success
        self.error_message = error_message
        self.timestamp = datetime.now()


class HardwareExecutor:
    """Pure hardware synthesis executor with no simulation dependencies."""
    
    def __init__(self, coordinator: SynthesisCoordinator, device_manager):
        self.coordinator = coordinator
        self.device_manager = device_manager
        self.logger = logging.getLogger("hardware_executor")
        
        # Hardware execution state
        self.current_step = None
        self.execution_results = []
        self.aborted = False
        
        # Command tracking for logs
        self.command_tracker = CommandTrackingExecutor(mock_mode=False)
    
    def execute_synthesis_schedule(self, schedule) -> List[HardwareExecutionResult]:
        """Execute complete synthesis schedule on hardware."""
        self.logger.info(f"Starting hardware execution of {len(schedule.steps)} steps")
        self.execution_results = []
        
        for step in schedule.steps:
            if self.aborted:
                self.logger.info("Hardware execution aborted by user")
                break
                
            result = self._execute_hardware_step(step)
            self.execution_results.append(result)
            
            if not result.success:
                self.logger.error(f"Step {step.step_number} failed: {result.error_message}")
                break
        
        self.logger.info(f"Hardware execution completed. {len(self.execution_results)} steps processed")
        return self.execution_results
    
    def _execute_hardware_step(self, step) -> HardwareExecutionResult:
        """Execute a single synthesis step on hardware."""
        self.current_step = step
        self.logger.info(f"Executing step {step.step_number}: {step.amino_acid or 'Program'}")
        
        try:
            # Generate executable program for this step
            executable_program = self.coordinator.generate_executable_program(step)
            
            # Execute each program step
            for program_step in executable_program.get('steps', []):
                success = self._execute_program_step(program_step)
                if not success:
                    return HardwareExecutionResult(
                        step.step_number, 
                        False, 
                        f"Program step failed: {program_step.get('function_id', 'unknown')}"
                    )
            
            return HardwareExecutionResult(step.step_number, True)
            
        except Exception as e:
            self.logger.error(f"Hardware execution error in step {step.step_number}: {e}")
            return HardwareExecutionResult(step.step_number, False, str(e))
    
    def _execute_program_step(self, program_step: Dict[str, Any]) -> bool:
        """Execute a single program step on hardware."""
        function_id = program_step['function_id']
        params = program_step['params']
        
        # Get composite function
        composite_function = get_composite_function(function_id)
        if not composite_function:
            self.logger.error(f"Composite function not found: {function_id}")
            return False
        
        # Parse parameters
        if not composite_function.parse_parameters(**params):
            self.logger.error(f"Parameter parsing failed: {composite_function.last_error}")
            return False
        
        # Generate hardware commands
        commands = composite_function.generate_hardware_commands(**params)
        
        # Execute commands with tracking
        try:
            results = self.command_tracker.execute_commands_with_tracking(
                commands,
                program_step['seq'],
                function_id,
                self.device_manager
            )
            
            # Check if any commands failed
            failed_commands = [r for r in results if r.startswith("FAILED:")]
            if failed_commands:
                self.logger.error(f"Hardware commands failed: {failed_commands}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Command execution failed: {e}")
            return False
    
    def abort_execution(self):
        """Abort current execution."""
        self.aborted = True
        self.logger.info("Hardware execution abort requested")
    
    def export_execution_log(self, output_path: Path, synthesis_info: Dict[str, Any] = None) -> Path:
        """Export execution log to CSV."""
        return self.command_tracker.export_to_csv(output_path, synthesis_info)
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary of execution results."""
        total_steps = len(self.execution_results)
        successful_steps = len([r for r in self.execution_results if r.success])
        failed_steps = total_steps - successful_steps
        
        return {
            "total_steps": total_steps,
            "successful_steps": successful_steps,
            "failed_steps": failed_steps,
            "success_rate": successful_steps / total_steps if total_steps > 0 else 0,
            "aborted": self.aborted,
            "command_stats": self.command_tracker.get_summary_statistics()
        }