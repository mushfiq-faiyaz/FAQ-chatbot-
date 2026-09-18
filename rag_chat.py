"""
rag_chat.py - RAG Pipeline Entry Point & Compatibility Wrapper
==============================================================

WHAT THIS MODULE DOES:
This module exposes the core question-answering logic of the FAQ Chatbot.
It re-exports `answer_question` from `rag_engine.py`, ensuring consistent
access for the FastAPI backend (api.py), CLI tools, and any external scripts.

HOW IT WORKS:
1. Takes a natural language user question.
2. Retrieves the most relevant context chunks from the ChromaDB vector database.
3. Formulates a strict, grounded RAG prompt.
4. Calls the Groq LLaMA 3.3 LLM to generate an accurate answer based only on retrieved context.
5. Returns a structured dictionary containing the answer and source citations.
"""

# Re-export answer_question from rag_engine
from rag_engine import answer_question, retrieve_relevant_chunks, build_rag_prompt, get_chroma_collection, prepare_conversation_history

__all__ = ["answer_question", "retrieve_relevant_chunks", "build_rag_prompt", "get_chroma_collection", "prepare_conversation_history"]

