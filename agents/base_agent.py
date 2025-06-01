# agents/base_agent.py
from abc import ABC, abstractmethod
from typing import Dict, Any
from shared_memory import SharedMemory

class BaseAgent(ABC):
    def __init__(self, memory: SharedMemory):
        self.memory = memory
        self.agent_name = self.__class__.__name__

    @abstractmethod
    def process_input(self, input_content: Any) -> Dict[str, Any]:
        """
        Processes the input content specific to the agent's function.
        Returns a dictionary containing extracted_data, decision_trace, and potential chained_action.
        """
        pass

    def _log_decision_trace(self, trace_message: str) -> str:
        """Helper to log decision traces."""
        return f"[{self.agent_name}] {trace_message}"