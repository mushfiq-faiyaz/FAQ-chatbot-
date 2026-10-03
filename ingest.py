"""
ingest.py - Document Ingestion & Vector Embedding Pipeline
===========================================================

WHAT THIS SCRIPT DOES:
This script prepares your PDF documents for the AI chatbot. It runs in three stages:
  1. SCAN & READ: Finds all PDF files in the 'docs/' directory and extracts their text
     page-by-page using pdfplumber with table-aware formatting.
  2. CHUNK: Breaks large pages of text into smaller, overlapping segments so the search
     engine can pinpoint exact paragraphs without losing context.
  3. EMBED & STORE: Converts each text chunk into an 'embedding' and stores them in ChromaDB.
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
    """
    if not docs_dir.exists():
        print(f"❌ Error: The documents folder '{docs_dir}' does not exist.")
        return []
    
    pdf_files = sorted(list(docs_dir.rglob("*.pdf")))
    return pdf_files


def format_table_to_markdown_and_breakdown(table_data: List[List[Any]]) -> str:
    """
    Converts raw table rows from pdfplumber into clean Markdown and plan-by-plan
    structured text to ensure columns and plans are never mixed up during semantic search.
    """
    if not table_data:
        return ""
    
    clean_table = []
    for row in table_data:
        clean_row = []
        for cell in row:
            if cell is None:
                clean_row.append("")
            else:
                c_str = " ".join(str(cell).replace("\n", " ").split())
                if c_str in ("—", "", "-", "N/A"):
                    c_str = "None"
                clean_row.append(c_str)
        clean_table.append(clean_row)
    
    if not clean_table or not any(clean_table):
        return ""

    # Ensure header row has a meaningful first column label
    if not clean_table[0][0] or clean_table[0][0] == "None":
        clean_table[0][0] = "Feature / Plan"
    if len(clean_table) > 1 and (not clean_table[1][0] or clean_table[1][0] == "None"):
        clean_table[1][0] = "Price"

    # Standardize column count across all rows
    col_count = max(len(r) for r in clean_table)
    for r in clean_table:
        while len(r) < col_count:
            r.append("")

    col_widths = [max(len(r[c]) for r in clean_table) for c in range(col_count)]
    
    # 1. Build Markdown Table
    lines = []
    header = "| " + " | ".join(clean_table[0][c].ljust(col_widths[c]) for c in range(col_count)) + " |"
    sep = "| " + " | ".join("-" * max(3, col_widths[c]) for c in range(col_count)) + " |"
    lines.append(header)
    lines.append(sep)
    for row in clean_table[1:]:
        lines.append("| " + " | ".join(row[c].ljust(col_widths[c]) for c in range(col_count)) + " |")

    # 2. Build Plan-by-Plan Feature Breakdown
    plan_headers = clean_table[0][1:]
    plan_summaries = []
    for p_idx, plan_name in enumerate(plan_headers, start=1):
        if not plan_name.strip():
            continue
        attrs = []
        for r_idx in range(1, len(clean_table)):
            feat_name = clean_table[r_idx][0]
            val = clean_table[r_idx][p_idx]
            attrs.append(f"{feat_name}: {val}")
        plan_summaries.append(f"- Plan {plan_name}: {'; '.join(attrs)}")

    md_table = "\n".join(lines)
    breakdown = "\n".join(plan_summaries)
    return f"\n\n[PRICING & FEATURES TABLE]\n{md_table}\n\n[DETAILED PLAN BREAKDOWN]\n{breakdown}\n\n"


def extract_page_text_with_tables(page: pdfplumber.page.Page) -> str:
    """
    Extracts text from a PDF page while preserving table structures intact.
    """
    tables = page.find_tables()
    if not tables:
        return page.extract_text() or ""

    # Sort tables top-to-bottom
    sorted_tables = sorted(tables, key=lambda t: t.bbox[1])
    parts = []
    last_bottom = 0

    for t in sorted_tables:
        bbox = t.bbox
        # Crop and extract text appearing above this table
        if bbox[1] > last_bottom:
            above_crop = page.crop((0, last_bottom, page.width, bbox[1]))
            above_text = above_crop.extract_text()
            if above_text and above_text.strip():
                parts.append(above_text.strip())

        # Extract and format the structured table
        t_data = t.extract()
        formatted_t = format_table_to_markdown_and_breakdown(t_data)
        if formatted_t.strip():
            parts.append(formatted_t.strip())

        last_bottom = max(last_bottom, bbox[3])

    # Crop and extract text appearing below the last table
    if last_bottom < page.height:
        below_crop = page.crop((0, last_bottom, page.width, page.height))
        below_text = below_crop.extract_text()
        if below_text and below_text.strip():
            parts.append(below_text.strip())

    return "\n\n".join(parts)


def extract_text_from_pdf(pdf_path: Path) -> List[Dict[str, Any]]:
    """
    Reads a single PDF file and extracts text page by page with table awareness.
    """
    pages_data = []
    filename = pdf_path.name

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                raw_text = extract_page_text_with_tables(page)
                
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
    Splits a body of text into smaller chunks with a sliding overlap,
    respecting paragraph and newline boundaries where possible.
    """
    if not text:
        return []
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = start + chunk_size
        
        # If not at end of text, find a natural boundary (preferring paragraph or line breaks)
        if end < text_len:
            double_nl = text.rfind("\n\n", start, end)
            single_nl = text.rfind("\n", start, end)
            space_boundary = text.rfind(" ", start, end)
            
            if double_nl != -1 and double_nl > start + (chunk_size // 3):
                end = double_nl
            elif single_nl != -1 and single_nl > start + (chunk_size // 2):
                end = single_nl
            elif space_boundary != -1 and space_boundary > start + (chunk_size // 2):
                end = space_boundary
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
            
        if end >= text_len:
            break
            
        start = max(start + 1, end - chunk_overlap)
        
    return chunks


def prepare_documents_for_indexing(docs_dir: Path = config.DOCS_DIR) -> List[Dict[str, Any]]:
    """
    Reads all PDFs from the specified directory, breaks each page into overlapping chunks,
    and attaches rich metadata.
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
    """
    if not config.CHROMA_DB_DIR.exists():
        return True

    try:
        contents = list(config.CHROMA_DB_DIR.iterdir())
        if not contents:
            return True
        sqlite_file = config.CHROMA_DB_DIR / "chroma.sqlite3"
        if not sqlite_file.exists():
            return True

        client = chromadb.PersistentClient(path=str(config.CHROMA_DB_DIR))
        existing_collections = [c.name for c in client.list_collections()]
        if config.COLLECTION_NAME not in existing_collections:
            return True
        collection = client.get_collection(name=config.COLLECTION_NAME)
        if collection.count() == 0:
            return True
    except Exception:
        return True

    return False


def index_documents(force_reindex: bool = True, docs_dir: Path = config.DOCS_DIR) -> int:
    """
    Connects to ChromaDB, generates embeddings for each chunk, and saves them to disk.
    """
    chunks = prepare_documents_for_indexing(docs_dir)
    if not chunks:
        print("❌ No text chunks to index. Exiting.")
        return 0

    print(f"\n📦 Initializing ChromaDB vector database at: {config.CHROMA_DB_DIR}")
    client = chromadb.PersistentClient(path=str(config.CHROMA_DB_DIR))
    embedding_func = embedding_functions.DefaultEmbeddingFunction()

    existing_collections = [c.name for c in client.list_collections()]
    if force_reindex and config.COLLECTION_NAME in existing_collections:
        print(f"🔄 Clearing previous index '{config.COLLECTION_NAME}'...")
        client.delete_collection(name=config.COLLECTION_NAME)

    collection = client.get_or_create_collection(
        name=config.COLLECTION_NAME,
        embedding_function=embedding_func,
        metadata={"hnsw:space": "cosine"}
    )

    ids = [chunk["id"] for chunk in chunks]
    documents = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    print(f"🧠 Generating vector embeddings and storing {len(documents)} chunks...")
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
    return len(ids)


if __name__ == "__main__":
    print("=" * 60)
    print(" LedgerFlow Document Ingestion & Embedding Pipeline")
    print("=" * 60)
    total_indexed = index_documents(force_reindex=True)
    print(f"✅ Ingestion complete. Total chunks indexed: {total_indexed}")
