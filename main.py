from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request # Added Request
from fastapi.responses import HTMLResponse # Added HTMLResponse
from fastapi.templating import Jinja2Templates # Added Jinja2Templates
from pydantic import BaseModel
import uvicorn
import os
import json
from typing import Dict, Any, Optional
import asyncio

# Import your agents
from agents.classifier_agent_gemini import ClassifierAgent
from agents.email_agent_gemini import EmailAgent
from agents.json_agent import JSONAgent
from agents.pdf_agent import PDFAgent
from agents.action_router import ActionRouter
from shared_memory import SharedMemory

# If you are using python-dotenv for local environment variables, uncomment these:
# from dotenv import load_dotenv
# load_dotenv()

# --- MODEL DEFINITIONS (MOVED TO TOP FOR CORRECT SCOPE) ---
class AgentOutput(BaseModel):
    agent_name: str
    extracted_data: Dict[str, Any]
    decision_trace: str
    chained_action_triggered: Optional[str] = None

class ProcessingResult(BaseModel):
    input_metadata: Dict[str, Any]
    classification: Dict[str, str]
    agent_outputs: Dict[str, AgentOutput]
    final_action: Optional[str] = None
    audit_log: str
# --- END MODEL DEFINITIONS ---


app = FastAPI(
    title="Multi-Format Autonomous AI System",
    description="Processes inputs, classifies intent, and triggers chained actions."
)

# Initialize shared memory and agents
memory = SharedMemory(db_path="shared_memory.db")

# Retrieve GEMINI_API_KEY from environment variables
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set. Please set it before starting the application.")

# Initialize agents, passing the API key to those that use Gemini
classifier_agent = ClassifierAgent(memory=memory, gemini_api_key=GEMINI_API_KEY)
email_agent = EmailAgent(memory=memory, gemini_api_key=GEMINI_API_KEY)
json_agent = JSONAgent(memory=memory)
pdf_agent = PDFAgent(memory=memory)
action_router = ActionRouter(memory=memory)

# Directory to store temporary uploaded files
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# --- UI Integration: NEW LINES START HERE ---
# Initialize Jinja2Templates to serve HTML files from the 'templates' directory
templates = Jinja2Templates(directory="templates")

# NEW: Root endpoint to serve the UI form
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """
    Serves the main HTML page with input forms.
    """
    return templates.TemplateResponse("index.html", {"request": request})

# --- UI Integration: NEW ENDPOINT FOR UI SUBMISSIONS ---
# This endpoint will handle UI forms and return an HTML response.
# It duplicates the core processing logic to avoid changing the original /upload's JSON behavior.
@app.post("/ui_upload", response_class=HTMLResponse)
async def ui_upload_input(
    request: Request, # Added Request parameter
    file: UploadFile = File(None),
    raw_text: Optional[str] = Form(None),
    json_data: Optional[str] = Form(None)
):
    """
    Handles uploads from the UI, processes them, and returns an HTML response.
    This endpoint duplicates the core processing logic to avoid changing the original /upload's JSON behavior.
    """
    input_type = None
    input_content = None
    file_path = None
    original_filename = "N/A"
    
    try: # Wrap the entire logic in a try-except for UI error display
        if file:
            original_filename = file.filename
            file_extension = file.filename.split(".")[-1].lower()
            file_path = os.path.join(UPLOAD_DIR, original_filename)
            with open(file_path, "wb") as f:
                f.write(await file.read())

            if file_extension in ["eml", "msg"]:
                input_type = "email_file"
            elif file_extension == "pdf":
                input_type = "pdf"
            else:
                if os.path.exists(file_path):
                    os.remove(file_path)
                raise HTTPException(status_code=400, detail=f"Unsupported file type: .{file_extension}. Supported types are .eml, .msg, .pdf.")
            input_content = file_path

        elif raw_text:
            input_type = "email_text"
            input_content = raw_text

        elif json_data:
            input_type = "json"
            try:
                input_content = json.loads(json_data)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid JSON format provided in 'json_data' field.")
        else:
            raise HTTPException(status_code=400, detail="No input provided. Please provide a 'file', 'raw_text', or 'json_data'.")

        audit_log = []
        processing_results = {
            "input_metadata": {
                "source_type": input_type,
                "timestamp": SharedMemory.get_current_timestamp(),
                "filename": original_filename
            },
            "classification": {},
            "agent_outputs": {}, # This will contain AgentOutput objects
            "final_action": None,
            "audit_log": ""
        }

        audit_log.append(f"Classifier Agent: Processing input type: {input_type}")
        classification_result = await classifier_agent.classify(input_type, input_content)
        processing_results["classification"] = classification_result
        audit_log.append(f"Classifier Agent Output: {classification_result}")

        routed_agent_name = classification_result.get("routed_agent")
        audit_log.append(f"Action Router: Routing to {routed_agent_name} based on classification.")

        agent_output_data = {}
        if routed_agent_name == "EmailAgent":
            agent_output_data = await email_agent.process_input(input_content)
        elif routed_agent_name == "JSONAgent":
            agent_output_data = json_agent.process_input(input_content)
        elif routed_agent_name == "PDFAgent":
            agent_output_data = pdf_agent.process_input(input_content)
        else:
            audit_log.append(f"No specific agent found for {routed_agent_name} or agent is 'UnknownAgent'.")

        action_data_for_router = agent_output_data.get("action_trigger_data", {})
        if "chained_action" in agent_output_data:
            action_data_for_router["chained_action"] = agent_output_data["chained_action"]

        processing_results["agent_outputs"][routed_agent_name] = AgentOutput(
            agent_name=routed_agent_name,
            extracted_data=agent_output_data.get("extracted_data", {}),
            decision_trace=agent_output_data.get("decision_trace", "N/A"),
            chained_action_triggered=agent_output_data.get("chained_action", None)
        )
        audit_log.append(f"{routed_agent_name} Output: {agent_output_data}")

        final_action_triggered = await action_router.trigger_final_action(
            classification_result["intent"],
            action_data_for_router
        )
        processing_results["final_action"] = final_action_triggered
        audit_log.append(f"Final Action Router: Triggered action: {final_action_triggered}")

        # --- CRITICAL FIX: Write the COMPLETE interaction to Shared Memory at the end ---
        final_input_metadata = processing_results["input_metadata"]
        final_classification = processing_results["classification"]
        final_agent_outputs_for_db = {k: v.dict() for k, v in processing_results["agent_outputs"].items()}
        final_chained_actions_for_db = [processing_results["final_action"]] if processing_results["final_action"] else []
        final_decision_traces_for_db = audit_log

        memory.write_interaction(
            input_metadata=final_input_metadata,
            classification=final_classification,
            agent_outputs=final_agent_outputs_for_db,
            chained_actions=final_chained_actions_for_db,
            decision_traces=final_decision_traces_for_db
        )
        # --- END CRITICAL FIX ---

        processing_results["audit_log"] = "\n".join(audit_log)

        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Return HTML response for UI display
        # Convert processing_results (which contains AgentOutput objects) to a fully serializable dict
        json_serializable_processing_results = processing_results.copy()
        ui_agent_outputs = {}
        for agent_name, agent_output_model in processing_results["agent_outputs"].items():
            ui_agent_outputs[agent_name] = agent_output_model.dict()
        json_serializable_processing_results["agent_outputs"] = ui_agent_outputs
        
        formatted_result = json.dumps(json_serializable_processing_results, indent=2)
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "result": formatted_result}
        )

    except HTTPException as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"HTTP Error: {e.status_code} - {e.detail}"}
        )
    except Exception as e:
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "error": f"An unexpected error occurred: {str(e)}"}
        )

# --- Original /upload endpoint remains here, UNCHANGED except for name ---
# It still handles JSON responses for API clients.
@app.post("/upload", response_model=ProcessingResult)
async def upload_input( # Renamed for clarity to avoid conflict with ui_upload_input
    file: UploadFile = File(None),
    raw_text: Optional[str] = Form(None),
    json_data: Optional[str] = Form(None)
):
    """
    Original API endpoint for programmatic access (returns JSON).
    It contains the same core processing logic as /ui_upload internally.
    """
    # This section mirrors the processing flow of ui_upload_input but prepares a JSON response.
    # It contains the core logic that was in your main.py before UI integration.
    input_type = None
    input_content = None
    file_path = None
    original_filename = "N/A"

    if file:
        original_filename = file.filename
        file_extension = file.filename.split(".")[-1].lower()
        file_path = os.path.join(UPLOAD_DIR, original_filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

        if file_extension in ["eml", "msg"]:
            input_type = "email_file"
        elif file_extension == "pdf":
            input_type = "pdf"
        else:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{file_extension}. Supported types are .eml, .msg, .pdf.")
        input_content = file_path

    elif raw_text:
        input_type = "email_text"
        input_content = raw_text

    elif json_data:
        input_type = "json"
        try:
            input_content = json.loads(json_data)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON format provided in 'json_data' field.")
    else:
        raise HTTPException(status_code=400, detail="No input provided. Please provide a 'file', 'raw_text', or 'json_data'.")

    audit_log = []
    processing_results = {
        "input_metadata": {
            "source_type": input_type,
            "timestamp": SharedMemory.get_current_timestamp(),
            "filename": original_filename
        },
        "classification": {},
        "agent_outputs": {}, # Will contain AgentOutput objects
        "final_action": None,
        "audit_log": ""
    }

    audit_log.append(f"Classifier Agent: Processing input type: {input_type}")
    classification_result = await classifier_agent.classify(input_type, input_content)
    processing_results["classification"] = classification_result
    audit_log.append(f"Classifier Agent Output: {classification_result}")

    routed_agent_name = classification_result.get("routed_agent")
    audit_log.append(f"Action Router: Routing to {routed_agent_name} based on classification.")

    agent_output_data = {}
    if routed_agent_name == "EmailAgent":
        agent_output_data = await email_agent.process_input(input_content)
    elif routed_agent_name == "JSONAgent":
        agent_output_data = json_agent.process_input(input_content)
    elif routed_agent_name == "PDFAgent":
        agent_output_data = pdf_agent.process_input(input_content)
    else:
        audit_log.append(f"No specific agent found for {routed_agent_name} or agent is 'UnknownAgent'.")

    action_data_for_router = agent_output_data.get("action_trigger_data", {})
    if "chained_action" in agent_output_data:
        action_data_for_router["chained_action"] = agent_output_data["chained_action"]

    processing_results["agent_outputs"][routed_agent_name] = AgentOutput( # Uses AgentOutput
        agent_name=routed_agent_name,
        extracted_data=agent_output_data.get("extracted_data", {}),
        decision_trace=agent_output_data.get("decision_trace", "N/A"),
        chained_action_triggered=agent_output_data.get("chained_action", None)
    )
    audit_log.append(f"{routed_agent_name} Output: {agent_output_data}")

    final_action_triggered = await action_router.trigger_final_action(
        classification_result["intent"],
        action_data_for_router
    )
    processing_results["final_action"] = final_action_triggered
    audit_log.append(f"Final Action Router: Triggered action: {final_action_triggered}")

    # --- CRITICAL FIX: Write the COMPLETE interaction to Shared Memory at the end ---
    final_input_metadata = processing_results["input_metadata"]
    final_classification = processing_results["classification"]
    final_agent_outputs_for_db = {k: v.dict() for k, v in processing_results["agent_outputs"].items()}
    final_chained_actions_for_db = [processing_results["final_action"]] if processing_results["final_action"] else []
    final_decision_traces_for_db = audit_log

    memory.write_interaction(
        input_metadata=final_input_metadata,
        classification=final_classification,
        agent_outputs=final_agent_outputs_for_db,
        chained_actions=final_chained_actions_for_db,
        decision_traces=final_decision_traces_for_db
    )
    # --- END CRITICAL FIX ---

    processing_results["audit_log"] = "\n".join(audit_log)

    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    return processing_results # Returns Pydantic model (JSON)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)