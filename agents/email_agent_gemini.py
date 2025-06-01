# agents/email_agent_gemini.py
from agents.base_agent import BaseAgent
from shared_memory import SharedMemory
from agents.gemini_utils import GeminiAPI # Import the Gemini utility
import email
from email import policy
import re
import json
import os
from typing import Dict, Any

class EmailAgent(BaseAgent):
    def __init__(self, memory: SharedMemory, gemini_api_key: str):
        super().__init__(memory)
        self.gemini_api = GeminiAPI(api_key=gemini_api_key)

        self.email_extraction_schema = {
            "sender": {"type": "string"},
            "subject": {"type": "string"},
            "urgency": {"type": "string", "enum": ["Low", "Medium", "High", "Critical", "Unknown"]},
            "tone": {"type": "string", "enum": ["Polite", "Neutral", "Escalation", "Threatening", "Query", "Unknown"]},
            "issue_request": {"type": "string"},
            "action_needed": {"type": "string"}
        }

        self.prompt_template = """You are an AI Email processing agent.
            Extract structured fields from the following email content.
            Also, identify the tone and urgency of the email.

            Email Content:
            {email_content}

            Extract the following:
            - sender: The sender's email address.
            - subject: The subject of the email.
            - urgency: Classify the urgency (Low, Medium, High, Critical, Unknown).
            - tone: Identify the tone (Polite, Neutral, Escalation, Threatening, Query, Unknown).
            - issue_request: A summary of the main issue or request.
            - action_needed: What specific action is explicitly requested or implied.

            Provide the output in JSON format conforming to the following schema:
            {schema}

            Few-shot Examples:
            Example 1:
            Email: "Subject: Urgent Issue with Order #12345\\nFrom: customer@example.com\\nDear Support, My recent order #12345 arrived damaged. I need a replacement immediately. This is unacceptable."
            Output: {{"sender": "customer@example.com", "subject": "Urgent Issue with Order #12345", "urgency": "Critical", "tone": "Escalation", "issue_request": "Order #12345 arrived damaged, needs replacement.", "action_needed": "Provide replacement for order #12345 immediately."}}

            Example 2:
            Email: "Subject: Query about new policy\\nFrom: user@company.com\\nHi Team, Could you please clarify the new expense policy regarding travel? Thanks."
            Output: {{"sender": "user@company.com", "subject": "Query about new policy", "urgency": "Low", "tone": "Polite", "issue_request": "Clarification on new expense policy for travel.", "action_needed": "Clarify new expense policy."}}

            Your extraction (JSON only):
            """

    def _extract_from_eml_file(self, file_path: str) -> str:
        """Extracts text content from an .eml file."""
        try:
            with open(file_path, 'rb') as fp:
                msg = email.message_from_bytes(fp.read(), policy=policy.default)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))

                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        body += part.get_payload(decode=True).decode(errors='ignore')
                        break
            else:
                body = msg.get_payload(decode=True).decode(errors='ignore')

            sender = msg['From'] if msg['From'] else 'unknown@example.com'
            subject = msg['Subject'] if msg['Subject'] else 'No Subject'
            return f"Subject: {subject}\nFrom: {sender}\n\n{body}"
        except Exception as e:
            return f"Error reading email file: {e}. Raw content might be included below.\n{file_path}"

    async def process_input(self, input_content: Any) -> Dict[str, Any]:
        """
        Processes email content (raw text or file path) and extracts information.
        """
        trace = self._log_decision_trace("Starting email processing...")
        email_text = ""

        if isinstance(input_content, str) and os.path.exists(input_content):
            trace += self._log_decision_trace(f"Processing email from file: {input_content}")
            email_text = self._extract_from_eml_file(input_content)
        elif isinstance(input_content, str):
            trace += self._log_decision_trace("Processing raw email text.")
            email_text = input_content
        else:
            trace += self._log_decision_trace("Invalid input for EmailAgent. Expected string or file path.")
            return {"extracted_data": {}, "decision_trace": trace, "chained_action": None, "action_trigger_data": {}}

        full_prompt = self.prompt_template.format(
            email_content=email_text,
            schema=json.dumps(self.email_extraction_schema, indent=2)
        )

        extracted_data = {}
        chained_action = None
        action_trigger_data = {
            "intent": self.memory.read_latest_interaction().get("classification", {}).get("intent"),
            "urgency": "Unknown",
            "tone": "Unknown",
            "issue_request": "",
            "sender": "",
            "subject": ""
        }

        try:
            raw_gemini_output = await self.gemini_api.generate_content(full_prompt)
            trace += self._log_decision_trace(f"Gemini raw email extraction output: {raw_gemini_output}")

            if isinstance(raw_gemini_output, dict):
                extracted_data = raw_gemini_output
            elif isinstance(raw_gemini_output, str):
                try:
                    extracted_data = json.loads(raw_gemini_output)
                except json.JSONDecodeError:
                    trace += self._log_decision_trace(f"Gemini email output not valid JSON: {raw_gemini_output}. Using empty data.")
            else:
                 trace += self._log_decision_trace("Gemini email output is None or unexpected type. Using empty data.")

            # Update action_trigger_data with extracted values
            action_trigger_data.update({
                "urgency": extracted_data.get("urgency", "Unknown"),
                "tone": extracted_data.get("tone", "Unknown"),
                "issue_request": extracted_data.get("issue_request", ""),
                "sender": extracted_data.get("sender", ""),
                "subject": extracted_data.get("subject", "")
            })

            # Determine action based on tone and urgency
            if action_trigger_data["tone"] == "Escalation" or action_trigger_data["urgency"] in ["High", "Critical"]:
                chained_action = "Escalate to CRM"
            elif action_trigger_data["tone"] == "Threatening":
                chained_action = "Flag Risk and Escalate"
            else:
                chained_action = "Log and Close"

            trace += self._log_decision_trace(f"Determined chained action: {chained_action}")

            return {
                "extracted_data": extracted_data,
                "decision_trace": trace,
                "chained_action": chained_action,
                "action_trigger_data": action_trigger_data
            }

        except Exception as e:
            trace += self._log_decision_trace(f"Error processing email with Gemini: {e}")
            return {"extracted_data": extracted_data, "decision_trace": trace, "chained_action": None, "action_trigger_data": action_trigger_data}