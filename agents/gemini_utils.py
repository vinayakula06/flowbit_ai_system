# agents/gemini_utils.py
import httpx
import json
import os # Import os for environment variable check if needed, though not directly used in this snippet
from typing import Dict, Any, Optional

# NEW IMPORTS FOR RETRY LOGIC
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

class GeminiAPI:
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash-latest"):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.model = model
        self.client = httpx.AsyncClient()

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=10), # Wait 1s, 2s, 4s... up to 10s
        stop=stop_after_attempt(3), # Retry 3 times
        # Retry only on specific network/connection errors, not on all HTTP errors
        retry=retry_if_exception_type(httpx.NetworkError) | # Catches connection refused, DNS errors, etc.
              retry_if_exception_type(httpx.TimeoutException) | # Catches read timeouts
              retry_if_exception_type(httpx.ConnectError) | # Catches connection errors
              retry_if_exception_type(httpx.ConnectTimeout) | # Catches connection timeouts
              retry_if_exception_type(httpx.RemoteProtocolError), # Catches protocol-level errors
        # Note: By default, tenacity does not retry on httpx.HTTPStatusError (4xx/5xx).
        # If you wanted to retry on specific 5xx errors (e.g., 500, 502, 503, 504), you would
        # need to add retry_if_exception_type(httpx.HTTPStatusError) and potentially use a
        # custom `before_sleep` or `after` callback to check the status code before retrying.
        # For this application, common LLM failures are often network/timeout or 429 (rate limit).
        # 429 needs different handling (e.g., longer waits, more attempts, or specific token bucket).
    )
    async def generate_content(self, prompt_text: str, temperature: float = 0.0) -> Optional[str]:
        """
        Calls the Gemini API to generate content with retry logic.
        """
        url = f"{self.base_url}/{self.model}:generateContent?key={self.api_key}"
        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "response_mime_type": "application/json"
            }
        }

        # The core HTTP call. Exceptions raised here will trigger tenacity's retry.
        try:
            response = await self.client.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status() # This will raise httpx.HTTPStatusError for 4xx or 5xx

            response_json = response.json()

            if response_json and "candidates" in response_json and len(response_json["candidates"]) > 0:
                first_candidate = response_json["candidates"][0]
                if "content" in first_candidate and "parts" in first_candidate["content"]:
                    for part in first_candidate["content"]["parts"]:
                        if "text" in part:
                            try:
                                return json.loads(part["text"])
                            except json.JSONDecodeError:
                                return part["text"] # Return raw text if not valid JSON (fallback)
            return None # No content found in response

        except httpx.RequestError as e: # This is caught by tenacity's retry_if_exception_type
            print(f"HTTPX Request Error during Gemini API call (retrying): {e}")
            raise e # Re-raise to trigger retry by tenacity
        except httpx.HTTPStatusError as e: # Catches HTTP errors (e.g., 400, 429, 500)
            print(f"HTTP Status Error from Gemini API: {e.response.status_code} - {e.response.text}")
            # By default, tenacity does not retry on HTTPStatusError unless explicitly configured in @retry.
            # We are catching it here and not re-raising for retry based on typical usage.
            return None # Or raise a custom exception if you want specific error propagation
        except Exception as e:
            print(f"An unexpected error occurred during Gemini API call: {e}")
            return None