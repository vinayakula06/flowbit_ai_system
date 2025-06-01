# agents/pdf_agent.py
from agents.base_agent import BaseAgent
from shared_memory import SharedMemory
import PyPDF2
import re
from typing import Dict, Any, List
import os

class PDFAgent(BaseAgent):
    def __init__(self, memory: SharedMemory):
        super().__init__(memory)

    def _extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extracts text from a PDF file using PyPDF2."""
        text = ""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text += page.extract_text() or "" # Handle case where extract_text() returns None
            return text
        except Exception as e:
            # More specific error logging for the agent's decision trace
            self._log_decision_trace(f"Error extracting text from PDF '{pdf_path}': {e}")
            return f"Error extracting text from PDF: {e}"

    def _parse_invoice_data(self, text: str) -> Dict[str, Any]:
        """Parses invoice data from text. (Highly dependent on invoice format)"""
        invoice_data = {}
        # Example regex for common invoice fields
        # Note: These regex patterns are highly dependent on the exact text format in your PDFs.
        invoice_data["invoice_number"] = re.search(r"Invoice N[o#]?:\s*([A-Za-z0-9-]+)", text, re.IGNORECASE)
        invoice_data["invoice_number"] = invoice_data["invoice_number"].group(1) if invoice_data["invoice_number"] else "N/A"

        invoice_data["total_amount"] = re.search(r"(?:Total|Grand Total):\s*[$€£]?\s*([\d,\.]+)", text, re.IGNORECASE)
        # Convert to float, handling commas as thousands separators
        invoice_data["total_amount"] = float(invoice_data["total_amount"].group(1).replace(",", "")) if invoice_data["total_amount"] else 0.0

        invoice_data["currency"] = re.search(r"(?:Total|Grand Total):\s*([$€£])", text)
        invoice_data["currency"] = invoice_data["currency"].group(1) if invoice_data["currency"] else "USD" # Default to USD

        # Simplified line item parsing (can be very complex for real invoices)
        # This example assumes a simple format like: Item Description Quantity Price Total
        # Adjust this regex if your invoice format is different.
        line_items = []
        # Look for lines that typically start with a description, followed by numbers
        for line in text.split('\n'):
            # Example: "Consulting Services     1          15000.00     15000.00"
            match = re.search(r"([\w\s]+?)\s+(\d+)\s+([\d.]+)\s+([\d.]+)", line.strip())
            if match:
                description = match.group(1).strip()
                try:
                    quantity = int(match.group(2))
                    unit_price = float(match.group(3))
                    line_total = float(match.group(4))
                    line_items.append({
                        "description": description,
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "line_total": line_total
                    })
                except ValueError:
                    # Skip if conversion fails (e.g., malformed number)
                    pass
        invoice_data["line_items"] = line_items

        return invoice_data

    def _check_policy_mentions(self, text: str) -> List[str]:
        """Checks for specific policy mentions like GDPR, FDA, HIPAA."""
        mentions = []
        if re.search(r"\bGDPR\b", text, re.IGNORECASE): # \b for word boundary
            mentions.append("GDPR")
        if re.search(r"\bFDA\b", text, re.IGNORECASE):
            mentions.append("FDA")
        if re.search(r"\bHIPAA\b", text, re.IGNORECASE):
            mentions.append("HIPAA")
        if re.search(r"\b(CCPA|California Consumer Privacy Act)\b", text, re.IGNORECASE): # Example for another regulation
            mentions.append("CCPA")
        return mentions

    def process_input(self, input_content: str) -> Dict[str, Any]:
        """
        Extracts fields from PDF, parses invoice data or policy mentions, and flags.
        `input_content` is expected to be the path to the PDF file.
        """
        trace = self._log_decision_trace("Starting PDF processing...")
        pdf_path = input_content

        if not os.path.exists(pdf_path) or not pdf_path.lower().endswith(".pdf"):
            trace += self._log_decision_trace(f"Invalid PDF path provided: {pdf_path}")
            return {"extracted_data": {}, "decision_trace": trace, "chained_action": "Log Error", "action_trigger_data": {}}

        pdf_text = self._extract_text_from_pdf(pdf_path)
        if "Error extracting text" in pdf_text or not pdf_text.strip(): # Also check if text is empty after strip
            trace += self._log_decision_trace(f"Failed to extract meaningful text from PDF: {pdf_text[:100]}...")
            return {"extracted_data": {"pdf_extraction_error": pdf_text}, "decision_trace": trace, "chained_action": "Review PDF Manually", "action_trigger_data": {}}

        trace += self._log_decision_trace("Text extracted from PDF. Analyzing content...")

        extracted_data = {"raw_text_snippet": pdf_text[:500]} # Store a snippet

        chained_action = None
        action_trigger_data = {
            "pdf_path": pdf_path,
            "extracted_text_snippet": pdf_text[:200]
        }

        # Retrieve intent from shared memory
        latest_interaction = self.memory.read_latest_interaction()
        classification_intent = latest_interaction.get("classification", {}).get("intent")

        if classification_intent == "Invoice":
            invoice_data = self._parse_invoice_data(pdf_text)
            extracted_data["invoice_details"] = invoice_data
            trace += self._log_decision_trace(f"Parsed invoice data: {invoice_data}")

            if invoice_data.get("total_amount", 0) > 10000:
                chained_action = "Flag High Value Invoice"
                trace += self._log_decision_trace(f"Invoice total ({invoice_data.get('total_amount', 0)}) exceeds 10,000.")
                action_trigger_data["invoice_total"] = invoice_data.get("total_amount")
                action_trigger_data["invoice_number"] = invoice_data.get("invoice_number")
            else:
                chained_action = "Process Invoice"

        elif classification_intent == "Regulation":
            policy_mentions = self._check_policy_mentions(pdf_text)
            extracted_data["policy_mentions"] = policy_mentions
            trace += self._log_decision_trace(f"Policy mentions found: {policy_mentions}")

            if policy_mentions:
                chained_action = "Flag Compliance Risk"
                trace += self._log_decision_trace(f"Detected compliance keywords: {', '.join(policy_mentions)}.")
                action_trigger_data["compliance_keywords"] = policy_mentions
            else:
                chained_action = "Process Policy Document"
        else:
            trace += self._log_decision_trace(f"PDF content does not match expected intent for detailed parsing: {classification_intent}. Routing for manual review.")
            chained_action = "Review PDF Manually" # Default if intent is Unknown or not handled

        return {
            "extracted_data": extracted_data,
            "decision_trace": trace,
            "chained_action": chained_action,
            "action_trigger_data": action_trigger_data
        }