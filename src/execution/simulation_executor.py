#!/usr/bin/env python3
"""
Simulation execution system for virtual peptide synthesis.
Provides timing simulation and interactive controls for development and testing.
"""

import time
import logging
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..synthesis.coordinator import SynthesisCoordinator


@dataclass
class SimulatedCommand:
    """Represents a simulated synthesis command."""
    command_id: str
    function_name: str
    description: str
    parameters: Dict[str, Any]
    estimated_duration_seconds: float
    group_id: Optional[str] = None
    sequence_number: int = 0


@dataclass
class SimulationResult:
    """Result of simulated command execution."""
    command_id: str
    success: bool
    actual_duration_seconds: float
    start_time: datetime
    end_time: datetime
    output_message: str
    error_message: Optional[str] = None


class SimulationExecutor:
    """Executes commands with timing simulation and progress tracking."""
    
    def __init__(self, speed_multiplier: float = 1.0):
        self.logger = logging.getLogger("simulation_executor")
        self.speed_multiplier = speed_multiplier
        self.paused = False
        self.callbacks: List[Callable] = []
    
    def add_callback(self, callback: Callable):
        """Add callback for execution updates."""
        self.callbacks.append(callback)
    
    def set_speed_multiplier(self, speed: float):
        """Set execution speed multiplier."""
        self.speed_multiplier = max(0.1, min(10.0, speed))
    
    def set_paused(self, paused: bool):
        """Pause or resume execution."""
        self.paused = paused
    
    def execute_simulated_command(self, command: SimulatedCommand) -> SimulationResult:
        """Execute a single command with timing simulation."""
        start_time = datetime.now()
        
        # Calculate actual duration with speed multiplier
        actual_duration = command.estimated_duration_seconds / self.speed_multiplier
        
        # Simulate execution with pause support
        elapsed = 0
        update_interval = 0.1  # Update every 100ms
        
        self._notify_callbacks({
            'type': 'command_started',
            'command': command,
            'start_time': start_time
        })
        
        while elapsed < actual_duration:
            if not self.paused:
                time.sleep(update_interval)
                elapsed += update_interval
                
                # Send progress update
                self._notify_callbacks({
                    'type': 'command_progress',
                    'command': command,
                    'progress': elapsed / actual_duration,
                    'elapsed_seconds': elapsed
                })
            else:
                time.sleep(0.1)  # Still sleep while paused
        
        end_time = datetime.now()
        
        # Create result
        result = SimulationResult(
            command_id=command.command_id,
            success=True,  # Always succeed in simulation
            actual_duration_seconds=elapsed,
            start_time=start_time,
            end_time=end_time,
            output_message=f"✅ {command.description}"
        )
        
        self._notify_callbacks({
            'type': 'command_completed',
            'command': command,
            'result': result
        })
        
        return result
    
    def execute_simulated_command_list(self, commands: List[SimulatedCommand]) -> List[SimulationResult]:
        """Execute a list of commands in sequence."""
        results = []
        
        self.logger.info(f"Starting simulation of {len(commands)} commands")
        
        for i, command in enumerate(commands):
            self.logger.debug(f"Simulating command {i+1}/{len(commands)}: {command.description}")
            
            result = self.execute_simulated_command(command)
            results.append(result)
            
            if not result.success:
                self.logger.error(f"Command simulation failed: {command.description}")
        
        self.logger.info(f"Completed simulation of {len(commands)} commands")
        return results
    
    def _notify_callbacks(self, event_data: Dict[str, Any]):
        """Notify all callbacks of execution events."""
        for callback in self.callbacks:
            try:
                callback(event_data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")


class SimulationCommandGenerator:
    """Generates simulated commands from synthesis programs."""
    
    def __init__(self):
        self.logger = logging.getLogger("simulation_command_generator")
        
        # Port mapping for human-readable descriptions
        self.port_descriptions = {
            'R1': 'Amino acid reagent',
            'R2': 'Activator (Oxyma)',
            'R3': 'Deprotection solution (Piperidine/DMF)',
            'R4': 'DMF solvent',
            'R5': 'Reactor vessel',
            'R6': 'Waste collection',
            'MV': 'Mixing vessel',
            'RV': 'Reactor vessel'
        }
    
    def generate_commands_from_steps(self, compiled_steps: List[Dict[str, Any]], 
                                   amino_acid: str = None) -> List[SimulatedCommand]:
        """Generate simulated commands from compiled program steps."""
        commands = []
        
        for i, step in enumerate(compiled_steps):
            command = self._convert_step_to_command(step, i + 1, amino_acid)
            if command:
                commands.append(command)
        
        self.logger.info(f"Generated {len(commands)} simulated commands")
        return commands
    
    def _convert_step_to_command(self, step: Dict[str, Any], seq_num: int, 
                               amino_acid: str = None) -> Optional[SimulatedCommand]:
        """Convert a single compiled step to a simulated command."""
        function_id = step.get('function_id', 'unknown')
        params = step.get('params', {})
        comments = step.get('comments', '')
        group_id = step.get('group_id')
        
        # Generate command based on function type
        if function_id == 'transfer_reagent':
            return self._create_transfer_command(step, seq_num, amino_acid)
        elif function_id == 'agitate_reactor':
            return self._create_agitate_command(step, seq_num)
        elif function_id == 'drain_reactor':
            return self._create_drain_command(step, seq_num)
        elif function_id == 'set_valve_position':
            return self._create_valve_command(step, seq_num)
        else:
            # Generic command for unknown functions
            return SimulatedCommand(
                command_id=f"step_{seq_num}_{function_id}",
                function_name=function_id,
                description=f"Execute {function_id}: {comments}",
                parameters=params,
                estimated_duration_seconds=self._estimate_step_duration(step),
                group_id=group_id,
                sequence_number=seq_num
            )
    
    def _create_transfer_command(self, step: Dict[str, Any], seq_num: int, 
                               amino_acid: str = None) -> SimulatedCommand:
        """Create transfer command with human-readable description."""
        params = step.get('params', {})
        comments = step.get('comments', '')
        volume_calc = step.get('volume_calculation', {})
        
        source_port = params.get('source_port', 'unknown')
        dest_port = params.get('dest_port', 'unknown')
        volume_ml = volume_calc.get('calculated_volume_ml', params.get('volume_ml', 0))
        
        source_desc = self.port_descriptions.get(source_port, source_port)
        dest_desc = self.port_descriptions.get(dest_port, dest_port)
        
        if amino_acid and source_port == 'R1':
            source_desc = f"Fmoc-{amino_acid} solution"
        
        description = f"Transfer {volume_ml:.3f} mL from {source_desc} to {dest_desc}"
        if comments:
            description += f" ({comments})"
        
        return SimulatedCommand(
            command_id=f"transfer_{seq_num}",
            function_name="transfer_reagent",
            description=description,
            parameters=params,
            estimated_duration_seconds=self._calculate_transfer_time(volume_ml),
            group_id=step.get('group_id'),
            sequence_number=seq_num
        )
    
    def _create_agitate_command(self, step: Dict[str, Any], seq_num: int) -> SimulatedCommand:
        """Create agitation command."""
        params = step.get('params', {})
        comments = step.get('comments', '')
        
        duration_sec = params.get('time_seconds', 0)
        duration_min = params.get('time_minutes', duration_sec / 60)
        
        if duration_min > 1:
            time_desc = f"{duration_min:.1f} minutes"
        else:
            time_desc = f"{duration_sec:.0f} seconds"
        
        description = f"Agitate reactor for {time_desc}"
        if comments:
            description += f" ({comments})"
        
        return SimulatedCommand(
            command_id=f"agitate_{seq_num}",
            function_name="agitate_reactor",
            description=description,
            parameters=params,
            estimated_duration_seconds=duration_sec,
            group_id=step.get('group_id'),
            sequence_number=seq_num
        )
    
    def _create_drain_command(self, step: Dict[str, Any], seq_num: int) -> SimulatedCommand:
        """Create drain command."""
        params = step.get('params', {})
        comments = step.get('comments', '')
        
        description = "Drain reactor contents to waste"
        if comments:
            description += f" ({comments})"
        
        return SimulatedCommand(
            command_id=f"drain_{seq_num}",
            function_name="drain_reactor", 
            description=description,
            parameters=params,
            estimated_duration_seconds=10.0,  # Default drain time
            group_id=step.get('group_id'),
            sequence_number=seq_num
        )
    
    def _create_valve_command(self, step: Dict[str, Any], seq_num: int) -> SimulatedCommand:
        """Create valve positioning command."""
        params = step.get('params', {})
        position = params.get('valve_position', 0)
        
        description = f"Set valve to position {position}"
        
        return SimulatedCommand(
            command_id=f"valve_{seq_num}",
            function_name="set_valve_position",
            description=description,
            parameters=params,
            estimated_duration_seconds=2.0,  # Quick valve movement
            group_id=step.get('group_id'),
            sequence_number=seq_num
        )
    
    def _calculate_transfer_time(self, volume_ml: float) -> float:
        """Calculate transfer time based on volume and flow rate."""
        flow_rate_ml_per_sec = 0.5  # Typical pump flow rate
        return max(2.0, volume_ml / flow_rate_ml_per_sec)  # Minimum 2 seconds
    
    def _estimate_step_duration(self, step: Dict[str, Any]) -> float:
        """Estimate step duration from parameters."""
        params = step.get('params', {})
        
        # Check for explicit timing
        if 'time_seconds' in params:
            return float(params['time_seconds'])
        elif 'time_minutes' in params:
            return float(params['time_minutes']) * 60
        
        # Estimate based on function type
        function_id = step.get('function_id', '')
        if function_id == 'transfer_reagent':
            volume = params.get('volume_ml', 0)
            return self._calculate_transfer_time(volume)
        
        return 5.0  # Default 5 seconds for unknown operations


class SynthesisSimulationExecutor:
    """High-level executor for simulated synthesis steps."""
    
    def __init__(self, coordinator: SynthesisCoordinator, speed_multiplier: float = 1.0):
        self.coordinator = coordinator
        self.command_generator = SimulationCommandGenerator()
        self.simulation_executor = SimulationExecutor(speed_multiplier)
        self.logger = logging.getLogger("synthesis_simulation_executor")
        
        self.current_step = None
        self.current_commands = []
        self.execution_callbacks = []
    
    def add_execution_callback(self, callback: Callable):
        """Add callback for execution updates."""
        self.execution_callbacks.append(callback)
        self.simulation_executor.add_callback(callback)
    
    def set_speed_multiplier(self, speed: float):
        """Set execution speed."""
        self.simulation_executor.set_speed_multiplier(speed)
    
    def set_paused(self, paused: bool):
        """Pause or resume execution."""
        self.simulation_executor.set_paused(paused)
    
    def execute_synthesis_step_simulation(self, step) -> List[SimulationResult]:
        """Execute a synthesis step simulation by generating and running simulated commands."""
        self.current_step = step
        
        self.logger.info(f"Simulating synthesis step {step.step_number}: {step.amino_acid or 'Program'}")
        
        try:
            # Check if this is an enhanced program first
            from ..programs.programs import get_enhanced_program
            enhanced_program = get_enhanced_program(step.program_name)
            
            if enhanced_program:
                # For enhanced programs, get the compiled program directly
                target_mmol = step.parameters.get('resin_mmol', 
                             step.parameters.get('target_mmol', 0.1))
                
                compiled_program = enhanced_program.compile_for_scale(target_mmol)
                
                if compiled_program:
                    compiled_steps = compiled_program.get('steps', [])
                else:
                    self.logger.error(f"Failed to compile enhanced program: {step.program_name}")
                    return []
            else:
                # Generate executable program with substituted parameters (legacy method)
                executable_program = self.coordinator.generate_executable_program(step)
                compiled_steps = executable_program.get('steps', [])
            
            # Generate simulated commands from compiled steps
            self.current_commands = self.command_generator.generate_commands_from_steps(
                compiled_steps, step.amino_acid
            )
            
            # Execute simulated commands
            results = self.simulation_executor.execute_simulated_command_list(self.current_commands)
            
            self.logger.info(f"Step {step.step_number} simulation completed with {len(results)} commands")
            return results
            
        except Exception as e:
            self.logger.error(f"Failed to simulate step {step.step_number}: {e}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return []
    
    def get_current_command_info(self) -> Optional[Dict[str, Any]]:
        """Get information about currently simulating command."""
        if not self.current_commands:
            return None
        
        if self.current_commands:
            cmd = self.current_commands[0]
            return {
                'command_description': cmd.description,
                'function_name': cmd.function_name,
                'estimated_duration': cmd.estimated_duration_seconds,
                'parameters': cmd.parameters
            }
        
        return None