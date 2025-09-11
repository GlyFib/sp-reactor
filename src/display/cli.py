#!/usr/bin/env python3
"""
Interactive CLI for the Virtual Peptide Reactor.
Provides real-time synthesis monitoring with interactive controls.
"""

import os
import sys
import time
import threading
import signal
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.display.progress import ProgressTracker, create_progress_steps_from_schedule
from src.synthesis.coordinator import SynthesisCoordinator, SynthesisParameters
from src.synthesis.stoichiometry_deprecated import StoichiometryCalculator
from src.synthesis.command_executor import SynthesisStepExecutor


class SynthesisCLI:
    """Interactive CLI for peptide synthesis monitoring and control."""
    
    def __init__(self):
        self.progress_tracker = ProgressTracker()
        self.synthesis_coordinator = None
        self.current_schedule = None
        self.synthesis_thread = None
        self.running = True
        self.paused = False
        self.speed_multiplier = 1.0
        
        # CLI state
        self.show_details = False
        self.last_display_time = 0
        self.display_interval = 1.0  # Update every second
        
        # Command execution tracking
        self.step_executor = None
        self.current_command_info = None
        self.command_progress = 0.0
        self.total_commands_in_step = 0
        self.completed_commands_in_step = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        
        # Setup progress callback
        self.progress_tracker.add_callback(self._on_progress_update)
    
    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C gracefully."""
        self.running = False
        print("\n\n🛑 Synthesis interrupted by user")
        sys.exit(0)
    
    def _on_progress_update(self, progress):
        """Callback for progress updates."""
        current_time = time.time()
        if current_time - self.last_display_time >= self.display_interval:
            self._update_display()
            self.last_display_time = current_time
    
    def _on_command_execution_event(self, event_data):
        """Callback for command execution events."""
        event_type = event_data.get('type')
        
        if event_type == 'command_started':
            command = event_data['command']
            self.current_command_info = {
                'description': command.description,
                'function_name': command.function_name,
                'estimated_duration': command.estimated_duration_seconds,
                'start_time': event_data['start_time']
            }
            self.command_progress = 0.0
            
        elif event_type == 'command_progress':
            self.command_progress = event_data['progress']
            
        elif event_type == 'command_completed':
            self.completed_commands_in_step += 1
            self.command_progress = 1.0
            
        # Force display update for command events
        self._update_display()
    
    def _clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def _get_input_non_blocking(self):
        """Get keyboard input without blocking (Unix only)."""
        try:
            import select
            import tty
            import termios
            
            if select.select([sys.stdin], [], [], 0) == ([sys.stdin], [], []):
                old_settings = termios.tcgetattr(sys.stdin)
                try:
                    tty.setraw(sys.stdin.fileno())
                    return sys.stdin.read(1).upper()
                finally:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        except ImportError:
            # Windows compatibility - use input() instead
            pass
        return None
    
    def _create_progress_bar(self, percent: float, width: int = 40) -> str:
        """Create a text progress bar."""
        filled = int(width * percent / 100)
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {percent:.1f}%"
    
    def _format_time(self, time_str: str) -> str:
        """Format time string for display."""
        if not time_str or time_str == "0:00:00":
            return "00:00:00"
        return time_str
    
    def _update_display(self):
        """Update the CLI display."""
        if not self.progress_tracker.current_progress:
            return
        
        self._clear_screen()
        
        # Header
        print("🧪 Virtual Peptide Reactor - Synthesis Monitor")
        print("=" * 60)
        
        # Synthesis summary
        summary = self.progress_tracker.get_synthesis_summary()
        current_step_info = self.progress_tracker.get_current_step_info()
        
        print(f"📋 Sequence: {summary.get('sequence', 'Unknown')}")
        print(f"⚡ Speed: {summary.get('speed_multiplier', 1.0):.1f}x")
        print()
        
        # Overall progress
        progress_percent = summary.get('progress_percent', 0)
        progress_bar = self._create_progress_bar(progress_percent)
        
        print("📊 Overall Progress:")
        print(f"   {progress_bar}")
        print(f"   Step {summary.get('current_step', 0)}/{summary.get('total_steps', 0)}")
        print()
        
        # Current step details
        if current_step_info:
            print("🔄 Current Step:")
            aa = current_step_info.get('amino_acid', 'N/A')
            operation = current_step_info.get('operation', 'Unknown')
            status = current_step_info.get('status', 'Unknown')
            
            print(f"   Step {current_step_info.get('step_number', 0)}: {operation}")
            if aa and aa != 'N/A':
                print(f"   Amino Acid: {aa}")
            print(f"   Status: {status.upper()}")
            
            # Step progress bar
            step_progress = current_step_info.get('step_progress', 0) * 100
            step_bar = self._create_progress_bar(step_progress, 30)
            print(f"   Step Progress: {step_bar}")
            
            # Show current command details if available
            if self.current_command_info:
                print(f"\n   🔧 Current Command:")
                print(f"      {self.current_command_info['description']}")
                
                # Command progress bar
                cmd_progress = self.command_progress * 100
                cmd_bar = self._create_progress_bar(cmd_progress, 25)
                print(f"      Progress: {cmd_bar}")
                
                # Show command timing
                if self.current_command_info.get('start_time'):
                    elapsed = (datetime.now() - self.current_command_info['start_time']).total_seconds()
                    estimated = self.current_command_info['estimated_duration']
                    print(f"      Elapsed: {elapsed:.1f}s / {estimated:.1f}s")
                
                # Show step command progress
                if self.total_commands_in_step > 0:
                    print(f"      Command {self.completed_commands_in_step + 1}/{self.total_commands_in_step}")
            
            if current_step_info.get('error_message'):
                print(f"   ❌ Error: {current_step_info['error_message']}")
            print()
        
        # Timing information
        print("⏱️  Timing:")
        print(f"   Elapsed:   {self._format_time(summary.get('elapsed_time', '00:00:00'))}")
        print(f"   Remaining: {self._format_time(summary.get('remaining_time', '00:00:00'))}")
        if summary.get('estimated_end_time'):
            print(f"   Est. End:  {summary['estimated_end_time']}")
        print()
        
        # Synthesis statistics
        if self.show_details and self.current_schedule:
            print("📈 Synthesis Details:")
            print(f"   Completed Steps: {summary.get('completed_steps', 0)}")
            print(f"   Error Steps: {summary.get('error_steps', 0)}")
            print(f"   Resin Mass: {self.current_schedule.resin_mass_g:.2f} g")
            print(f"   Target Scale: {self.current_schedule.target_scale_mmol:.2f} mmol")
            print()
            
            # Show reagent consumption (top 5)
            consumption = self.current_schedule.total_reagent_consumption
            if consumption:
                print("🧪 Reagent Consumption:")
                for reagent, amount in list(consumption.items())[:5]:
                    print(f"   {reagent:<20}: {amount:.2f} mL")
                if len(consumption) > 5:
                    print(f"   ... and {len(consumption) - 5} more reagents")
                print()
        
        # Status indicators
        status_line = "🟢 RUNNING" if not self.paused else "🟡 PAUSED"
        if summary.get('error_steps', 0) > 0:
            status_line += " ⚠️  ERRORS"
        
        print(f"Status: {status_line}")
        print()
        
        # Interactive controls
        print("🎮 Controls: [S]peed | [P]ause/Resume | [D]etails | [Q]uit")
        print("   (Press key + Enter)")
        print()
    
    def _handle_user_input(self):
        """Handle user keyboard input."""
        try:
            user_input = input().strip().upper()
            
            if user_input == 'S':
                self._handle_speed_control()
            elif user_input == 'P':
                self._handle_pause_toggle()
            elif user_input == 'D':
                self._handle_details_toggle()
            elif user_input == 'Q':
                self._handle_quit()
                
        except (EOFError, KeyboardInterrupt):
            self._handle_quit()
    
    def _handle_speed_control(self):
        """Handle speed control input."""
        try:
            print("Enter speed multiplier (0.1 - 10.0, current: {:.1f}): ".format(self.speed_multiplier), end="")
            speed_input = input().strip()
            
            if speed_input:
                new_speed = float(speed_input)
                if 0.1 <= new_speed <= 10.0:
                    self.speed_multiplier = new_speed
                    self.progress_tracker.set_speed_multiplier(new_speed)
                    if self.step_executor:
                        self.step_executor.set_speed_multiplier(new_speed)
                    print(f"Speed set to {new_speed:.1f}x")
                else:
                    print("Speed must be between 0.1 and 10.0")
            
        except ValueError:
            print("Invalid speed value")
        
        time.sleep(1)  # Brief pause to show message
    
    def _handle_pause_toggle(self):
        """Handle pause/resume toggle."""
        self.paused = not self.paused
        if self.step_executor:
            self.step_executor.set_paused(self.paused)
        status = "PAUSED" if self.paused else "RESUMED"
        print(f"Synthesis {status}")
        time.sleep(1)
    
    def _handle_details_toggle(self):
        """Handle details view toggle."""
        self.show_details = not self.show_details
        status = "ON" if self.show_details else "OFF"
        print(f"Details view {status}")
        time.sleep(1)
    
    def _handle_quit(self):
        """Handle quit command."""
        self.running = False
        print("\n🛑 Synthesis monitoring stopped")
        sys.exit(0)
    
    def _execute_synthesis_step_with_commands(self, step, step_number):
        """Execute a synthesis step using the command-based system."""
        # Start step
        self.progress_tracker.start_step(step_number)
        
        # Reset command tracking
        self.completed_commands_in_step = 0
        self.total_commands_in_step = 0
        self.current_command_info = None
        self.command_progress = 0.0
        
        try:
            # Execute step using step executor
            if self.step_executor and step:
                results = self.step_executor.execute_synthesis_step(step)
                
                # Update total commands count
                self.total_commands_in_step = len(results)
                
                # Complete step if successful
                if results and all(r.success for r in results):
                    self.progress_tracker.complete_step(step_number, success=True)
                else:
                    # Handle partial failure
                    error_msg = f"Step failed: {len([r for r in results if not r.success])} commands failed"
                    self.progress_tracker.complete_step(step_number, success=False, error_message=error_msg)
            else:
                # Fallback to old simulation method
                self._simulate_synthesis_step_fallback(step_number, 180.0)  # Default 3 hours
                
        except Exception as e:
            # Handle execution error
            error_msg = f"Execution error: {str(e)}"
            self.progress_tracker.complete_step(step_number, success=False, error_message=error_msg)
    
    def _simulate_synthesis_step_fallback(self, step_number, duration_minutes):
        """Fallback simulation method for when command execution fails."""
        # Calculate actual duration (with speed multiplier and pause handling)
        base_duration = duration_minutes * 60  # Convert to seconds
        actual_duration = base_duration / self.speed_multiplier
        
        # Simulate step execution with pause support
        elapsed = 0
        update_interval = 0.1  # Update every 100ms
        
        while elapsed < actual_duration and self.running:
            if not self.paused:
                time.sleep(update_interval)
                elapsed += update_interval
            else:
                time.sleep(0.1)  # Still sleep while paused, but don't count time
        
        # Complete step
        if self.running:
            self.progress_tracker.complete_step(step_number, success=True)
    
    def run_synthesis(self, sequence: str, scale_mmol: float = 0.1, 
                     programs_dir: Optional[Path] = None):
        """Run a complete synthesis with CLI monitoring."""
        
        # Initialize synthesis system
        if not programs_dir:
            programs_dir = project_root / "programs"
        
        self.synthesis_coordinator = SynthesisCoordinator(programs_dir)
        
        # Initialize step executor
        self.step_executor = SynthesisStepExecutor(self.synthesis_coordinator, self.speed_multiplier)
        self.step_executor.add_execution_callback(self._on_command_execution_event)
        
        # Create synthesis parameters
        params = SynthesisParameters(
            peptide_sequence=sequence,
            target_scale_mmol=scale_mmol,
            aa_program="aa_oxyma_dic_v1"  # Use the enhanced program
        )
        
        # Generate synthesis schedule
        print("🔨 Generating synthesis schedule...")
        self.current_schedule = self.synthesis_coordinator.create_synthesis_schedule(params)
        
        # Create progress steps
        progress_steps = create_progress_steps_from_schedule(self.current_schedule)
        
        # Initialize progress tracking
        self.progress_tracker.start_synthesis(sequence, progress_steps)
        
        # Start synthesis simulation in background thread
        self.synthesis_thread = threading.Thread(
            target=self._run_synthesis_simulation_with_commands,
            args=(self.current_schedule.steps,),
            daemon=True
        )
        self.synthesis_thread.start()
        
        # Start display updates
        self._update_display()
        
        # Main interaction loop
        while self.running and not self.progress_tracker.is_synthesis_complete():
            try:
                self._handle_user_input()
            except KeyboardInterrupt:
                break
        
        # Final status
        if self.progress_tracker.is_synthesis_complete():
            print("\n🎉 Synthesis completed successfully!")
        else:
            print("\n🛑 Synthesis stopped")
    
    def _run_synthesis_simulation_with_commands(self, synthesis_steps):
        """Run synthesis simulation using the command-based system."""
        for i, synthesis_step in enumerate(synthesis_steps):
            if not self.running:
                break
            
            self._execute_synthesis_step_with_commands(synthesis_step, i)
    
    def _run_synthesis_simulation(self, progress_steps):
        """DEPRECATED: Old simulation method - kept for compatibility."""
        for i, step_info in enumerate(progress_steps):
            if not self.running:
                break
            
            self._simulate_synthesis_step_fallback(i, step_info.estimated_duration_minutes)
    
    def interactive_sequence_input(self) -> tuple:
        """Interactive peptide sequence input with validation."""
        print("🧪 Virtual Peptide Reactor - Interactive Mode")
        print("=" * 50)
        print()
        
        # Get peptide sequence
        while True:
            sequence = input("Enter peptide sequence (e.g., FMRF-NH2, Ac-YGGFL-NH2): ").strip()
            if not sequence:
                print("Please enter a valid peptide sequence")
                continue
            
            # Basic validation
            from synthesis.sequence_parser import validate_sequence
            is_valid, warnings = validate_sequence(sequence)
            
            if not is_valid:
                print("❌ Invalid sequence. Please check amino acid codes.")
                continue
            
            if warnings:
                print("⚠️  Sequence warnings:")
                for warning in warnings:
                    print(f"   {warning}")
                
                confirm = input("Continue with this sequence? (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
            
            break
        
        # Get synthesis scale
        while True:
            try:
                scale_input = input("Enter synthesis scale in mmol [0.1]: ").strip()
                scale_mmol = float(scale_input) if scale_input else 0.1
                
                if scale_mmol <= 0:
                    print("Scale must be positive")
                    continue
                    
                break
                
            except ValueError:
                print("Please enter a valid number")
        
        # Show synthesis preview
        print(f"\n📋 Synthesis Preview:")
        print(f"   Sequence: {sequence}")
        print(f"   Scale: {scale_mmol} mmol")
        
        confirm = input("\nStart synthesis? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Synthesis cancelled")
            return None, None
        
        return sequence, scale_mmol


def run_interactive_mode():
    """Run the CLI in interactive mode."""
    cli = SynthesisCLI()
    
    # Get sequence and parameters interactively
    sequence, scale = cli.interactive_sequence_input()
    if not sequence:
        return
    
    # Run synthesis with monitoring
    cli.run_synthesis(sequence, scale)


def run_file_mode(sequence_file: Path, config_file: Optional[Path] = None, 
                 scale_mmol: float = 0.1):
    """Run synthesis from file inputs."""
    print(f"🗂️  Loading sequence from: {sequence_file}")
    
    # Load sequence from file
    if sequence_file.suffix == '.txt':
        with open(sequence_file, 'r') as f:
            lines = f.readlines()
            # Find first non-comment line
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#'):
                    sequence = line
                    break
            else:
                print("❌ No valid sequence found in file")
                return
    else:
        print("❌ Unsupported sequence file format")
        return
    
    print(f"📋 Loaded sequence: {sequence}")
    
    # Run synthesis
    cli = SynthesisCLI()
    cli.run_synthesis(sequence, scale_mmol)


if __name__ == "__main__":
    # Simple test mode
    print("🧪 CLI Test Mode")
    run_interactive_mode()