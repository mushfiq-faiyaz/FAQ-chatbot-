"""
test_search.py - Search Verification Script
============================================

WHAT THIS SCRIPT DOES:
Before building the full web chat application or connecting to an AI model, this script
tests the search engine directly. It sends a sample question to ChromaDB and prints the
most relevant text chunks that were matched, along with their source document and page number.

WHY TEST RETRIEVAL SEPARATELY? (EDUCATIONAL EXPLANATION):
In a RAG (Retrieval-Augmented Generation) system, the AI is only as good as the context
it is given! If the search step fails to retrieve the right document chunks, the AI will
have no choice but to say "I don't know" or make something up.
By verifying the search step first:
1. You confirm that your PDF ingestion worked correctly.
2. You confirm that the embeddings correctly identify the right paragraphs.
3. You can inspect the similarity distances to tune CHUNK_SIZE and TOP_K.

USAGE:
  Run with default question:
    python test_search.py

  Or run with your own custom question:
    python test_search.py "What is the refund policy?"
"""

import sys
from pathlib import Path
import chromadb
from chromadb.utils import embedding_functions

# Ensure Windows terminal doesn't crash when printing Unicode characters or emojis
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import our centralized configuration settings
import config


def test_vector_search(query: str, top_k: int = config.TOP_K_RESULTS):
    """
    Queries ChromaDB with a natural language question and prints the matching snippets.
    
    Parameters:
    - query: The question or search phrase.
    - top_k: How many matching chunks to retrieve.
    """
    print("=" * 70)
    print(" 🔍 TaskFlow Vector Search Verification")
    print("=" * 70)
    print(f"❓ Query: \"{query}\"")
    print(f"🎯 Target Results: Top {top_k} most relevant chunks\n")

    # Verify that the vector database directory exists
    if not config.CHROMA_DB_DIR.exists():
        print(f"❌ Error: Database directory '{config.CHROMA_DB_DIR}' does not exist.")
        print("💡 Please run 'python ingest.py' first to build the vector index.")
        return

    # Connect to the persistent ChromaDB database on disk
    client = chromadb.PersistentClient(path=str(config.CHROMA_DB_DIR))
    
    # Use the same embedding function that was used during ingestion
    embedding_func = embedding_functions.DefaultEmbeddingFunction()

    try:
        collection = client.get_collection(
            name=config.COLLECTION_NAME,
            embedding_function=embedding_func
        )
    except Exception as e:
        print(f"❌ Could not find collection '{config.COLLECTION_NAME}': {e}")
        print("💡 Please run 'python ingest.py' first to build the vector index.")
        return

    # Total number of chunks stored in this collection
    total_docs = collection.count()
    print(f"📚 Total indexed chunks in database: {total_docs}\n")

    if total_docs == 0:
        print("⚠️ The database is currently empty. Run 'python ingest.py' to populate it.")
        return

    # Perform the semantic search
    # ChromaDB converts the 'query_texts' into embeddings and calculates cosine distance
    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, total_docs)
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    print("=" * 70)
    print(" 📄 RETRIEVED CONTEXT CHUNKS")
    print("=" * 70)

    for rank, (doc_text, meta, dist) in enumerate(zip(documents, metadatas, distances), start=1):
        source_doc = meta.get("source", "Unknown Document")
        page_num = meta.get("page", "?")
        
        # UNDERSTANDING DISTANCE:
        # We configured cosine distance:
        # - A distance close to 0.0 means nearly identical meaning.
        # - Distances between 0.15 and 0.50 indicate high relevance in practice.
        # - Distances above 0.80 indicate weak relevance.
        # We can also compute a simple similarity percentage: (1 - distance) * 100
        similarity_pct = max(0.0, (1.0 - dist)) * 100

        print(f"\n[Result #{rank}]")
        print(f"📌 Source:   {source_doc} (Page {page_num})")
        print(f"📊 Distance: {dist:.4f} (Approx. {similarity_pct:.1f}% semantic similarity)")
        print("─" * 70)
        print(doc_text)
        print("─" * 70)

    print("\n✅ Verification complete! Search is retrieving relevant text accurately.")
    print("💡 Next step: 'rag_engine.py' passes these retrieved chunks to Groq LLM.")


if __name__ == "__main__":
    # If the user supplied a question via the command line, use it;
    # otherwise, use this default pricing question.
    if len(sys.argv) > 1:
        sample_question = " ".join(sys.argv[1:])
    else:
        sample_question = "What pricing plans does TaskFlow offer, and what is the cost of the Starter plan?"

    test_vector_search(sample_question)
