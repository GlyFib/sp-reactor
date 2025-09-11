import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Represents a validation error with context."""
    step_seq: Optional[int]
    error_type: str
    message: str
    severity: str  # 'error', 'warning', 'info'
    context: Optional[Dict[str, Any]] = None


class ProgramValidator:
    """Validates compiled program plans."""
    
    def __init__(self, function_definitions_dir: Path):
        self.function_definitions_dir = Path(function_definitions_dir)
        self.logger = logging.getLogger("program_validator")
        self.available_functions = self._load_available_functions()
    
    def _load_available_functions(self) -> Dict[str, Dict[str, Any]]:
        """Load available function definitions for validation."""
        functions = {}
        
        # Load atomic functions
        atomic_dir = self.function_definitions_dir / "atomic"
        if atomic_dir.exists():
            for json_file in atomic_dir.glob("*.json"):
                func_def = self._load_function_def(json_file)
                if func_def:
                    functions[func_def["function_id"]] = func_def
        
        # Load composite functions
        composite_dir = self.function_definitions_dir / "composite"
        if composite_dir.exists():
            for json_file in composite_dir.glob("*.json"):
                func_def = self._load_function_def(json_file)
                if func_def:
                    functions[func_def["function_id"]] = func_def
        
        self.logger.info(f"Loaded {len(functions)} function definitions for validation")
        return functions
    
    def _load_function_def(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """Load a single function definition."""
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load function definition from {json_file}: {e}")
            return None
    
    def validate_plan(self, plan: Dict[str, Any]) -> List[ValidationError]:
        """
        Validate a compiled program plan.
        Returns list of validation errors/warnings.
        """
        errors = []
        steps = plan.get("steps", [])
        
        # Validate plan structure
        errors.extend(self._validate_plan_structure(plan))
        
        # Validate individual steps
        for step_data in steps:
            errors.extend(self._validate_step(step_data))
        
        # Validate step sequence and dependencies
        errors.extend(self._validate_step_sequence(steps))
        
        # Validate parameter consistency
        errors.extend(self._validate_parameter_consistency(steps))
        
        return errors
    
    def _validate_plan_structure(self, plan: Dict[str, Any]) -> List[ValidationError]:
        """Validate overall plan structure."""
        errors = []
        
        required_fields = ["program_id", "version", "steps", "step_count"]
        for field in required_fields:
            if field not in plan:
                errors.append(ValidationError(
                    step_seq=None,
                    error_type="missing_field",
                    message=f"Plan missing required field: {field}",
                    severity="error"
                ))
        
        # Validate step count matches actual steps
        if "steps" in plan and "step_count" in plan:
            actual_count = len(plan["steps"])
            declared_count = plan["step_count"]
            if actual_count != declared_count:
                errors.append(ValidationError(
                    step_seq=None,
                    error_type="count_mismatch",
                    message=f"Step count mismatch: declared {declared_count}, actual {actual_count}",
                    severity="error"
                ))
        
        return errors
    
    def _validate_step(self, step_data: Dict[str, Any]) -> List[ValidationError]:
        """Validate a single program step."""
        errors = []
        
        step_seq = step_data.get("seq", "unknown")
        function_id = step_data.get("function_id")
        
        # Check function exists
        if not function_id:
            errors.append(ValidationError(
                step_seq=step_seq,
                error_type="missing_function",
                message="Step missing function_id",
                severity="error"
            ))
            return errors
        
        if function_id not in self.available_functions:
            errors.append(ValidationError(
                step_seq=step_seq,
                error_type="unknown_function",
                message=f"Unknown function: {function_id}",
                severity="error",
                context={"function_id": function_id}
            ))
            return errors
        
        # Validate function parameters
        function_def = self.available_functions[function_id]
        step_params = step_data.get("params", {})
        errors.extend(self._validate_function_parameters(step_seq, function_def, step_params))
        
        # Validate step structure
        required_step_fields = ["seq", "source_step_id", "group_id", "function_id"]
        for field in required_step_fields:
            if field not in step_data:
                errors.append(ValidationError(
                    step_seq=step_seq,
                    error_type="missing_step_field",
                    message=f"Step missing required field: {field}",
                    severity="error"
                ))
        
        return errors
    
    def _validate_function_parameters(self, step_seq: int, function_def: Dict[str, Any], 
                                    step_params: Dict[str, Any]) -> List[ValidationError]:
        """Validate function parameters against function definition."""
        errors = []
        
        func_params = function_def.get("parameters", {})
        
        # Check required parameters
        for param_name, param_def in func_params.items():
            if param_def.get("required", False) and param_name not in step_params:
                # Skip if parameter is a template placeholder
                if not any(isinstance(v, str) and "{{" in str(v) for v in step_params.values()):
                    errors.append(ValidationError(
                        step_seq=step_seq,
                        error_type="missing_parameter",
                        message=f"Missing required parameter: {param_name}",
                        severity="error",
                        context={"parameter": param_name, "function": function_def["function_id"]}
                    ))
        
        # Validate parameter types and constraints
        for param_name, param_value in step_params.items():
            if param_name in func_params:
                param_def = func_params[param_name]
                param_errors = self._validate_parameter_value(
                    step_seq, param_name, param_value, param_def, function_def["function_id"]
                )
                errors.extend(param_errors)
        
        return errors
    
    def _validate_parameter_value(self, step_seq: int, param_name: str, param_value: Any,
                                param_def: Dict[str, Any], function_id: str) -> List[ValidationError]:
        """Validate a single parameter value."""
        errors = []
        
        # Skip validation for template placeholders
        if isinstance(param_value, str) and param_value.startswith("{{") and param_value.endswith("}}"):
            return errors
        
        param_type = param_def.get("type", "string")
        validation_rules = param_def.get("validation", {})
        
        # Type validation
        if param_type == "number" and not isinstance(param_value, (int, float)):
            try:
                float(param_value)
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    step_seq=step_seq,
                    error_type="invalid_type",
                    message=f"Parameter {param_name} must be a number, got {type(param_value).__name__}",
                    severity="error",
                    context={"parameter": param_name, "function": function_id}
                ))
        
        elif param_type == "string" and not isinstance(param_value, str):
            errors.append(ValidationError(
                step_seq=step_seq,
                error_type="invalid_type",
                message=f"Parameter {param_name} must be a string, got {type(param_value).__name__}",
                severity="error",
                context={"parameter": param_name, "function": function_id}
            ))
        
        # Range validation for numbers
        if param_type == "number" and isinstance(param_value, (int, float)):
            if "minimum" in validation_rules:
                min_val = validation_rules["minimum"]
                exclusive = validation_rules.get("exclusiveMinimum", False)
                if (exclusive and param_value <= min_val) or (not exclusive and param_value < min_val):
                    op = ">" if exclusive else ">="
                    errors.append(ValidationError(
                        step_seq=step_seq,
                        error_type="value_out_of_range",
                        message=f"Parameter {param_name} must be {op} {min_val}, got {param_value}",
                        severity="error",
                        context={"parameter": param_name, "function": function_id}
                    ))
            
            if "maximum" in validation_rules:
                max_val = validation_rules["maximum"]
                exclusive = validation_rules.get("exclusiveMaximum", False)
                if (exclusive and param_value >= max_val) or (not exclusive and param_value > max_val):
                    op = "<" if exclusive else "<="
                    errors.append(ValidationError(
                        step_seq=step_seq,
                        error_type="value_out_of_range",
                        message=f"Parameter {param_name} must be {op} {max_val}, got {param_value}",
                        severity="error",
                        context={"parameter": param_name, "function": function_id}
                    ))
        
        return errors
    
    def _validate_step_sequence(self, steps: List[Dict[str, Any]]) -> List[ValidationError]:
        """Validate step sequence and numbering."""
        errors = []
        
        if not steps:
            return errors
        
        # Check sequential numbering
        for i, step in enumerate(steps):
            expected_seq = i + 1
            actual_seq = step.get("seq")
            
            if actual_seq != expected_seq:
                errors.append(ValidationError(
                    step_seq=actual_seq,
                    error_type="sequence_error",
                    message=f"Step sequence mismatch: expected {expected_seq}, got {actual_seq}",
                    severity="warning"
                ))
        
        return errors
    
    def _validate_parameter_consistency(self, steps: List[Dict[str, Any]]) -> List[ValidationError]:
        """Validate parameter consistency across steps."""
        errors = []
        
        # Check for common parameter naming issues
        param_variations = {}
        
        for step in steps:
            params = step.get("params", {})
            for param_name in params.keys():
                # Group similar parameter names
                base_name = param_name.lower().replace("_", "").replace("time", "").replace("vol", "")
                if base_name not in param_variations:
                    param_variations[base_name] = []
                param_variations[base_name].append((step.get("seq"), param_name))
        
        # Report potential inconsistencies
        for base_name, variations in param_variations.items():
            unique_names = set(name for _, name in variations)
            if len(unique_names) > 1:
                step_seq = variations[0][0]  # Report on first occurrence
                errors.append(ValidationError(
                    step_seq=step_seq,
                    error_type="parameter_inconsistency",
                    message=f"Inconsistent parameter naming for '{base_name}': {sorted(unique_names)}",
                    severity="warning",
                    context={"variations": list(unique_names)}
                ))
        
        return errors


class PreflightChecker:
    """Performs preflight checks on program plans before execution."""
    
    def __init__(self):
        self.logger = logging.getLogger("preflight_checker")
    
    def check(self, plan: Dict[str, Any], device_manager=None) -> List[ValidationError]:
        """
        Perform preflight checks on a program plan.
        Returns list of potential issues.
        """
        errors = []
        steps = plan.get("steps", [])
        
        # Resource utilization checks
        errors.extend(self._check_resource_usage(steps))
        
        # Device availability checks (if device_manager provided)
        if device_manager:
            errors.extend(self._check_device_availability(steps, device_manager))
        
        # Safety checks
        errors.extend(self._check_safety_constraints(steps))
        
        # Performance warnings
        errors.extend(self._check_performance_issues(steps))
        
        return errors
    
    def _check_resource_usage(self, steps: List[Dict[str, Any]]) -> List[ValidationError]:
        """Check resource usage patterns."""
        errors = []
        
        # Count reagent usage
        reagent_usage = {}
        total_volume = 0.0
        
        for step in steps:
            params = step.get("params", {})
            
            # Track reagent volumes
            if "reagent_name" in params and "volume_ml" in params:
                reagent = params["reagent_name"]
                try:
                    volume = float(params["volume_ml"])
                    reagent_usage[reagent] = reagent_usage.get(reagent, 0) + volume
                    total_volume += volume
                except (ValueError, TypeError):
                    pass
        
        # Warn about high volume usage
        if total_volume > 100.0:  # Example threshold
            errors.append(ValidationError(
                step_seq=None,
                error_type="high_volume_usage",
                message=f"Program uses {total_volume:.1f} mL total volume",
                severity="warning",
                context={"total_volume": total_volume}
            ))
        
        # Report reagent usage
        for reagent, volume in reagent_usage.items():
            if volume > 50.0:  # Example threshold per reagent
                errors.append(ValidationError(
                    step_seq=None,
                    error_type="high_reagent_usage",
                    message=f"High usage of {reagent}: {volume:.1f} mL",
                    severity="info",
                    context={"reagent": reagent, "volume": volume}
                ))
        
        return errors
    
    def _check_device_availability(self, steps: List[Dict[str, Any]], device_manager) -> List[ValidationError]:
        """Check if required devices are available."""
        errors = []
        
        # This would integrate with the actual device manager
        # For now, provide a placeholder implementation
        
        required_devices = set()
        for step in steps:
            function_id = step.get("function_id")
            
            # Map functions to required devices (simplified)
            if function_id == "transfer_reagent":
                required_devices.update(["vici_valve", "masterflex_pump"])
            elif function_id == "drain_reactor":
                required_devices.add("solenoid_valve")
        
        for device_id in required_devices:
            if hasattr(device_manager, 'has_device'):
                if not device_manager.has_device(device_id):
                    errors.append(ValidationError(
                        step_seq=None,
                        error_type="missing_device",
                        message=f"Required device not available: {device_id}",
                        severity="error",
                        context={"device": device_id}
                    ))
        
        return errors
    
    def _check_safety_constraints(self, steps: List[Dict[str, Any]]) -> List[ValidationError]:
        """Check safety constraints and patterns."""
        errors = []
        
        # Check for potentially unsafe sequences
        for i, step in enumerate(steps):
            function_id = step.get("function_id")
            
            # Example: Warn if transfer without subsequent drain
            if function_id == "transfer_reagent" and i < len(steps) - 1:
                next_functions = [s.get("function_id") for s in steps[i+1:i+5]]  # Look ahead 5 steps
                if "drain_reactor" not in next_functions:
                    errors.append(ValidationError(
                        step_seq=step.get("seq"),
                        error_type="safety_warning",
                        message="Transfer without subsequent drain detected",
                        severity="warning",
                        context={"step_function": function_id}
                    ))
        
        return errors
    
    def _check_performance_issues(self, steps: List[Dict[str, Any]]) -> List[ValidationError]:
        """Check for potential performance issues."""
        errors = []
        
        # Check for excessive step count
        if len(steps) > 1000:
            errors.append(ValidationError(
                step_seq=None,
                error_type="performance_warning",
                message=f"Program has {len(steps)} steps, which may impact performance",
                severity="warning",
                context={"step_count": len(steps)}
            ))
        
        # Check for very long estimated duration
        estimated_duration = 0.0
        for step in steps:
            params = step.get("params", {})
            # Simple estimation based on common time parameters
            for param_name, param_value in params.items():
                if "time" in param_name.lower() and isinstance(param_value, (int, float)):
                    estimated_duration += param_value
        
        if estimated_duration > 480:  # 8 hours
            errors.append(ValidationError(
                step_seq=None,
                error_type="long_duration",
                message=f"Estimated duration: {estimated_duration:.1f} minutes ({estimated_duration/60:.1f} hours)",
                severity="warning",
                context={"duration_minutes": estimated_duration}
            ))
        
        return errors


def format_validation_errors(errors: List[ValidationError]) -> str:
    """Format validation errors for display."""
    if not errors:
        return "✓ No validation errors found"
    
    lines = []
    error_count = sum(1 for e in errors if e.severity == "error")
    warning_count = sum(1 for e in errors if e.severity == "warning")
    info_count = sum(1 for e in errors if e.severity == "info")
    
    lines.append(f"Validation Results: {error_count} errors, {warning_count} warnings, {info_count} info")
    lines.append("-" * 60)
    
    for error in errors:
        icon = "❌" if error.severity == "error" else "⚠️" if error.severity == "warning" else "ℹ️"
        step_info = f"Step {error.step_seq}: " if error.step_seq else ""
        lines.append(f"{icon} {step_info}{error.message}")
    
    return "\n".join(lines)