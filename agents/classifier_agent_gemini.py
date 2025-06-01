# agents/classifier_agent_gemini.py
# REMOVE: from agents.base_agent import BaseAgent # This line should NOT be here
from shared_memory import SharedMemory
from agents.gemini_utils import GeminiAPI
import json
import re
from typing import Dict, Any
import os

# NEW IMPORTS for file content extraction
import email
from email import policy
import PyPDF2 # For PDF reading

class ClassifierAgent: # <--- REMOVED INHERITANCE FROM BaseAgent
    def __init__(self, memory: SharedMemory, gemini_api_key: str):
        self.memory = memory # Directly set memory
        self.agent_name = self.__class__.__name__ # Define agent_name

        self.gemini_api = GeminiAPI(api_key=gemini_api_key)

        self.classification_schema = {
            "format": {"type": "string", "enum": ["JSON", "Email", "PDF", "Unknown"]},
            "intent": {"type": "string", "enum": ["RFQ", "Complaint", "Invoice", "Regulation", "Fraud Risk", "Unknown"]},
            "routed_agent": {"type": "string", "enum": ["EmailAgent", "JSONAgent", "PDFAgent", "UnknownAgent"]}
        }

        # --- UPDATED PROMPT TEMPLATE ---
        self.prompt_template = """You are an AI classifier agent specialized in understanding business communications.
            Your primary task is to classify the format and business intent of the given input.
            Based on the identified format, you must also determine the most appropriate specialized agent for further processing.

            Available Formats: JSON, Email, PDF
            Available Intents: RFQ, Complaint, Invoice, Regulation, Fraud Risk
            Available Agents for Routing: EmailAgent, JSONAgent, PDFAgent

            **Key Intent Definitions:**
            -   **Complaint**: Expresses dissatisfaction, reports issues (damaged goods, poor service, bugs), or demands resolution for a problem. Look for words like "unacceptable," "problem," "issue," "damaged," "not working," "dissatisfied," "urgent," "fix," "refund," "escalate."
            -   **RFQ (Request for Quotation)**: Seeks pricing or proposals for goods or services.
            -   **Invoice**: A bill for goods or services provided. Often contains "Invoice No.", "Total Amount", "Due Date".
            -   **Regulation**: Contains legal rules, compliance requirements, or policy documents. Often mentions terms like "GDPR", "FDA", "compliance", "policy".
            -   **Fraud Risk**: Indicates suspicious activity, potential security breaches, or high-risk transactions.

            Input content:
            {input_content}

            Carefully analyze the 'Input content' to first infer its format (JSON, Email, or PDF). Then determine its business intent. Be precise in classifying the format as 'PDF' if the content implies a document structure (like an invoice or policy).

            Based on the content and inferred format, classify and provide the output in JSON format conforming STRICTLY to the following schema:
            {schema}

            Few-shot Examples:
            ---
            Example 1 (Email - Complaint - High Urgency):
            Input: "Subject: IMMEDIATE ATTENTION REQUIRED: Damaged Shipment - Order #XYZ789\\nDear Support, My recent order #12345 arrived damaged. I need a replacement immediately. This is unacceptable."
            Output: {{"format": "Email", "intent": "Complaint", "routed_agent": "EmailAgent"}}

            Example 2 (Email - Complaint - Service Issue):
            Input: "Subject: Issue with my recent service visit\\nFrom: unhappy@customer.com\\nDear Team, I am writing to express my dissatisfaction with the service technician who visited yesterday. The problem with my internet connection is still unresolved, and he was quite rude."
            Output: {{"format": "Email", "intent": "Complaint", "routed_agent": "EmailAgent"}}

            Example 3 (PDF - Invoice):
            Input: "This document is a PDF invoice. It explicitly states: Invoice No: INV-2025-001. Date: 2025-05-31. Total Amount: $12,500.00. Due Date: 2025-06-30. Line Items: Item A - 5000.00, Item B - 7500.00."
            Output: {{"format": "PDF", "intent": "Invoice", "routed_agent": "PDFAgent"}}

            Example 4 (PDF - Regulation):
            Input: "This is a PDF document detailing the new data privacy regulations. It specifies GDPR compliance requirements for data processing and mentions FDA guidelines related to product safety."
            Output: {{"format": "PDF", "intent": "Regulation", "routed_agent": "PDFAgent"}}

            Example 5 (JSON - Fraud Risk - High Risk):
            Input: {{"transaction_id": "TXN789", "amount": 15000, "user_id": "USR456", "risk_score": 0.95, "ip_address": "192.168.1.100"}}
            Output: {{"format": "JSON", "intent": "Fraud Risk", "routed_agent": "JSONAgent"}}

            Example 6 (Email - RFQ):
            Input: "Subject: Request for Quotation - Server Hardware\\nDear Vendor, We are looking to purchase 10 servers with the following specifications..."
            Output: {{"format": "Email", "intent": "RFQ", "routed_agent": "EmailAgent"}}
            ---

            Your classification (JSON only):
            """
        # --- END UPDATED PROMPT TEMPLATE ---

    def _infer_format_heuristic(self, input_content: Any) -> str:
        """Basic heuristic to guess format before LLM for better routing."""
        if isinstance(input_content, dict):
            return "JSON"
        elif isinstance(input_content, str):
            if re.search(r'Subject:.*?\n|From:.*?\n|To:.*?\n|Dear\s+\w+', input_content, re.IGNORECASE | re.DOTALL):
                return "Email"
            # If the string content strongly suggests a PDF (e.g. from raw PDF text)
            if re.search(r'\b(?:invoice|bill|document|policy|regulation)\b', input_content, re.IGNORECASE) and \
               re.search(r'\b(?:PDF|PDF document|document analysis)\b', input_content, re.IGNORECASE):
                return "PDF"
            # If it's a file path to a PDF or email, it will be handled by the main classify logic
            elif input_content.lower().endswith(".pdf"):
                return "PDF"
            elif input_content.lower().endswith((".eml", ".msg")):
                return "Email"
        return "Unknown"

    def _log_decision_trace(self, trace_message: str) -> str:
        """Helper to log decision traces."""
        return f"[{self.agent_name}] {trace_message}"

    def _extract_email_content_from_file(self, file_path: str) -> str:
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
            self._log_decision_trace(f"Error extracting content from email file {file_path} for classification: {e}")
            return f"Error: Could not read email file content for classification. Details: {e}"

    def _extract_pdf_content_from_file(self, file_path: str) -> str:
        """Extracts text content from a PDF file using PyPDF2."""
        text = ""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() or ""
            return text
        except Exception as e:
            self._log_decision_trace(f"Error extracting content from PDF file {file_path} for classification: {e}")
            return f"Error: Could not read PDF file content for classification. Details: {e}"


    async def classify(self, input_type: str, input_content: Any) -> Dict[str, str]:
        """
        Classifies the input content and returns format, intent, and routed agent.
        """
        trace = self._log_decision_trace(f"Starting classification for {input_type}...")

        llm_input_content = input_content

        # --- Read actual file content for classification ---
        if input_type == "email_file" and isinstance(input_content, str) and os.path.exists(input_content):
            llm_input_content = self._extract_email_content_from_file(input_content)
            trace += self._log_decision_trace(f"Read email file content for classification. Snippet: {llm_input_content[:200]}...")
        elif input_type == "pdf" and isinstance(input_content, str) and os.path.exists(input_content):
            llm_input_content = self._extract_pdf_content_from_file(input_content)
            trace += self._log_decision_trace(f"Read PDF file content for classification. Snippet: {llm_input_content[:200]}...")
        elif input_type == "json" and isinstance(input_content, dict):
            llm_input_content = json.dumps(input_content, indent=2)
            trace += self._log_decision_trace(f"Converted JSON dict to string for classification.")
        elif input_type == "email_text":
            llm_input_content = input_content
            trace += self._log_decision_trace(f"Using raw email text for classification.")

        full_prompt = self.prompt_template.format(
            input_content=llm_input_content,
            schema=json.dumps(self.classification_schema, indent=2)
        )

        classification = {"format": "Unknown", "intent": "Unknown", "routed_agent": "UnknownAgent"}
        try:
            raw_gemini_output = await self.gemini_api.generate_content(full_prompt)
            trace += self._log_decision_trace(f"Gemini raw classification output: {raw_gemini_output}")

            if isinstance(raw_gemini_output, dict):
                classification = raw_gemini_output
            elif isinstance(raw_gemini_output, str):
                try:
                    classification = json.loads(raw_gemini_output)
                except json.JSONDecodeError:
                    trace += self._log_decision_trace(f"Gemini output not valid JSON: {raw_gemini_output}. Attempting heuristic fallback.")
            else:
                 trace += self._log_decision_trace("Gemini output is None or unexpected type. Attempting heuristic fallback.")

            # Basic validation of LLM output against schema enums
            if not all(k in classification for k in ["format", "intent", "routed_agent"]):
                trace += self._log_decision_trace("LLM output missing required keys. Defaulting to Unknown.")
                raise ValueError("LLM output missing required keys.")

            if classification["format"] not in self.classification_schema["format"]["enum"]:
                trace += self._log_decision_trace(f"Invalid format '{classification['format']}' from LLM. Setting to 'Unknown'.")
                classification["format"] = "Unknown"
            if classification["intent"] not in self.classification_schema["intent"]["enum"]:
                trace += self._log_decision_trace(f"Invalid intent '{classification['intent']}' from LLM. Setting to 'Unknown'.")
                classification["intent"] = "Unknown"
            if classification["routed_agent"] not in self.classification_schema["routed_agent"]["enum"]:
                trace += self._log_decision_trace(f"Invalid routed_agent '{classification['routed_agent']}' from LLM. Setting to 'UnknownAgent'.")
                classification["routed_agent"] = "UnknownAgent"

        except Exception as e:
            trace += self._log_decision_trace(f"Error during Gemini classification: {e}. Attempting heuristic fallback.")
            inferred_format = self._infer_format_heuristic(input_content)
            classification = {
                "format": inferred_format,
                "intent": "Unknown",
                "routed_agent": {
                    "Email": "EmailAgent",
                    "JSON": "JSONAgent",
                    "PDF": "PDFAgent"
                }.get(inferred_format, "UnknownAgent")
            }
            trace += self._log_decision_trace(f"Heuristic fallback classification: {classification}")

        # --- IMPORTANT ---
        # The memory.write_interaction call has been REMOVED from here.
        # It is now handled once, at the very end of the main.py's upload_input function,
        # where all aggregated data from all agents is available.

        return classification