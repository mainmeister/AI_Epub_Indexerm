# EPUB Indexer & Literary Intelligence Suite

A high-throughput, resource-efficient EPUB cataloguer, search engine, and AI-powered literary analysis toolkit. Designed to maximize the utility and discoverability of digital libraries while minimizing computational overhead through parallel processing, zero external Python dependencies, and persistent SQLite caching.

---

## Key Capabilities

- **Zero-Dependency Core**: Built entirely on Python standard libraries (`sqlite3`, `zipfile`, `xml.etree.ElementTree`, `urllib.request`, `concurrent.futures`).
- **High-Performance Ingestion**: Parallelized multi-core metadata extraction from EPUB archives ([`META-INF/container.xml`](https://www.w3.org/publishing/epub32/epub-ocf.html#sec-container-metainf) and [OPF package documents](https://www.w3.org/publishing/epub32/epub-packages.html)) with automatic orphan record pruning.
- **Full-Text Search (FTS5)**: Fast [BM25](https://en.wikipedia.org/wiki/Okapi_BM25)-ranked keyword querying (using SQLite's built-in Okapi BM25 probabilistic ranking function to score and order results by relevance based on term frequency and document length) across titles, authors, subjects, and descriptions using [SQLite FTS5](https://www.sqlite.org/fts5.html) virtual tables and automatic synchronization triggers.
- **Semantic Vector Search**: [Dense vector retrieval](https://en.wikipedia.org/wiki/Vector_search) powered by local [`nomic-embed-text`](https://ollama.com/library/nomic-embed-text) embeddings stored directly in SQLite as normalized binary float buffers.
- **The Literary Sommelier (RAG Recommender)**: Conversational, persona-driven book recommendations ("Dr. Watson" via [`llama3.2:1b`](https://ollama.com/library/llama3.2)) grounded in [Retrieval-Augmented Generation (RAG)](https://en.wikipedia.org/wiki/Retrieval-augmented_generation) semantic vector search context.
- **The Reader's Dossier**: Instant structured analysis covering plot hooks, tone/atmosphere, and read-alike recommendations via [`llama3.2:1b`](https://ollama.com/library/llama3.2).
- **Visual Cover Art Analysis**: On-demand extraction and multimodal visual inspection of cover artwork via [`moondream`](https://ollama.com/library/moondream).
- **Structured JSON Auto-Tagger**: Automatic extraction and catalog enrichment of genre and thematic tags via [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5).
- **Persistent Result Caching**: Stores generated dossiers, visual analyses, embeddings, and recommendations to eliminate redundant inference and maximize computational efficiency.

---

## System Requirements & Prerequisites

### 1. Python Environment
- Python 3.8+ with [SQLite3 FTS5 module](https://www.sqlite.org/fts5.html) enabled (standard in modern distributions).
- No external `pip` packages required.

### 2. Ollama & Local Models
Ensure [Ollama](https://ollama.com) is running locally at `http://127.0.0.1:11434` with the necessary models pulled:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2:1b
ollama pull moondream
ollama pull qwen2.5:1.5b
```

#### Model Sources & References
- [`nomic-embed-text`](https://ollama.com/library/nomic-embed-text) — High-dimensional (768d) 8192-token context text embedding model by [Nomic AI](https://www.nomic.ai).
- [`llama3.2:1b`](https://ollama.com/library/llama3.2) — Lightweight multilingual large language model optimized for edge devices and instruction following by [Meta AI](https://ai.meta.com/llama/).
- [`moondream`](https://ollama.com/library/moondream) — Small-footprint multimodal vision-language model for image description and visual question answering by [Moondream](https://moondream.ai).
- [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5) — Compact instruction-tuned LLM optimized for structured JSON generation and tagging by [Qwen / Alibaba Cloud](https://github.com/QwenLM/Qwen2.5).

---

## Database Architecture

The application utilizes SQLite with Write-Ahead Logging ([`PRAGMA journal_mode = WAL`](https://www.sqlite.org/wal.html)) and optimized memory caches for rapid queries and concurrent access:

- `books`: Primary catalog storing file metadata (path, title, author, publisher, publication date, language, identifiers, subjects, description, file size).
- `books_fts`: [SQLite FTS5](https://www.sqlite.org/fts5.html) virtual table synchronized via `INSERT`, `UPDATE`, and `DELETE` triggers.
- `book_embeddings`: Binary float blobs of normalized vector embeddings mapped to book IDs.
- `book_dossiers`: Cached literary analysis dossiers.
- `book_covers`: Cached multimodal visual inspection transcripts.
- `recommendation_cache`: Cached RAG recommendation query outputs.

---

## Command-Line Usage

### 1. Scanning and Cataloguing
Discover EPUB files, extract metadata across CPU cores, and build the database index:

```bash
# Scan default directory (./epub) into default database (./epub_catalog.db)
python3 epub_indexer.py --scan

# Scan custom directory and database path with specific worker count
python3 epub_indexer.py --scan --dir /path/to/epubs --db /path/to/catalog.db --workers 8
```

### 2. Generating Vector Embeddings
Compute normalized embeddings for all pending books:

```bash
# Generate vector embeddings in batches of 50
python3 epub_indexer.py --embed

# Custom batch size or limit
python3 epub_indexer.py --embed --batch-size 100 --limit 500
```

### 3. Incremental Maintenance
Scan for new/removed EPUB files and compute missing embeddings in one workflow:

```bash
python3 epub_indexer.py --update
```

### 4. Full-Text Search (FTS5)
Search by keywords or FTS5 boolean expressions, ranked by relevance using SQLite's built-in [BM25](https://en.wikipedia.org/wiki/Okapi_BM25) ranking function:

```bash
python3 epub_indexer.py --search "dystopia OR surveillance" --limit 20
python3 epub_indexer.py --search "Arthur Conan Doyle"

# Export matching EPUB file paths to a file
python3 epub_indexer.py --search "Arthur Conan Doyle" --output matched_books.txt
```

### 5. Semantic Vector Search
Retrieve volumes based on conceptual or thematic natural language queries:

```bash
python3 epub_indexer.py --semantic-search "hard science fiction involving generational starships" --limit 10

# Export semantic search results to a file
python3 epub_indexer.py --semantic-search "cyberpunk artificial intelligence" -o results.txt
```

### 6. The Literary Sommelier (RAG Recommender)
Get conversational recommendations synthesizing library holdings:

```bash
python3 epub_indexer.py --ask "I want an atmospheric Victorian gothic mystery with supernatural undertones"

# Bypass cached recommendation to force regeneration and save referenced EPUB paths
python3 epub_indexer.py --ask "philosophical cyberpunk stories" --refresh --output picks.txt
```

### 7. Reader's Dossier
Generate or view structured reading briefs by Book ID, exact title, partial title, or filename:

```bash
python3 epub_indexer.py --dossier "Frankenstein"
python3 epub_indexer.py --dossier 42 --refresh
```

### 8. Visual Cover Art Analysis
Inspect and transcribe jacket artwork using the multimodal vision model:

```bash
python3 epub_indexer.py --cover "Dune"
```

### 9. Automatic Genre/Thematic Tagging
Extract standardized tags and permanently update the catalog and FTS index:

```bash
python3 epub_indexer.py --autotag "Neuromancer"
```

### 10. Library Statistics
Inspect catalog health, metadata completeness, embedding coverage, and top tags:

```bash
python3 epub_indexer.py --stats
```

---

## Options Summary

| Argument | Description | Default |
|---|---|---|
| `--scan` | Scans EPUB files and indexes metadata into SQLite | `False` |
| `--embed` | Generates vector embeddings for unindexed books | `False` |
| `--update` | Executes incremental scan and embedding pipeline | `False` |
| `--search <QUERY>` | Queries catalog using SQLite FTS5 | `None` |
| `--semantic-search <QUERY>` | Queries catalog via dense vector cosine similarity | `None` |
| `--ask <QUERY>` | Requests RAG recommendations from Dr. Watson | `None` |
| `--dossier <TARGET>` | Generates/displays Reader's Dossier (by ID or Title) | `None` |
| `--cover <TARGET>` | Analyzes EPUB cover artwork via Moondream (by ID or Title) | `None` |
| `--autotag <TARGET>` | Generates JSON tags via Qwen2.5 and updates database | `None` |
| `--stats` | Displays catalog statistics and cache health | `False` |
| `--refresh` | Forces regeneration of cached AI outputs | `False` |
| `--dir <PATH>` | Target directory containing EPUB archives | `./epub` |
| `--db <PATH>` | SQLite database file location | `./epub_catalog.db` |
| `--limit <INT>` | Maximum search results or processed records | `30` |
| `--output <PATH>`, `-o <PATH>` | Output file path to save matching EPUB file paths | `None` |
| `--batch-size <INT>` | Batch size for Ollama embedding generation | `50` |
| `--workers <INT>` | Worker process count for parallel metadata extraction | `CPU count` |
