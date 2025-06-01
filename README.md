# Multi-Format Autonomous AI System

## Objective
This project aims to build a multi-agent system capable of processing diverse inputs (Email, JSON, PDF), classifying their format and business intent, routing them to specialized agents for detailed processing, and dynamically triggering follow-up actions based on extracted data and contextual decisioning.

## Architecture

```mermaid
graph TD
    A[User Input: Email, JSON, PDF] --> B[FastAPI Endpoint /upload]
    B --> C{Classifier Agent}
    C -- Format + Intent --> D[Shared Memory Store]
    C -- Routing --> E{Action Router}

    E -- Route to Email Agent --> F[Email Agent]
    E -- Route to JSON Agent] --> G[JSON Agent]
    E -- Route to PDF Agent] --> H[PDF Agent]

    F -- Extracted Data + Actions --> D
    G -- Extracted Data + Actions --> D
    H -- Extracted Data + Actions --> D

    D -- Agent Decisions + Chained Actions --> I[Action Router]
    I -- Triggers External API Calls --> J[Simulated CRM / Risk Alert API]
    D -- Logs for Audit --> K[Output Logs]