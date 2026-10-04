"""
api.py - FastAPI HTTP Service for TaskFlow RAG Pipeline
========================================================

WHAT THIS SCRIPT DOES:
This file wraps our existing Retrieval-Augmented Generation (RAG) pipeline
in a lightweight, high-performance HTTP REST API using FastAPI. It allows external
clients (like our floating web chat widget, mobile apps, or curl) to submit questions
over HTTP and receive AI-generated answers with source citations.

KEY DESIGN PRINCIPLES:
1. CODE REUSE: We do not re-implement the vector search or prompt engineering here.
   Instead, we import `answer_question()` directly from `rag_chat.py` (which re-exports
   from `rag_engine.py`).
2. ROBUST ERROR HANDLING: If the backend RAG pipeline encounters an unexpected crash,
   we catch the exception and return a clean HTTP 500 status with a generic error message.
   Raw internal errors and stack traces are logged on the server and never leaked to the client.
3. CORS ENABLED: Cross-Origin Resource Sharing is enabled with wildcard permissions for testing,
   allowing the embeddable chat widget running on any domain/port (e.g., localhost:3000,
   test.html via file:// or http-server) to communicate with this backend.
4. SELF-HOSTED VIA UVICORN: Includes a `__main__` entry point so you can start the API
   directly with `python api.py`.

ENDPOINTS:
  - GET  /health : Simple status probe returning {"status": "ok"}.
  - POST /chat   : Accepts {"message": "..."} and returns {"answer": "...", "sources": [...]}.

USAGE:
  Start the server:
    python api.py
  Or with uvicorn CLI directly:
    uvicorn api:app --reload --port 8000
"""

import sys
import logging
from contextlib import asynccontextmanager
from typing import List, Any
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# Ensure Windows terminal doesn't crash when printing Unicode characters or emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Configure logger to capture diagnostic information on the server
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("rag_api")

# ==============================================================================
# 1. IMPORT RAG PIPELINE
# ==============================================================================
# Import and reuse the existing answer_question() function and collection helper.
# We import from rag_chat.py as requested, falling back to rag_engine.py if needed.
try:
    from rag_chat import answer_question, get_chroma_collection
except ImportError:
    from rag_engine import answer_question, get_chroma_collection

import config


# ==============================================================================
# WIDGET-SPECIFIC SYSTEM PROMPT (USED ONLY IN API PATH)
# ==============================================================================
API_SYSTEM_PROMPT = config.SYSTEM_PROMPT



# ==============================================================================
# 2. REQUEST & RESPONSE SCHEMAS (PYDANTIC)
# ==============================================================================
class ChatRequest(BaseModel):
    """
    Schema for incoming chat requests.
    Validates that the client provides a JSON payload with a non-empty 'message' string,
    and an optional conversation history list.
    """
    message: str = Field(
        ...,
        description="The user's natural language question.",
        examples=["What pricing plans does TaskFlow offer?"]
    )
    history: list[dict[str, Any]] | None = Field(
        default=None,
        description="Optional list of previous conversation turns for multi-turn context."
    )



class ChatResponse(BaseModel):
    """
    Schema for outgoing chat responses.
    Contains the generated AI answer and the list of retrieved context sources.
    """
    answer: str = Field(
        ...,
        description="AI-generated answer based on the knowledge base."
    )
    sources: List[Any] = Field(
        default_factory=list,
        description="List of retrieved document chunks and source citations."
    )


# ==============================================================================
# 3. FASTAPI INITIALIZATION, LIFESPAN (WARMUP), & CORS MIDDLEWARE
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager for startup and shutdown events.
    Pre-warms the RAG pipeline on server startup to eliminate cold-start latency:
      1. Loads the sentence-transformers embedding model into memory.
      2. Opens and connects to the persistent ChromaDB collection.
      3. Runs a throwaway warmup query through the full pipeline
         (embed -> retrieve -> generate via Groq).
    """
    logger.info("Warming up RAG pipeline...")
    try:
        # 1 & 2: Load embedding model and connect to ChromaDB collection
        get_chroma_collection()

        # 3: Run one throwaway warmup query through the full pipeline (embed -> retrieve -> generate)
        answer_question("What is TaskFlow?", system_prompt=API_SYSTEM_PROMPT)
    except Exception as exc:
        logger.error(f"Error during RAG pipeline warmup: {exc}", exc_info=True)

    logger.info("Ready to serve requests")
    yield


# Create the FastAPI application instance with metadata for auto-generated docs
app = FastAPI(
    title="TaskFlow FAQ Chatbot API",
    description="HTTP API serving RAG-powered answers from TaskFlow PDF documentation.",
    version="1.0.0",
    lifespan=lifespan
)

# Add Cross-Origin Resource Sharing (CORS) middleware.
# During local development and testing, allowing all origins ("*") enables web browsers
# to send requests to this API from test pages running on different ports or domains.
# In production, replace ["*"] with a whitelist of your trusted website domains.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Allows all origins during testing
    allow_credentials=True,
    allow_methods=["*"],          # Allows all HTTP methods (GET, POST, OPTIONS, etc.)
    allow_headers=["*"],          # Allows all HTTP headers
)


# ==============================================================================
# 4. API ENDPOINTS
# ==============================================================================
@app.get(
    "/health",
    summary="Health Check",
    tags=["System"],
    response_model=dict
)
def health_check():
    """
    Simple health check probe.
    Used by load balancers, monitoring tools, or developers to quickly confirm
    that the server is alive and accepting HTTP traffic.
    """
    return {"status": "ok"}


@app.post(
    "/chat",
    summary="Ask a Question",
    tags=["Chat"],
    response_model=ChatResponse
)
def chat(request: ChatRequest):
    """
    Main chat endpoint for the FAQ widget:
    1. Receives the user question from the JSON request body.
    2. Passes it directly to answer_question() in the RAG pipeline.
    3. Returns the answer and sources as JSON.
    4. Catches any unhandled exceptions and returns an HTTP 500 error without
       leaking internal stack traces or sensitive implementation details.
    """
    # Guard against completely empty or whitespace-only messages
    clean_message = request.message.strip()
    if not clean_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty."
        )

    try:
        # Delegate to our existing RAG pipeline using the widget-optimized system prompt and bounded history
        rag_result = answer_question(
            clean_message,
            system_prompt=API_SYSTEM_PROMPT,
            history=request.history
        )

        # Extract answer and sources from the RAG engine result
        answer = rag_result.get("answer", "")
        sources = rag_result.get("sources", [])

        return ChatResponse(answer=answer, sources=sources)

    except Exception as exc:
        # Log the detailed exception server-side for troubleshooting
        logger.error(f"Unexpected error while processing chat question: {exc}", exc_info=True)

        # Return a safe, generic HTTP 500 error to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while processing your question. Please try again later."
        )


# ==============================================================================
# 5. SERVER ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print(" 🚀 Starting TaskFlow FAQ Chatbot API Server")
    print("=" * 70)
    print("📍 Local URL:    http://127.0.0.1:8000")
    print("🩺 Health Check: http://127.0.0.1:8000/health")
    print("💬 Chat API:     http://127.0.0.1:8000/chat")
    print("📖 Interactive Docs: http://127.0.0.1:8000/docs")
    print("=" * 70)

    # Run the Uvicorn ASGI server locally on port 8000 with hot-reloading enabled
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
