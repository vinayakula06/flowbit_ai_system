# agents/action_router.py
# REMOVE: from agents.base_agent import BaseAgent # This line should NOT be here
from shared_memory import SharedMemory
from typing import Dict, Any, Optional
import httpx # For simulating API calls
import json # Ensure json is imported for json.dumps (used in simulate functions for clarity)

# NEW IMPORTS FOR RETRY LOGIC
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

class ActionRouter: # <--- REMOVED INHERITANCE FROM BaseAgent
    def __init__(self, memory: SharedMemory):
        self.memory = memory # Directly set memory
        self.agent_name = self.__class__.__name__ # Define agent_name

    def _log_decision_trace(self, trace_message: str) -> str:
        """Helper to log decision traces."""
        return f"[{self.agent_name}] {trace_message}"

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=5), # Wait 1s, 2s, 4s... up to 5s
        stop=stop_after_attempt(3), # Retry 3 times
        # Retry only on specific network/connection errors, not on HTTP status errors initially
        retry=retry_if_exception_type(httpx.NetworkError) |
              retry_if_exception_type(httpx.TimeoutException) |
              retry_if_exception_type(httpx.ConnectError) |
              retry_if_exception_type(httpx.ConnectTimeout),
        # You could add retry_if_exception_type(httpx.HTTPStatusError) and then
        # use a custom before_sleep callback to check if it's a 5xx error.
    )
    async def _simulate_crm_escalate(self, data: Dict[str, Any]) -> str:
        """Simulates calling a CRM escalation API."""
        try:
            # In a real scenario, this would be an actual HTTP POST to a CRM system.
            # For demonstration, we'll just return a success message with data logged.
            # async with httpx.AsyncClient() as client:
            #     response = await client.post("https://api.example.com/crm/escalate", json=data, timeout=5)
            #     response.raise_for_status() # This raises httpx.HTTPStatusError for 4xx/5xx
            #     return f"CRM escalation successful: {response.status_code}"

            # For demo, just return success message. If you want to test retry,
            # you can temporarily add `raise httpx.NetworkError("Simulated network issue")` here.
            return f"CRM escalation simulated: {json.dumps(data)}"
        except httpx.RequestError as e: # This is caught by tenacity's retry_if_exception_type
            self._log_decision_trace(f"Simulated CRM escalation failed (retrying on network/timeout): {e}")
            raise e # Re-raise to trigger retry by tenacity
        except httpx.HTTPStatusError as e:
            # Do NOT retry on all HTTP status errors, only specific ones if desired (e.g., 5xx).
            # We catch it here and return failure message rather than re-raising for retry.
            return f"CRM escalation failed (HTTP error {e.response.status_code}): {e.response.text}"
        except Exception as e:
            return f"CRM escalation failed (unexpected error): {e}"

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(httpx.NetworkError) |
              retry_if_exception_type(httpx.TimeoutException) |
              retry_if_exception_type(httpx.ConnectError) |
              retry_if_exception_type(httpx.ConnectTimeout),
    )
    async def _simulate_risk_alert(self, data: Dict[str, Any]) -> str:
        """Simulates calling a risk alert system API."""
        try:
            # In a real scenario, this would be an actual HTTP POST to a risk alert system.
            # For demonstration, we'll just return a success message with the data logged.
            # async with httpx.AsyncClient() as client:
            #     response = await client.post("https://api.example.com/risk_alert", json=data, timeout=5)
            #     response.raise_for_status()
            #     return f"Risk alert triggered successfully: {response.status_code}"
            return f"Risk alert simulated: {json.dumps(data)}"
        except httpx.RequestError as e:
            self._log_decision_trace(f"Simulated Risk Alert failed (retrying on network/timeout): {e}")
            raise e
        except httpx.HTTPStatusError as e:
            return f"Risk alert failed (HTTP error {e.response.status_code}): {e.response.text}"
        except Exception as e:
            return f"Risk alert failed (unexpected error): {e}"

    async def _simulate_log_and_close(self, data: Dict[str, Any]) -> str:
        """Simulates logging the interaction and closing it."""
        # This is an internal operation, typically doesn't need retry logic.
        return f"Interaction logged and closed (routine): {json.dumps(data)}"

    async def trigger_final_action(self, intent: str, action_trigger_data: Dict[str, Any]) -> str:
        """
        Triggers the final follow-up action based on agent outputs and intent.
        Prioritizes specialized agent's explicit 'chained_action' if available and valid.
        """
        trace = self._log_decision_trace(f"Determining final action for intent: {intent} with data: {action_trigger_data}")
        final_action_status = "No action triggered"

        # --- Strategy 1: Prioritize explicit 'chained_action' from the specialized agent ---
        # The specialized agent (EmailAgent, JSONAgent, PDF Agent) might explicitly recommend an action
        specialized_agent_recommended_action = action_trigger_data.get("chained_action")

        if specialized_agent_recommended_action == "Escalate to CRM":
            trace += self._log_decision_trace("Specialized agent recommended 'Escalate to CRM'. Executing.")
            final_action_status = await self._simulate_crm_escalate(
                {"type": "Specialized Agent Escalation (CRM)", "details": action_trigger_data}
            )
        elif specialized_agent_recommended_action == "Flag Risk and Escalate":
            trace += self._log_decision_trace("Specialized agent recommended 'Flag Risk and Escalate'. Executing.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "Specialized Agent Risk Flag (Escalate)", "details": action_trigger_data}
            )
        elif specialized_agent_recommended_action == "Log Anomaly":
            trace += self._log_decision_trace("Specialized agent recommended 'Log Anomaly'. Executing.")
            final_action_status = await self._simulate_log_and_close( # Log anomaly can be considered a 'log and close' with specific details
                {"type": "Anomaly Logged", "details": action_trigger_data}
            )
        elif specialized_agent_recommended_action == "Flag High Value Invoice":
            trace += self._log_decision_trace("Specialized agent recommended 'Flag High Value Invoice'. Executing.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "High Value Invoice Alert", "details": action_trigger_data}
            )
        elif specialized_agent_recommended_action == "Flag Compliance Risk":
            trace += self._log_decision_trace("Specialized agent recommended 'Flag Compliance Risk'. Executing.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "Compliance Risk Flagged", "details": action_trigger_data}
            )
        elif specialized_agent_recommended_action in ["Log and Close", "Process JSON Data", "Process Invoice", "Process Policy Document", "Review PDF Manually"]:
            trace += self._log_decision_trace(f"Specialized agent recommended routine processing/review ('{specialized_agent_recommended_action}'). Executing log and close.")
            final_action_status = await self._simulate_log_and_close(
                {"type": f"Routine Processed ({specialized_agent_recommended_action})", "details": action_trigger_data}
            )
        # --- Strategy 2: Fallback to Classifier Intent-based routing if no explicit action from specialized agent ---
        # This block will only be hit if specialized_agent_recommended_action was None or not handled above
        elif intent == "Complaint" and action_trigger_data.get("urgency") in ["High", "Critical"]:
            trace += self._log_decision_trace("Classifier intent 'Complaint' and high urgency detected. Executing CRM escalation.")
            final_action_status = await self._simulate_crm_escalate(
                {"type": "Classifier-driven Complaint Escalation", "details": action_trigger_data}
            )
        elif intent == "Fraud Risk" and action_trigger_data.get("risk_level") == "High":
            trace += self._log_decision_trace("Classifier intent 'Fraud Risk' and high risk level detected. Executing risk alert.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "Classifier-driven Fraud Risk Detected", "details": action_trigger_data}
            )
        elif intent == "Invoice" and action_trigger_data.get("invoice_total", 0) > 10000:
            trace += self._log_decision_trace("Classifier intent 'Invoice' and high total amount detected. Executing risk alert.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "Classifier-driven High Value Invoice Alert", "details": action_trigger_data}
            )
        elif intent == "Regulation" and action_trigger_data.get("compliance_keywords"):
            trace += self._log_decision_trace("Classifier intent 'Regulation' and compliance keywords detected. Executing risk alert.")
            final_action_status = await self._simulate_risk_alert(
                {"type": "Classifier-driven Compliance Risk Flagged", "details": action_trigger_data}
            )
        # --- Default Fallback ---
        else:
            trace += self._log_decision_trace("No specific action triggered by specialized agent or classifier intent. Defaulting to log and close.")
            final_action_status = await self._simulate_log_and_close(
                {"type": "Routine Processing (Default)", "details": action_trigger_data}
            )

        trace += self._log_decision_trace(f"Final action result: {final_action_status}")
        return final_action_status