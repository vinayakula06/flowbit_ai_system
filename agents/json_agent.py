# agents/json_agent.py
from agents.base_agent import BaseAgent
from shared_memory import SharedMemory
from typing import Dict, Any, List
import json
from faker import Faker

class JSONAgent(BaseAgent):
    def __init__(self, memory: SharedMemory):
        super().__init__(memory)
        self.fake = Faker()

        self.required_schemas = {
            "RFQ": {
                "request_id": str,
                "items": list,
                "due_date": str,
                "contact_email": str
            },
            "Fraud Risk": {
                "transaction_id": str,
                "amount": (int, float),
                "user_id": str,
                "risk_score": (int, float),
                "ip_address": str
            },
            "Invoice": {
                "invoice_number": str,
                "customer_id": str,
                "total_amount": (int, float),
                "currency": str,
                "line_items": list
            }
            # Add more schemas as needed for other intents if they map to JSON
        }

    def _validate_json_schema(self, data: Dict[str, Any], intent: str) -> List[str]:
        """Validates JSON data against a predefined schema for the given intent."""
        errors = []
        schema = self.required_schemas.get(intent)

        if not schema:
            errors.append(f"No schema defined for intent: {intent}")
            return errors

        for field, expected_type in schema.items():
            if field not in data:
                errors.append(f"Missing required field: '{field}'")
            elif not isinstance(data[field], expected_type):
                # Handle cases where expected_type is a tuple of types (e.g., int or float)
                if isinstance(expected_type, tuple):
                    if not any(isinstance(data[field], t) for t in expected_type):
                        errors.append(f"Field '{field}' has wrong type. Expected one of {expected_type}, got {type(data[field])}")
                else:
                    errors.append(f"Field '{field}' has wrong type. Expected {expected_type}, got {type(data[field])}")

        return errors

    def _generate_sample_webhook_data(self, intent: str) -> Dict[str, Any]:
        """Simulates incoming webhook data based on intent."""
        if intent == "Fraud Risk":
            return {
                "transaction_id": self.fake.uuid4(),
                "amount": round(self.fake.random_number(digits=5) + self.fake.pyfloat(left_digits=2, right_digits=2, positive=True), 2),
                "user_id": self.fake.uuid4(),
                "risk_score": round(self.fake.pyfloat(left_digits=0, right_digits=2, positive=True, max_value=1.0), 2),
                "ip_address": self.fake.ipv4()
            }
        elif intent == "RFQ":
            return {
                "request_id": self.fake.uuid4(),
                "items": [
                    {"item_name": self.fake.word(), "quantity": self.fake.random_int(min=1, max=100)},
                    {"item_name": self.fake.word(), "quantity": self.fake.random_int(min=1, max=100)}
                ],
                "due_date": self.fake.date_this_month().isoformat(),
                "contact_email": self.fake.email()
            }
        elif intent == "Invoice":
            return {
                "invoice_number": self.fake.unique.random_int(min=10000, max=99999),
                "customer_id": self.fake.uuid4(),
                "total_amount": round(self.fake.random_number(digits=5) + self.fake.pyfloat(left_digits=2, right_digits=2, positive=True), 2),
                "currency": self.fake.currency_code(),
                "line_items": [
                    {"description": self.fake.sentence(nb_words=3), "quantity": self.fake.random_int(1,5), "unit_price": round(self.fake.pyfloat(left_digits=2, right_digits=2, positive=True),2)},
                    {"description": self.fake.sentence(nb_words=3), "quantity": self.fake.random_int(1,5), "unit_price": round(self.fake.pyfloat(left_digits=2, right_digits=2, positive=True),2)}
                ]
            }
        return {} # Return empty if no specific sample for intent

    def process_input(self, input_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parses webhook data, validates schema, and flags anomalies.
        """
        trace = self._log_decision_trace("Starting JSON processing...")
        extracted_data = input_content

        # Retrieve intent from shared memory
        latest_interaction = self.memory.read_latest_interaction()
        classification_intent = latest_interaction.get("classification", {}).get("intent")

        if not classification_intent:
            trace += self._log_decision_trace("Could not retrieve intent from shared memory. Cannot validate schema.")
            return {"extracted_data": extracted_data, "decision_trace": trace, "chained_action": "Log Anomaly"}

        validation_errors = self._validate_json_schema(extracted_data, classification_intent)
        chained_action = None

        action_trigger_data = {
            "intent": classification_intent,
            "json_data": extracted_data,
            "validation_errors": validation_errors
        }

        if validation_errors:
            trace += self._log_decision_trace(f"JSON validation errors detected: {validation_errors}")
            chained_action = "Log Anomaly"
            # Simulate logging alert in memory/API
            # self.memory.log_alert({"type": "JSON_Schema_Mismatch", "errors": validation_errors, "data": extracted_data})
        else:
            trace += self._log_decision_trace("JSON schema validated successfully.")
            chained_action = "Process JSON Data" # Or a more specific action

            # Example of flagging specific anomalies within valid JSON data
            if classification_intent == "Fraud Risk" and extracted_data.get("risk_score", 0) > 0.8:
                trace += self._log_decision_trace("High fraud risk score detected.")
                chained_action = "Flag Fraud Risk"
                action_trigger_data["risk_level"] = "High"


        # Store in memory (simplified)
        return {
            "extracted_data": extracted_data,
            "decision_trace": trace,
            "chained_action": chained_action,
            "action_trigger_data": action_trigger_data
        }