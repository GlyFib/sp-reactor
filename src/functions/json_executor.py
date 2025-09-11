import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union
import re


class FunctionExecutor:
    """Loads and executes functions defined in JSON format."""
    
    def __init__(self, definitions_dir: Union[str, Path], schema_path: Union[str, Path]):
        self.definitions_dir = Path(definitions_dir)
        self.schema_path = Path(schema_path)
        self.functions = {}
        self.schema = None
        self.logger = logging.getLogger("function_executor")
        
        # Load schema
        self._load_schema()
        
        # Load all function definitions
        self._load_functions()
    
    def _load_schema(self):
        """Load JSON schema for validation."""
        try:
            with open(self.schema_path) as f:
                self.schema = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Failed to load schema from {self.schema_path}: {e}")
    
    def _load_functions(self):
        """Load all function definitions from atomic and composite directories."""
        atomic_dir = self.definitions_dir / "atomic"
        composite_dir = self.definitions_dir / "composite"
        
        # Load atomic functions
        if atomic_dir.exists():
            for json_file in atomic_dir.glob("*.json"):
                self._load_function_file(json_file)
        
        # Load composite functions
        if composite_dir.exists():
            for json_file in composite_dir.glob("*.json"):
                self._load_function_file(json_file)
        
        self.logger.info(f"Loaded {len(self.functions)} functions")
    
    def _load_function_file(self, json_file: Path):
        """Load a single function definition file."""
        try:
            with open(json_file) as f:
                function_def = json.load(f)
            
            # Basic validation (replace with jsonschema when available)
            required_fields = ["function_id", "type", "version"]
            for field in required_fields:
                if field not in function_def:
                    raise ValueError(f"Missing required field: {field}")
            
            function_id = function_def["function_id"]
            
            # Check for duplicate function IDs
            if function_id in self.functions:
                raise ValueError(f"Duplicate function ID: {function_id}")
            
            self.functions[function_id] = function_def
            self.logger.debug(f"Loaded function: {function_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to load function from {json_file}: {e}")
            raise
    
    def get_function(self, function_id: str) -> Optional[Dict[str, Any]]:
        """Get function definition by ID."""
        return self.functions.get(function_id)
    
    def list_functions(self) -> Dict[str, str]:
        """Get list of available functions with their descriptions."""
        return {
            func_id: func_def.get("description", "No description")
            for func_id, func_def in self.functions.items()
        }
    
    def validate_parameters(self, function_id: str, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate parameters for a function."""
        function_def = self.get_function(function_id)
        if not function_def:
            return False, f"Function not found: {function_id}"
        
        parameters = function_def.get("parameters", {})
        
        # Check required parameters
        for param_name, param_def in parameters.items():
            if param_def.get("required", False) and param_name not in kwargs:
                return False, f"Missing required parameter: {param_name}"
        
        # Validate parameter values
        for param_name, value in kwargs.items():
            if param_name not in parameters:
                continue  # Extra parameters are allowed for now
            
            param_def = parameters[param_name]
            validation_result = self._validate_parameter_value(param_name, value, param_def)
            if not validation_result[0]:
                return False, validation_result[1]
        
        return True, None
    
    def _validate_parameter_value(self, param_name: str, value: Any, param_def: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate a single parameter value."""
        param_type = param_def["type"]
        
        # Type checking
        if param_type == "string" and not isinstance(value, str):
            return False, f"Parameter {param_name} must be a string"
        elif param_type == "number" and not isinstance(value, (int, float)):
            return False, f"Parameter {param_name} must be a number"
        elif param_type == "boolean" and not isinstance(value, bool):
            return False, f"Parameter {param_name} must be a boolean"
        
        # Validation rules
        validation = param_def.get("validation", {})
        
        if param_type == "number":
            if "minimum" in validation:
                min_val = validation["minimum"]
                exclusive = validation.get("exclusiveMinimum", False)
                if exclusive and value <= min_val:
                    return False, f"Parameter {param_name} must be > {min_val}"
                elif not exclusive and value < min_val:
                    return False, f"Parameter {param_name} must be >= {min_val}"
            
            if "maximum" in validation:
                max_val = validation["maximum"]
                exclusive = validation.get("exclusiveMaximum", False)
                if exclusive and value >= max_val:
                    return False, f"Parameter {param_name} must be < {max_val}"
                elif not exclusive and value > max_val:
                    return False, f"Parameter {param_name} must be <= {max_val}"
        
        elif param_type == "string":
            if "minLength" in validation and len(value) < validation["minLength"]:
                return False, f"Parameter {param_name} must be at least {validation['minLength']} characters"
            if "maxLength" in validation and len(value) > validation["maxLength"]:
                return False, f"Parameter {param_name} must be at most {validation['maxLength']} characters"
            if "pattern" in validation and not re.match(validation["pattern"], value):
                return False, f"Parameter {param_name} does not match required pattern"
        
        if "enum" in validation and value not in validation["enum"]:
            return False, f"Parameter {param_name} must be one of: {validation['enum']}"
        
        return True, None
    
    def execute_function(self, function_id: str, device_manager, **kwargs) -> tuple[bool, Optional[str]]:
        """Execute a function with given parameters."""
        function_def = self.get_function(function_id)
        if not function_def:
            return False, f"Function not found: {function_id}"
        
        # Apply default parameters
        parameters = function_def.get("parameters", {})
        for param_name, param_def in parameters.items():
            if param_name not in kwargs and "default" in param_def:
                kwargs[param_name] = param_def["default"]
        
        # Validate parameters
        valid, error = self.validate_parameters(function_id, **kwargs)
        if not valid:
            return False, error
        
        # Check required devices
        required_devices = function_def.get("required_devices", [])
        for device_id in required_devices:
            if not device_manager.has_device(device_id):
                return False, f"Required device not available: {device_id}"
        
        self.logger.info(f"Executing function: {function_id}")
        
        # Execute based on function type
        if function_def["type"] == "atomic":
            return self._execute_atomic(function_def, device_manager, **kwargs)
        elif function_def["type"] == "composite":
            return self._execute_composite(function_def, device_manager, **kwargs)
        else:
            return False, f"Unknown function type: {function_def['type']}"
    
    def _execute_atomic(self, function_def: Dict[str, Any], device_manager, **kwargs) -> tuple[bool, Optional[str]]:
        """Execute an atomic function."""
        operations = function_def.get("operations", [])
        
        for operation in operations:
            device_id = operation["device"]
            action = operation["action"]
            args = operation.get("args", [])
            on_error = operation.get("on_error", "return_false")
            
            try:
                # Handle special case for timer device
                if device_id == "timer":
                    if action == "wait":
                        import time
                        wait_time = kwargs.get(args[0], float(args[0])) if args else 1.0
                        # Convert minutes to seconds if parameter name suggests minutes
                        if args and "minute" in args[0]:
                            wait_time *= 60
                        time.sleep(wait_time)
                        continue
                
                # Get device
                device = device_manager.get_device(device_id)
                if not device:
                    error_msg = f"Device not found: {device_id}"
                    if on_error == "return_false":
                        return False, error_msg
                    elif on_error == "raise":
                        raise RuntimeError(error_msg)
                    # Continue on error
                    continue
                
                # Get method
                method = getattr(device, action, None)
                if not method:
                    error_msg = f"Method {action} not found on device {device_id}"
                    if on_error == "return_false":
                        return False, error_msg
                    elif on_error == "raise":
                        raise RuntimeError(error_msg)
                    continue
                
                # Prepare arguments
                method_args = []
                for arg_name in args:
                    if arg_name in kwargs:
                        method_args.append(kwargs[arg_name])
                    else:
                        # Try to parse as literal value
                        try:
                            method_args.append(float(arg_name))
                        except ValueError:
                            method_args.append(arg_name)
                
                # Execute method
                result = method(*method_args)
                
                # Check result (assume False means failure)
                if result is False:
                    error_msg = f"Operation failed: {device_id}.{action}"
                    if on_error == "return_false":
                        return False, error_msg
                    elif on_error == "raise":
                        raise RuntimeError(error_msg)
                
            except Exception as e:
                error_msg = f"Operation error: {device_id}.{action} - {str(e)}"
                if on_error == "return_false":
                    return False, error_msg
                elif on_error == "raise":
                    raise
                # Continue on error
                self.logger.warning(error_msg)
        
        return True, None
    
    def _execute_composite(self, function_def: Dict[str, Any], device_manager, **kwargs) -> tuple[bool, Optional[str]]:
        """Execute a composite function."""
        function_sequence = function_def.get("function_sequence", [])
        
        for step in function_sequence:
            step_function_id = step["function"]
            step_parameters = step.get("parameters", {})
            on_error = step.get("on_error", "return_false")
            
            # Resolve parameter templates
            resolved_params = {}
            for param_name, param_value in step_parameters.items():
                if isinstance(param_value, str) and param_value.startswith("{{") and param_value.endswith("}}"):
                    # Template parameter
                    template_var = param_value[2:-2].strip()
                    if template_var in kwargs:
                        resolved_params[param_name] = kwargs[template_var]
                    else:
                        error_msg = f"Template variable not found: {template_var}"
                        if on_error == "return_false":
                            return False, error_msg
                        elif on_error == "raise":
                            raise ValueError(error_msg)
                else:
                    resolved_params[param_name] = param_value
            
            # Execute sub-function
            try:
                success, error = self.execute_function(step_function_id, device_manager, **resolved_params)
                if not success:
                    if on_error == "return_false":
                        return False, f"Step {step_function_id} failed: {error}"
                    elif on_error == "raise":
                        raise RuntimeError(f"Step {step_function_id} failed: {error}")
                    # Continue on error
                    self.logger.warning(f"Step {step_function_id} failed: {error}")
            except Exception as e:
                error_msg = f"Step {step_function_id} error: {str(e)}"
                if on_error == "return_false":
                    return False, error_msg
                elif on_error == "raise":
                    raise
                # Continue on error
                self.logger.warning(error_msg)
        
        return True, None


# Compatibility layer - provides the same interface as the original atomic_functions.py
def get_function(function_id: str) -> Optional[Dict[str, Any]]:
    """Get function definition by ID - compatibility function."""
    global _executor
    if '_executor' not in globals():
        # Initialize with default paths
        definitions_dir = Path(__file__).parent / "definitions"
        schema_path = Path(__file__).parent / "schemas" / "function_schema.json"
        _executor = FunctionExecutor(definitions_dir, schema_path)
    
    return _executor.get_function(function_id)


def execute_function(function_id: str, device_manager, **kwargs) -> tuple[bool, Optional[str]]:
    """Execute function by ID - compatibility function."""
    global _executor
    if '_executor' not in globals():
        # Initialize with default paths
        definitions_dir = Path(__file__).parent / "definitions"
        schema_path = Path(__file__).parent / "schemas" / "function_schema.json"
        _executor = FunctionExecutor(definitions_dir, schema_path)
    
    return _executor.execute_function(function_id, device_manager, **kwargs)