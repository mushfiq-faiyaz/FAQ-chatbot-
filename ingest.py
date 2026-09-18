"""
ingest.py - Document Ingestion & Vector Embedding Pipeline
===========================================================

WHAT THIS SCRIPT DOES:
This script prepares your PDF documents for the AI chatbot. It runs in three stages:
  1. SCAN & READ: Finds all PDF files in the 'docs/' directory and extracts their text
     page-by-page using pdfplumber.
  2. CHUNK: Breaks large pages of text into smaller, overlapping segments so the search
     engine can pinpoint exact paragraphs without losing context.
  3. EMBED & STORE: Converts each text chunk into an 'embedding' (a list of numbers
     capturing the conceptual meaning of the text) and stores them in ChromaDB.

WHY THIS STEP IS NEEDED (EDUCATIONAL EXPLANATION):
- An LLM cannot read 500 pages of PDFs on every single user question — it would be too
  slow, too expensive, and exceed token limits.
- Instead, we perform "Retrieval-Augmented Generation" (RAG).
- First, we index the documents here. Later, when a user asks a question, we only send
  the 3-4 most relevant snippets to the AI.
- Embeddings allow us to do "semantic search": searching by meaning rather than exact
  keyword matching. For example, a search for "cost" will successfully match a chunk
  discussing "pricing", even if the word "cost" never appears!
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

# Ensure Windows terminal doesn't crash when printing Unicode characters or emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import pdfplumber
import chromadb
from chromadb.utils import embedding_functions

# Import our centralized configuration settings
import config


def find_pdf_files(docs_dir: Path = config.DOCS_DIR) -> List[Path]:
    """
    Scans the documents directory and all subdirectories for PDF files (.pdf).
    Using recursive search (rglob) ensures that documents placed in subfolders
    (like 'docs/taskflow/') are automatically found.
    """
    if not docs_dir.exists():
        print(f"❌ Error: The documents folder '{docs_dir}' does not exist.")
        return []
    
    pdf_files = sorted(list(docs_dir.rglob("*.pdf")))
    return pdf_files


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Reads a single PDF file and extracts text page by page.
    
    Why page-by-page?
    By recording the page number for each chunk, our chatbot can tell the user
    exact references like "Found in TaskFlow_Pricing_Plans.pdf, Page 2", making
    answers verifiable and trustworthy!
    """
    pages_data = []
    filename = pdf_path.name

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                raw_text = page.extract_text()
                
                # Check if the page contains extractable text
                if raw_text and raw_text.strip():
                    pages_data.append({
                        "source": filename,
                        "page": page_idx,
                        "filepath": str(pdf_path.relative_to(config.BASE_DIR)),
                        "text": raw_text.strip()
                    })
    except Exception as e:
        print(f"⚠️ Warning: Failed to read {pdf_path.name}: {e}")

    return pages_data


def split_text_into_chunks(
    text: str,
    chunk_size: int = config.CHUNK_SIZE,
    chunk_overlap: int = config.CHUNK_OVERLAP
) -> List[str]:
    """
    Splits a body of text into smaller chunks with a sliding overlap.
    
    Why do we need overlap?
    Imagine a sentence is cut in half at the chunk boundary:
      Chunk 1: "...the Enterprise plan costs"
      Chunk 2: "$99/month and includes SSO..."
    Neither chunk alone answers "How much is Enterprise?".
    With overlap, Chunk 2 includes the tail of Chunk 1, ensuring no context is lost!
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        # Define the end position for the current chunk
        end = start + chunk_size
        
        # If we are not at the very end of the text, try to break at a natural
        # boundary (a space or newline) so we don't cut words in half.
        if end < text_len:
            # Look backwards from 'end' up to 60 characters for a whitespace or period
            boundary = text.rfind(" ", start, end)
            newline_boundary = text.rfind("\n", start, end)
            best_boundary = max(boundary, newline_boundary)
            
            # If a clean boundary was found reasonably close, use it
            if best_boundary != -1 and best_boundary > start + (chunk_size // 2):
                end = best_boundary
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        # Move forward by (chunk_size - overlap)
        # If we reached the end of the text, break out of the loop
        if end >= text_len:
            break
            
        start = max(start + 1, end - chunk_overlap)
        
    return chunks


def prepare_documents_for_indexing(docs_dir: Path = config.DOCS_DIR) -> List[Dict[str, Any]]:
    """
    Reads all PDFs from the specified directory, breaks each page into overlapping chunks,
    and attaches rich metadata (source document, page number, chunk index).
    """
    pdf_files = find_pdf_files(docs_dir)
    
    if not pdf_files:
        print(f"⚠️ No PDF files found in '{docs_dir}'.")
        return []

    print(f"📂 Found {len(pdf_files)} PDF document(s) to process:")
    for pdf_file in pdf_files:
        print(f"   - {pdf_file.name}")

    all_chunks = []
    total_pages = 0

    for pdf_file in pdf_files:
        pages = extract_text_from_pdf(pdf_file)
        total_pages += len(pages)
        
        for page_data in pages:
            page_chunks = split_text_into_chunks(
                page_data["text"],
                chunk_size=config.CHUNK_SIZE,
                chunk_overlap=config.CHUNK_OVERLAP
            )
            
            for chunk_idx, chunk_text in enumerate(page_chunks):
                # Unique identifier for every chunk in ChromaDB
                chunk_id = f"{page_data['source']}_p{page_data['page']}_c{chunk_idx}"
                
                all_chunks.append({
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": {
                        "source": page_data["source"],
                        "page": int(page_data["page"]),
                        "filepath": page_data["filepath"],
                        "chunk_index": chunk_idx
                    }
                })

    print(f"\n📑 Extracted {total_pages} pages in total.")
    print(f"✂️  Created {len(all_chunks)} searchable text chunks.")
    return all_chunks


def is_chroma_db_empty_or_missing() -> bool:
    """
    Checks whether the ChromaDB vector database directory is missing or empty.

    WHY THIS CHECK IS NEEDED FOR CLOUD DEPLOYMENT (STREAMLIT CLOUD):
    ----------------------------------------------------------------
    1. Git Ignores Large Vector Files:
       The ChromaDB vector database folder ('chroma_db/') stores local SQLite and
       index files containing vector embeddings. To keep git repositories lightweight
       and avoid syncing large binaries, 'chroma_db/' is listed in .gitignore.

    2. Streamlit Cloud Starts Clean:
       When deployed on Streamlit Cloud, Streamlit clones the repository directly from
       GitHub. Because 'chroma_db/' is not in git, the folder does not exist on the
       cloud server.

    3. No Interactive Terminal on Cloud:
       In local development, you can run 'python ingest.py' once in the terminal.
       On Streamlit Cloud, there is no terminal to run manual commands before starting
       the web server. The app starts immediately by executing 'app.py'.

    4. Self-Healing Startup:
       By checking if the ChromaDB folder is missing or empty upon startup, the app
       can automatically detect first-time launch, extract text from PDFs in 'docs/',
       generate embeddings, and populate ChromaDB on the fly before users start chatting.

    Returns:
    - bool: True if the database is missing, empty, or uninitialized; False otherwise.
    """
    # 1. Directory does not exist
    if not config.CHROMA_DB_DIR.exists():
        return True

    # 2. Directory exists but is empty or missing sqlite database file
    try:
        contents = list(config.CHROMA_DB_DIR.iterdir())
        if not contents:
            return True
        sqlite_file = config.CHROMA_DB_DIR / "chroma.sqlite3"
        if not sqlite_file.exists():
            return True

        # 3. Collection does not exist or contains 0 items
        client = chromadb.PersistentClient(path=str(config.CHROMA_DB_DIR))
        existing_collections = [c.name for c in client.list_collections()]
        if config.COLLECTION_NAME not in existing_collections:
            return True
        collection = client.get_collection(name=config.COLLECTION_NAME)
        if collection.count() == 0:
            return True
    except Exception:
        # If any error occurs reading the DB (e.g. corrupted files), treat as empty
        return True

    return False


def index_documents(force_reindex: bool = True, docs_dir: Path = config.DOCS_DIR) -> int:
    """
    Connects to ChromaDB, generates embeddings for each chunk, and saves them to disk.
    
    This function is designed to be reusable:
    - Run standalone: python ingest.py
    - Called from web apps: invoked during app.py startup or via a 'Re-index' button.

    Parameters:
    - force_reindex (bool): If True, deletes any previous collection of the same name and
      re-indexes from scratch. This guarantees that deleted or modified documents
      are updated cleanly.
    - docs_dir (Path): The directory containing source PDF documents (defaults to config.DOCS_DIR).

    Returns:
    - int: The total number of chunks indexed into ChromaDB.
    """
    chunks = prepare_documents_for_indexing(docs_dir)
    if not chunks:
        print("❌ No text chunks to index. Exiting.")
        return 0

    print(f"\n📦 Initializing ChromaDB vector database at: {config.CHROMA_DB_DIR}")
    # PersistentClient saves data directly to a local directory on your hard drive
    client = chromadb.PersistentClient(path=str(config.CHROMA_DB_DIR))
    
    # We use ChromaDB's default embedding function (ONNX runtime running all-MiniLM-L6-v2)
    # This runs 100% locally on your CPU, fast, free, and needs no external API or key!
    embedding_func = embedding_functions.DefaultEmbeddingFunction()

    # If reindexing, remove existing collection to avoid stale duplicates
    existing_collections = [c.name for c in client.list_collections()]
    if force_reindex and config.COLLECTION_NAME in existing_collections:
        print(f"🔄 Clearing previous index '{config.COLLECTION_NAME}'...")
        client.delete_collection(name=config.COLLECTION_NAME)

    # Create or get the collection
    collection = client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=embedding_func,
        metadata={"hnsw:space": "cosine"}  # Use cosine similarity for text comparison
    )

    # Prepare batch lists for ChromaDB insertion
    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    print(f"🧠 Generating vector embeddings and storing {len(documents)} chunks...")
    # ChromaDB processes batches efficiently
    batch_size = 50
    for i in range(0, len(ids), batch_size):
        batch_ids = ids[i : i + batch_size]
        batch_docs = documents[i : i + batch_size]
        batch_meta = metadatas[i : i + batch_size]
        collection.add(
            ids=batch_ids,
            documents=batch_docs,
            metadatas=batch_meta
        )
        print(f"   Indexed {min(i + batch_size, len(ids))}/{len(ids)} chunks...")

    print(f"\n🎉 SUCCESS! All {len(ids)} chunks have been successfully embedded and indexed.")
    print(f"📁 Database saved to: {config.CHROMA_DB_DIR}")
    print("💡 You can now run 'python test_search.py' to test search queries against this index!")
    return len(ids)


if __name__ == "__main__":
    print("=" * 60)
    print(" TaskFlow Document Ingestion & Embedding Pipeline")
    print("=" * 60)
    total_indexed = index_documents(force_reindex=True)
    print(f"✅ Ingestion complete. Total chunks indexed: {total_indexed}")
