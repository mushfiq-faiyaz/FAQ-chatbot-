"""
app.py - Streamlit Chat Interface for FAQ / Documentation Support
==================================================================

WHAT THIS FILE DOES:
This is the interactive web interface where users can ask questions and receive
instant answers sourced from your PDF documents.

HOW STREAMLIT WORKS (EDUCATIONAL EXPLANATION):
Streamlit is a Python framework that converts Python scripts into interactive web apps.
Whenever a user clicks a button or types a message, Streamlit runs the script from top
to bottom. To remember the conversation history between these reruns, we use
`st.session_state`. Think of `st.session_state` like the application's memory bank!

KEY FEATURES INCLUDED:
1. Centralized settings loaded from config.py.
2. Clean, modern design with soft rounded chat bubbles and custom typography.
3. Interactive sidebar with API key management, database statistics, and 'Clear Chat'.
4. Document source pills / badges and an expandable viewer showing exact PDF excerpts.
5. Graceful error handling with friendly status banners.
"""

import os
import sys
from pathlib import Path
import streamlit as st

# Ensure Windows terminal doesn't crash on emoji prints
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import importlib
from dotenv import load_dotenv

# Ensure environment variables from .env are fresh on every run
load_dotenv(override=True)

# Import and reload our central configuration settings
import config
importlib.reload(config)

# Import and reload the RAG search and AI engine
import rag_engine
importlib.reload(rag_engine)
from rag_engine import answer_question, get_chroma_collection
from ingest import index_documents


# ==============================================================================
# CACHED RAG RESOURCES (LOAD ONCE ACROSS ALL SESSIONS & RERUNS)
# ==============================================================================
@st.cache_resource(show_spinner=False)
def get_cached_collection():
    """
    Initializes and caches the ChromaDB collection and sentence-transformers
    embedding model once across all users and reruns using Streamlit's cache_resource.
    """
    return get_chroma_collection()



# ==============================================================================
# 1. STREAMLIT PAGE CONFIGURATION
# ==============================================================================
# Must be the very first Streamlit call in the script!
# Sets browser title, tab icon, and default wide layout.
st.set_page_config(
    page_title=config.APP_TITLE,
    page_icon=config.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)


# ==============================================================================
# 2. CUSTOM MODERN STYLING (CSS)
# ==============================================================================
# Clean, soft aesthetic: rounded cards, gentle borders, and stylish source tags.
st.markdown("""
<style>
    /* Main container max width for comfortable reading */
    .block-container {
        max-width: 960px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }

    /* Header styling */
    .chat-header {
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(128, 128, 128, 0.2);
    }
    .chat-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
        color: inherit;
    }
    .chat-subtitle {
        font-size: 1rem;
        opacity: 0.8;
        margin-bottom: 0;
    }

    /* Source document pill tags */
    .source-container {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.6rem;
        margin-bottom: 0.4rem;
    }
    .source-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.2rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.78rem;
        font-weight: 500;
        background-color: rgba(59, 130, 246, 0.12);
        color: #2563eb;
        border: 1px solid rgba(59, 130, 246, 0.25);
    }

    /* Suggestion chips buttons styling */
    div[data-testid="stHorizontalBlock"] button {
        border-radius: 20px;
        font-size: 0.82rem;
        border: 1px solid rgba(128, 128, 128, 0.25);
        padding: 0.3rem 0.8rem;
        transition: all 0.2s ease;
    }

    /* Polished sidebar */
    section[data-testid="stSidebar"] {
        border-right: 1px solid rgba(128, 128, 128, 0.15);
    }
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# 3. EARLY STARTUP INITIALIZATION & RESOURCE WARMUP
# ==============================================================================
# Pre-load the embedding model and ChromaDB connection early so the user's first
# question does not experience cold-start latency.
with st.spinner("Loading assistant..."):
    try:
        cached_coll = get_cached_collection()
        rag_engine._cached_collection = cached_coll
    except Exception as e:
        st.error(f"Failed to initialize knowledge base: {e}")


# ==============================================================================
# 4. SESSION STATE INITIALIZATION (CHAT MEMORY)
# ==============================================================================
# When Streamlit reruns, local variables reset. 'st.session_state' is how we
# persist variables across reruns (such as the list of past messages).

if "messages" not in st.session_state:
    # Initialize with our welcome message defined in config.py
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": config.WELCOME_MESSAGE,
            "sources": []
        }
    ]


# ==============================================================================
# 5. SIDEBAR - SETTINGS, TOOLS & INFO
# ==============================================================================
with st.sidebar:
    st.title(f"{config.APP_ICON} {config.APP_TITLE}")
    st.caption("Customizable RAG FAQ & Documentation Assistant")

    st.markdown("---")

    # --- API Key Section ---
    st.subheader("🔑 AI Credentials")
    env_api_key = os.getenv("GROQ_API_KEY", "").strip()
    
    # Allow user to input or override the Groq key right from the UI
    user_api_key = st.text_input(
        "Groq API Key (Free)",
        type="password",
        value=st.session_state.get("custom_api_key", ""),
        help="Get a free key at https://console.groq.com/keys without entering a credit card.",
        placeholder="gsk_..."
    )
    if user_api_key:
        st.session_state["custom_api_key"] = user_api_key.strip()
        effective_key = user_api_key.strip()
    else:
        effective_key = env_api_key

    if effective_key and effective_key != "your_groq_api_key_here":
        st.success("API Key is configured", icon="✅")
    else:
        st.warning("No API Key detected. Please enter your Groq key above or in `.env`.", icon="⚠️")

    st.markdown("---")

    # --- Knowledge Base Info ---
    st.subheader("📚 Knowledge Base")
    selected_model = config.GROQ_MODEL
    try:
        collection = get_cached_collection()
        total_chunks = collection.count()
        st.write(f"**Indexed Chunks:** `{total_chunks}`")
        st.write(f"**Docs Directory:** `{config.DOCS_DIR.name}/`")
        
        # Groq Model Selector
        available_models = [
            "groq/compound",
            "groq/compound-mini",
            "qwen/qwen3.8-27b",
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
        ]
        default_index = available_models.index(config.GROQ_MODEL) if config.GROQ_MODEL in available_models else 0
        selected_model = st.selectbox(
            "Groq AI Model",
            options=available_models,
            index=default_index,
            help="Choose between Groq native models or other models hosted on Groq"
        )
    except Exception:
        total_chunks = 0
        st.error("Database not initialized yet.", icon="⚠️")

    # Button to re-index documents if user added new PDFs
    if st.button("🔄 Re-index All PDFs", use_container_width=True, help="Scan the docs folder and update vector database"):
        with st.spinner("Processing and indexing documents..."):
            try:
                index_documents(force_reindex=True)
                get_cached_collection.clear()
                if hasattr(rag_engine, "reset_chroma_collection"):
                    rag_engine.reset_chroma_collection()
                st.success("Successfully indexed documents!", icon="🎉")
                st.rerun()
            except Exception as e:
                st.error(f"Re-indexing failed: {e}")

    st.markdown("---")

    # --- Chat Actions ---
    st.subheader("🛠️ Chat Controls")
    if st.button("🗑️ Clear Conversation", use_container_width=True, type="secondary"):
        # Reset conversation history back to the initial greeting
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": config.WELCOME_MESSAGE,
                "sources": []
            }
        ]
        st.rerun()

    st.markdown("---")
    st.caption("Built with Groq • ChromaDB • Streamlit")


# ==============================================================================
# 6. MAIN CHAT AREA
# ==============================================================================
# Header display
st.markdown(f"""
<div class="chat-header">
    <div class="chat-title">{config.APP_ICON} {config.APP_TITLE}</div>
    <div class="chat-subtitle">{config.APP_SUBTITLE}</div>
</div>
""", unsafe_allow_html=True)

# Suggested question shortcuts (Chips)
st.write("**💡 Quick Questions:**")
quick_cols = st.columns(3)
sample_questions = [
    "What pricing plans are available?",
    "What is the refund policy?",
    "Why is TaskFlow running slow?"
]

clicked_question = None
for col, q in zip(quick_cols, sample_questions):
    if col.button(q, use_container_width=True):
        clicked_question = q


# ==============================================================================
# 7. RENDER CONVERSATION HISTORY
# ==============================================================================
# Every time the user interacts, Streamlit displays all saved messages
for msg in st.session_state.messages:
    role = msg["role"]
    content = msg["content"]
    sources = msg.get("sources", [])
    unique_sources = msg.get("unique_sources", [])

    with st.chat_message(role):
        st.markdown(content)

        # If this assistant message used document sources, render them neatly
        if unique_sources:
            st.markdown("**📄 Verified Sources:**")
            
            # 1. Render badge tags for instant visibility
            badges_html = '<div class="source-container">'
            for src in unique_sources:
                badges_html += f'<span class="source-badge">📑 {src}</span>'
            badges_html += '</div>'
            st.markdown(badges_html, unsafe_allow_html=True)

            # 2. Render expandable excerpt viewer so the user can verify the text
            with st.expander("🔍 View Retrieved Document Excerpts", expanded=False):
                for idx, src_chunk in enumerate(sources, start=1):
                    doc_name = src_chunk.get("source", "Document")
                    page_num = src_chunk.get("page", "?")
                    excerpt = src_chunk.get("text", "").strip()
                    st.markdown(f"**Excerpt {idx} — {doc_name} (Page {page_num}):**")
                    st.info(excerpt)


# ==============================================================================
# 8. HANDLE USER INPUT & GENERATE RESPONSE
# ==============================================================================
# Accept input from chat_input bar or from a clicked quick question chip
prompt = st.chat_input("Ask a question about TaskFlow documentation...")
active_prompt = prompt or clicked_question

if active_prompt:
    # 1. Append user's question to the chat history
    st.session_state.messages.append({"role": "user", "content": active_prompt})

    # Display user's question immediately
    with st.chat_message("user"):
        st.markdown(active_prompt)

    # 2. Generate assistant answer with a friendly spinner
    with st.chat_message("assistant"):
        with st.spinner("Searching documentation and synthesizing answer..."):
            result = answer_question(
                active_prompt,
                api_key=effective_key,
                model=selected_model,
                history=st.session_state.messages
            )


        answer_text = result["answer"]
        sources = result.get("sources", [])
        unique_sources = result.get("unique_sources", [])

        # Display the generated answer
        st.markdown(answer_text)

        # Display source document citations cleanly if available
        if unique_sources:
            st.markdown("**📄 Verified Sources:**")
            badges_html = '<div class="source-container">'
            for src in unique_sources:
                badges_html += f'<span class="source-badge">📑 {src}</span>'
            badges_html += '</div>'
            st.markdown(badges_html, unsafe_allow_html=True)

            with st.expander("🔍 View Retrieved Document Excerpts", expanded=False):
                for idx, src_chunk in enumerate(sources, start=1):
                    doc_name = src_chunk.get("source", "Document")
                    page_num = src_chunk.get("page", "?")
                    excerpt = src_chunk.get("text", "").strip()
                    st.markdown(f"**Excerpt {idx} — {doc_name} (Page {page_num}):**")
                    st.info(excerpt)

        # 3. Save assistant's answer and sources into session state
        st.session_state.messages.append({
            "role": "assistant",
            "content": answer_text,
            "sources": sources,
            "unique_sources": unique_sources
        })
