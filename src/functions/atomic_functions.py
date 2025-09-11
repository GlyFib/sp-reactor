from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging
import time


class AtomicFunction(ABC):
    """Base class for atomic hardware functions."""
    
    def __init__(self, function_id: str):
        self.function_id = function_id
        self.logger = logging.getLogger(f"function.{function_id}")
        self.last_error = None
        
    @abstractmethod
    def execute(self, device_manager, **kwargs) -> bool:
        """Execute the atomic function with given parameters."""
        pass
    
    @abstractmethod
    def validate_parameters(self, **kwargs) -> bool:
        """Validate function parameters before execution."""
        pass
    
    @abstractmethod
    def get_required_devices(self) -> list:
        """Return list of required device IDs."""
        pass
    
    def get_parameter_info(self) -> Dict[str, Any]:
        """Get information about function parameters."""
        return {}


class TransferReagent(AtomicFunction):
    """Transfer specific volume of reagent from valve position to reactor."""
    
    def __init__(self):
        super().__init__("transfer_reagent")
        
    def get_required_devices(self) -> list:
        return ["vici_valve", "masterflex_pump"]
    
    def validate_parameters(self, **kwargs) -> bool:
        required = ["reagent_name", "volume_ml", "flow_rate"]
        missing = [key for key in required if key not in kwargs]
        
        if missing:
            self.last_error = f"Missing parameters: {missing}"
            return False
            
        if kwargs["volume_ml"] <= 0:
            self.last_error = "Volume must be positive"
            return False
            
        if kwargs["flow_rate"] <= 0:
            self.last_error = "Flow rate must be positive"
            return False
            
        return True
    
    def execute(self, device_manager, **kwargs) -> bool:
        """Transfer reagent to reactor."""
        if not self.validate_parameters(**kwargs):
            return False
            
        try:
            valve = device_manager.get_device("vici_valve")
            pump = device_manager.get_device("masterflex_pump")
            
            reagent = kwargs["reagent_name"]
            volume = kwargs["volume_ml"]
            flow_rate = kwargs["flow_rate"]
            
            self.logger.info(f"Transferring {volume} mL of {reagent} at {flow_rate} mL/min")
            
            # Select reagent position
            if not valve.select_reagent(reagent):
                self.last_error = f"Failed to select reagent: {reagent}"
                return False
                
            # Transfer volume
            if not pump.dispense_volume(volume, flow_rate):
                self.last_error = f"Failed to transfer {volume} mL"
                return False
                
            return True
            
        except Exception as e:
            self.last_error = f"Transfer failed: {str(e)}"
            return False


class DrainReactor(AtomicFunction):
    """Drain reactor contents using vacuum."""
    
    def __init__(self):
        super().__init__("drain_reactor")
        
    def get_required_devices(self) -> list:
        return ["solenoid_valve"]
    
    def validate_parameters(self, **kwargs) -> bool:
        drain_time = kwargs.get("drain_time_seconds", 10.0)
        
        if drain_time <= 0:
            self.last_error = "Drain time must be positive"
            return False
            
        return True
    
    def execute(self, device_manager, **kwargs) -> bool:
        """Drain reactor contents."""
        if not self.validate_parameters(**kwargs):
            return False
            
        try:
            vacuum = device_manager.get_device("solenoid_valve")
            drain_time = kwargs.get("drain_time_seconds", 10.0)
            
            self.logger.info(f"Draining reactor for {drain_time} seconds")
            
            if not vacuum.drain_reactor(drain_time):
                self.last_error = "Reactor drain failed"
                return False
                
            return True
            
        except Exception as e:
            self.last_error = f"Drain failed: {str(e)}"
            return False


class AgitateReactor(AtomicFunction):
    """Agitate reactor contents for specified time."""
    
    def __init__(self):
        super().__init__("agitate_reactor")
        
    def get_required_devices(self) -> list:
        return []  # Agitation might be passive or use separate agitator
    
    def validate_parameters(self, **kwargs) -> bool:
        agitate_time = kwargs.get("agitate_time_minutes", 1.0)
        
        if agitate_time <= 0:
            self.last_error = "Agitation time must be positive"
            return False
            
        return True
    
    def execute(self, device_manager, **kwargs) -> bool:
        """Agitate reactor contents."""
        if not self.validate_parameters(**kwargs):
            return False
            
        try:
            agitate_time = kwargs.get("agitate_time_minutes", 1.0)
            
            self.logger.info(f"Agitating reactor for {agitate_time} minutes")
            
            # For now, implement as wait time
            # In real system, this would control agitator or bubbling
            time.sleep(agitate_time * 60)
            
            return True
            
        except Exception as e:
            self.last_error = f"Agitation failed: {str(e)}"
            return False


class WashReactor(AtomicFunction):
    """Perform single wash cycle with specified solvent."""
    
    def __init__(self):
        super().__init__("wash_reactor")
        
    def get_required_devices(self) -> list:
        return ["vici_valve", "masterflex_pump", "solenoid_valve"]
    
    def validate_parameters(self, **kwargs) -> bool:
        required = ["solvent", "volume_ml"]
        missing = [key for key in required if key not in kwargs]
        
        if missing:
            self.last_error = f"Missing parameters: {missing}"
            return False
            
        if kwargs["volume_ml"] <= 0:
            self.last_error = "Volume must be positive"
            return False
            
        return True
    
    def execute(self, device_manager, **kwargs) -> bool:
        """Perform single wash cycle."""
        if not self.validate_parameters(**kwargs):
            return False
            
        try:
            solvent = kwargs["solvent"]
            volume = kwargs["volume_ml"]
            flow_rate = kwargs.get("flow_rate", 10.0)
            wash_time = kwargs.get("wash_time_minutes", 1.0)
            drain_time = kwargs.get("drain_time_seconds", 5.0)
            
            self.logger.info(f"Washing with {volume} mL of {solvent}")
            
            # Transfer wash solvent
            transfer = TransferReagent()
            if not transfer.execute(device_manager, 
                                  reagent_name=solvent, 
                                  volume_ml=volume, 
                                  flow_rate=flow_rate):
                self.last_error = f"Failed to add wash solvent: {transfer.last_error}"
                return False
            
            # Agitate
            agitate = AgitateReactor()
            if not agitate.execute(device_manager, agitate_time_minutes=wash_time):
                self.last_error = f"Agitation failed: {agitate.last_error}"
                return False
            
            # Drain
            drain = DrainReactor()
            if not drain.execute(device_manager, drain_time_seconds=drain_time):
                self.last_error = f"Drain failed: {drain.last_error}"
                return False
                
            return True
            
        except Exception as e:
            self.last_error = f"Wash failed: {str(e)}"
            return False


class CheckReactorEmpty(AtomicFunction):
    """Check if reactor is empty (future: with sensors)."""
    
    def __init__(self):
        super().__init__("check_reactor_empty")
        
    def get_required_devices(self) -> list:
        return []  # Future: level sensors
    
    def validate_parameters(self, **kwargs) -> bool:
        return True
    
    def execute(self, device_manager, **kwargs) -> bool:
        """Check if reactor is empty."""
        try:
            # For now, assume reactor is empty after drain
            # In real system, would check level sensors
            self.logger.info("Checking reactor empty status")
            
            # Simulate check time
            time.sleep(0.5)
            
            return True
            
        except Exception as e:
            self.last_error = f"Empty check failed: {str(e)}"
            return False


# Function registry
ATOMIC_FUNCTIONS = {
    "transfer_reagent": TransferReagent(),
    "drain_reactor": DrainReactor(),
    "agitate_reactor": AgitateReactor(),
    "wash_reactor": WashReactor(),
    "check_reactor_empty": CheckReactorEmpty()
}


def get_function(function_id: str) -> Optional[AtomicFunction]:
    """Get atomic function by ID."""
    return ATOMIC_FUNCTIONS.get(function_id)