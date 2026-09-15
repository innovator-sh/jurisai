"""Ported from jurisai/Backend/app.py, relocated only — no behaviour change.

Still one hardcoded IPC corpus, still Chroma, still ingests synchronously at app
startup instead of a decoupled CLI. All three are tracked, open issues fixed in
Sprint 3 (corpus registry, Qdrant, `scripts/ingest.py` as its own entrypoint) —
this sprint only moves the framework from Flask's import-time execution to a
FastAPI lifespan hook, which is the mechanical equivalent for this framework.

Also fixes D033 (deprecated pre-0.1 `langchain.*` import paths) as an
unavoidable side effect: those modules don't exist in a current LangChain
install, so a faithful *working* port has to use the `langchain_community`
paths. The chunking strategy and vector store themselves are unchanged.
"""

import os

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.logging import get_logger

logger = get_logger(__name__)

DATA_DIR = "data/ipc"
PERSIST_DIRECTORY = "db"


def build_or_load_vector_store() -> Chroma:
    embeddings = SentenceTransformerEmbeddings(model_name="multi-qa-mpnet-base-dot-v1")
    logger.info("embeddings_initialized")

    if os.path.exists(PERSIST_DIRECTORY) and os.listdir(PERSIST_DIRECTORY):
        logger.info("using_existing_chromadb")
        return Chroma(persist_directory=PERSIST_DIRECTORY, embedding_function=embeddings)

    logger.info("no_existing_db_processing_pdfs")
    if not os.path.exists(DATA_DIR):
        raise FileNotFoundError(f"Directory not found: {DATA_DIR}. Add the IPC source PDF there.")

    # langchain-community's DirectoryLoader stub only lists a few loader_cls
    # options; PyPDFLoader is a valid runtime argument the stub doesn't cover.
    loader = DirectoryLoader(DATA_DIR, glob="*.pdf", loader_cls=PyPDFLoader)  # type: ignore[arg-type]
    documents = loader.load()
    if not documents:
        raise ValueError(f"No PDFs found in {DATA_DIR}")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=200)
    texts = text_splitter.split_documents(documents)
    vector_db = Chroma.from_documents(texts, embeddings, persist_directory=PERSIST_DIRECTORY)
    logger.info("chromadb_initialized", pdf_count=len(documents), chunk_count=len(texts))
    return vector_db
