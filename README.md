# EPUB Indexer & Literary Intelligence Suite

A high-throughput, resource-efficient EPUB cataloguer, search engine, and AI-powered literary analysis toolkit. Designed to maximize the utility and discoverability of digital libraries while minimizing computational overhead through parallel processing, zero external Python dependencies, and persistent SQLite caching.

---

## Table of Contents

- **[Part 1: Installation & User Guide](#part-1-installation--user-guide)**
  - [Overview of Capabilities](#overview-of-capabilities)
  - [System Requirements & Installation](#system-requirements--installation)
  - [Quick-Start Workflow](#quick-start-workflow)
  - [User Guide & Command Reference](#user-guide--command-reference)
  - [CLI Options Summary](#cli-options-summary)
- **[Part 2: Technical Architecture & Developer Reference](#part-2-technical-architecture--developer-reference)**
  - [1. System Architecture & Execution Pipeline](#1-system-architecture--execution-pipeline)
  - [2. EPUB OCF/OPF Parsing & Multiprocess Ingestion](#2-epub-ocfopf-parsing--multiprocess-ingestion)
  - [3. SQLite Engine Tuning, Relational Schema & FTS5 Internals](#3-sqlite-engine-tuning-relational-schema--fts5-internals)
  - [4. Dense Vector Representation & Cosine Similarity Engine](#4-dense-vector-representation--cosine-similarity-engine)
  - [5. Local LLM/VLM Inference Contracts & RAG Pipeline](#5-local-llmvlm-inference-contracts--rag-pipeline)
  - [6. Entity Resolution, Caching & Extension Guide](#6-entity-resolution-caching--extension-guide)

---

# Part 1: Installation & User Guide

## Overview of Capabilities

- **Zero-Dependency Core**: Runs out-of-the-box on standard Python 3.8+ without `pip` packages or virtual environments.
- **Fast Multi-Core Cataloguing**: Scans thousands of EPUB files in parallel, extracting titles, authors, publishers, publication dates, identifiers, subjects, and synopses while automatically pruning deleted files.
- **Full-Text Search (FTS5)**: Instant keyword and boolean search across titles, authors, subjects, and book descriptions ranked by relevance ([Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25)).
- **Semantic Vector Search**: Natural language conceptual search powered by [`nomic-embed-text`](https://ollama.com/library/nomic-embed-text) dense embeddings.
- **The Literary Sommelier (`--ask`)**: Conversational book recommendations in the persona of Dr. John H. Watson ([`llama3.2:1b`](https://ollama.com/library/llama3.2)), grounded in your actual library holdings via [Retrieval-Augmented Generation (RAG)](https://en.wikipedia.org/wiki/Retrieval-augmented_generation).
- **The Reader's Dossier (`--dossier`)**: Instant structured reading briefs covering premise/hook, tone/atmosphere, and comparable works.
- **Visual Cover Art Analysis (`--cover`)**: Extracts jacket artwork directly from the EPUB archive and performs visual description and text transcription via [`moondream`](https://ollama.com/library/moondream).
- **Automated Genre & Theme Tagging (`--autotag`)**: Enriches book metadata with standardized genre and thematic tags using [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5).
- **Persistent Caching**: Saves embeddings, dossiers, cover analyses, and recommendations in SQLite for instant subsequent retrieval.

---

## System Requirements & Installation

### 1. Python Environment
- **Python 3.8+** with the built-in `sqlite3` module compiled with [FTS5 support](https://www.sqlite.org/fts5.html) (enabled by default in modern Linux, macOS, and Windows Python distributions).
- **No external Python libraries** are required.

### 2. Ollama & Local AI Models
Install and start [Ollama](https://ollama.com) locally (listening on `http://127.0.0.1:11434`), then pull the four required models:

```bash
ollama pull nomic-embed-text
ollama pull llama3.2:1b
ollama pull moondream
ollama pull qwen2.5:1.5b
```

| Model | Role in Suite | Footprint / Context | Provider |
|---|---|---|---|
| [`nomic-embed-text`](https://ollama.com/library/nomic-embed-text) | Semantic vector embeddings (`--embed`, `--semantic-search`, `--ask`) | 768-dim, 8192 tokens | [Nomic AI](https://www.nomic.ai) |
| [`llama3.2:1b`](https://ollama.com/library/llama3.2) | Literary Sommelier RAG (`--ask`) & Reader's Dossier (`--dossier`) | 1B params | [Meta AI](https://ai.meta.com/llama/) |
| [`moondream`](https://ollama.com/library/moondream) | Cover art visual inspection & OCR (`--cover`) | 1.8B vision-language | [Moondream](https://moondream.ai) |
| [`qwen2.5:1.5b`](https://ollama.com/library/qwen2.5) | Structured JSON genre/theme auto-tagging (`--autotag`) | 1.5B params | [Qwen / Alibaba Cloud](https://github.com/QwenLM/Qwen2.5) |

---

## Quick-Start Workflow

To index your EPUB collection and generate semantic embeddings in a single step:

```bash
# Place your .epub files in ./epub (or specify --dir /path/to/epubs)
python3 epub_indexer.py --update
```

Once complete, verify your library health:

```bash
python3 epub_indexer.py --stats
```

---

## User Guide & Command Reference

### 1. Scanning and Cataloguing (`--scan`)
Discover `.epub` archives, extract internal metadata across all CPU cores, and populate the SQLite catalog:

```bash
# Scan default directory (./epub) into default database (./epub_catalog.db)
python3 epub_indexer.py --scan

# Scan a custom directory and database path with 8 worker processes
python3 epub_indexer.py --scan --dir /path/to/epubs --db /path/to/catalog.db --workers 8
```

### 2. Generating Vector Embeddings (`--embed`)
Compute normalized vector embeddings for any catalogued books that do not yet have embeddings:

```bash
# Generate vector embeddings in batches of 50 (resumable at any time with Ctrl+C)
python3 epub_indexer.py --embed

# Customize batch size or cap the number of books embedded in one run
python3 epub_indexer.py --embed --batch-size 100 --limit 500
```

### 3. Incremental Maintenance (`--update`)
Run `--scan` (adding new EPUBs and pruning deleted ones) followed immediately by `--embed` for newly added volumes:

```bash
python3 epub_indexer.py --update
```

### 4. Keyword & Boolean Full-Text Search (`--search`)
Query the catalog using keywords, exact phrases, or [SQLite FTS5 boolean syntax](https://www.sqlite.org/fts5.html#full_text_query_syntax) (`AND`, `OR`, `NOT`, column filters), ordered by BM25 relevance:

```bash
# Boolean search with result limit
python3 epub_indexer.py --search "dystopia OR surveillance" --limit 20

# Phrase / author search
python3 epub_indexer.py --search "Arthur Conan Doyle"

# Export matching EPUB file paths to a text file (one path per line)
python3 epub_indexer.py --search "Arthur Conan Doyle" --output matched_books.txt
```

### 5. Semantic Vector Search (`--semantic-search`)
Find books by concept, plot vibe, or theme—even when your query shares no exact keywords with the book's title or blurb:

```bash
python3 epub_indexer.py --semantic-search "hard science fiction involving generational starships" --limit 10

# Save matching file paths for downstream scripting
python3 epub_indexer.py --semantic-search "cyberpunk artificial intelligence" -o results.txt
```

### 6. The Literary Sommelier (`--ask`)
Ask "Dr. Watson" for curated reading advice based on your library's holdings:

```bash
python3 epub_indexer.py --ask "I want an atmospheric Victorian gothic mystery with supernatural undertones"

# Force fresh generation (bypassing cache) and export the recommended EPUB paths
python3 epub_indexer.py --ask "philosophical cyberpunk stories" --refresh --output picks.txt
```

### 7. Reader's Dossier (`--dossier`)
Generate or display a structured reading brief (Premise & Hook, Tone & Atmosphere, and Recommended For) by Book ID, exact title, partial title, or filename:

```bash
python3 epub_indexer.py --dossier "Frankenstein"
python3 epub_indexer.py --dossier 42 --refresh
```

### 8. Visual Cover Art Analysis (`--cover`)
Extract the book's cover image from inside the EPUB archive and inspect its visual style, palette, and typography:

```bash
python3 epub_indexer.py --cover "Dune"
python3 epub_indexer.py --cover 105 --refresh
```

### 9. Automatic Genre & Thematic Tagging (`--autotag`)
Extract 3–6 standardized genre and thematic tags and permanently merge them into the book's catalog record and FTS5 index:

```bash
python3 epub_indexer.py --autotag "Neuromancer"
```

### 10. Library & Cache Statistics (`--stats`)
View total volume count, disk footprint, metadata completeness percentages, embedding coverage, cached AI artifacts, and the top 15 subject tags:

```bash
python3 epub_indexer.py --stats
```

---

## CLI Options Summary

| Argument | Description | Default |
|---|---|---|
| `--scan` | Scans EPUB files and indexes metadata into SQLite | `False` |
| `--embed` | Generates vector embeddings for unindexed books | `False` |
| `--update` | Executes incremental `--scan` and `--embed` pipeline | `False` |
| `--search <QUERY>` | Queries catalog using SQLite FTS5 | `None` |
| `--semantic-search <QUERY>` | Queries catalog via dense vector cosine similarity | `None` |
| `--ask <QUERY>` | Requests RAG recommendations from Dr. Watson | `None` |
| `--dossier <TARGET>` | Generates/displays Reader's Dossier (by ID, Title, or Filename) | `None` |
| `--cover <TARGET>` | Analyzes EPUB cover artwork via Moondream (by ID, Title, or Filename) | `None` |
| `--autotag <TARGET>` | Generates JSON tags via Qwen2.5 and updates database | `None` |
| `--stats` | Displays catalog statistics and cache health | `False` |
| `--refresh` | Forces regeneration of cached AI outputs (`--ask`, `--dossier`, `--cover`) | `False` |
| `--dir <PATH>` | Target directory containing EPUB archives | `./epub` |
| `--db <PATH>` | SQLite database file location | `./epub_catalog.db` |
| `--limit <INT>` | Maximum search results or processed records | `30` |
| `--output <PATH>`, `-o <PATH>` | Output file path to save matching EPUB file paths (aliases: `--output-file`, `--out`, `--export`) | `None` |
| `--batch-size <INT>` | Batch size for Ollama embedding generation | `50` |
| `--workers <INT>` | Worker process count for parallel metadata extraction | `os.cpu_count()` |

---
---

# Part 2: Technical Architecture & Developer Reference

This section documents the internal design, data structures, storage engine mechanics, mathematical formulations, and inference protocols implemented in [`epub_indexer.py`](epub_indexer.py).

## 1. System Architecture & Execution Pipeline

[`epub_indexer.py`](epub_indexer.py) is architected as a single-file, zero-dependency Python module relying strictly on standard library primitives (`sqlite3`, `zipfile`, `xml.etree.ElementTree`, `concurrent.futures`, `array`, `urllib.request`, `json`, `re`, `html`, `base64`, `math`).

```mermaid
flowchart TD
    subgraph Ingestion ["1. Ingestion & Indexing (--scan / --update)"]
        A["Filesystem Walk (os.walk)"] --> B["Diff Engine (Existing vs Disk Paths)"]
        B -->|Orphan Paths| C["Chunked Cascade Pruning (500 IDs/tx)"]
        B -->|New Paths| D["ProcessPoolExecutor (chunksize=50)"]
        D --> E["parse_single_epub() (ZipFile + ElementTree)"]
        E --> F["Batch SQLite Writer (500 rows/tx)"]
    end

    subgraph Storage ["2. SQLite WAL Storage Engine (epub_catalog.db)"]
        F --> G[("books (Primary Table)")]
        G -->|AFTER INSERT/UPDATE/DELETE Triggers| H[("books_fts (FTS5 External Content)")]
        I[("book_embeddings (Float32 BLOBs)")]
        J[("book_dossiers / book_covers / recommendation_cache")]
    end

    subgraph Inference ["3. Local Ollama Inference Layer (127.0.0.1:11434)"]
        K["/api/embed (nomic-embed-text)"]
        L["/api/generate (llama3.2:1b / moondream / qwen2.5:1.5b)"]
    end

    G -->|Unembedded Rows| K
    K -->|L2 Normalize + array('f').tobytes()| I
    H -->|MATCH + BM25 rank| M["Lexical Search (--search)"]
    I -->|In-Memory Dot Product Scan| N["Semantic Search (--semantic-search)"]
    N -->|Top-K Context| L
    L <--> J
```

---

## 2. EPUB OCF/OPF Parsing & Multiprocess Ingestion

### 2.1 Open Container Format (OCF) & OPF Resolution
Each `.epub` file is a ZIP archive conforming to the IDPF/W3C Open Container Format. [`parse_single_epub()`](epub_indexer.py#L76-L163) extracts metadata in-memory without extracting files to disk:

1. **Container Inspection**: Reads `META-INF/container.xml` from the `zipfile.ZipFile` stream and queries `.//n:rootfile` under namespace `urn:oasis:names:tc:opendocument:xmlns:container` (falling back to wildcard namespace `.//{*}rootfile`) to read the `full-path` attribute pointing to the Package Document (`.opf`).
2. **Fallback Discovery**: If `META-INF/container.xml` is missing or malformed, scans `ZipFile.namelist()` for the first entry ending in `.opf`.
3. **Dublin Core Metadata Extraction**: Parses the OPF XML tree, locates `.//pkg:metadata` (`http://www.idpf.org/2007/opf` or `.//{*}metadata`), and extracts Dublin Core (`http://purl.org/dc/elements/1.1/`) elements via a namespace-resilient helper `get_all_texts(tag_name)`:
   - **Single-valued fields**: `title` (defaults to filename stem if absent), `date` (`pubdate`).
   - **Multi-valued fields** (joined with `"; "`): `creator` (`author`), `publisher`, `language`, `identifier` (`identifiers`), `subject` (`subjects`).
   - **Sanitized Synopsis**: Concatenates all `<dc:description>` nodes and passes them through [`clean_text()`](epub_indexer.py#L53-L59), which strips embedded HTML/XML tags (`re.compile(r"<[^>]+>")`), decodes HTML entities (`html.unescape()`), and collapses runs of whitespace (`re.compile(r"\s+")`).

### 2.2 Differential Sync & Multiprocess Execution
[`scan_and_index()`](epub_indexer.py#L267-L366) avoids redundant I/O through set-based state reconciliation:

- **Orphan Pruning**: Compares `existing_map` (`SELECT path, id FROM books`) against `current_disk_paths`. Deleted paths are purged in chunks of **500 IDs per transaction** across `book_embeddings`, `book_dossiers`, `book_covers`, and `books` (which automatically triggers FTS5 deletion via `books_ad`).
- **CPU-Bound Parallelism**: Only newly discovered file paths (`to_process`) are dispatched to `concurrent.futures.ProcessPoolExecutor(max_workers=num_workers)` using `executor.map(parse_single_epub, to_process, chunksize=50)`. Setting `chunksize=50` amortizes IPC serialization overhead across worker processes.
- **Batched Write Commits**: The parent process consumes parsed dictionaries from the generator and executes `cur.executemany("INSERT OR REPLACE INTO books ...", batch)` every **500 records**, maintaining a single writer connection to prevent SQLite lock contention.

---

## 3. SQLite Engine Tuning, Relational Schema & FTS5 Internals

### 3.1 Connection PRAGMAs
[`init_db()`](epub_indexer.py#L165-L265) configures SQLite for high-throughput concurrent read/write workloads:

```sql
PRAGMA journal_mode = WAL;     -- Write-Ahead Logging: readers do not block writers
PRAGMA synchronous = NORMAL;   -- Fsyncs at critical WAL checkpoints rather than every commit
PRAGMA cache_size = -64000;    -- Allocates 64,000 KiB (~64 MiB) of in-memory page cache
```

### 3.2 Relational & Virtual Table Schema

```sql
-- Primary catalog table
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE,
    filename TEXT,
    filesize INTEGER,
    title TEXT,
    author TEXT,
    publisher TEXT,
    pubdate TEXT,
    language TEXT,
    identifiers TEXT,
    subjects TEXT,
    description TEXT
);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);

-- External-content FTS5 virtual table (avoids duplicating text storage)
CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
    title,
    author,
    subjects,
    description,
    content='books',
    content_rowid='id'
);
```

### 3.3 FTS5 Synchronization Triggers & BM25 Ranking
Because `books_fts` is configured with `content='books'` (an external content table), SQLite stores only the inverted index B-trees in `books_fts` and reads column values from `books` via `id = rowid`. Synchronization is enforced via three triggers:

- `books_ai` (`AFTER INSERT ON books`): Inserts `new.id, new.title, new.author, new.subjects, new.description` into `books_fts`.
- `books_ad` (`AFTER DELETE ON books`): Issues the special FTS5 `'delete'` command `INSERT INTO books_fts(books_fts, rowid, ...) VALUES('delete', old.id, ...)` to purge tokens from the inverted index.
- `books_au` (`AFTER UPDATE ON books`): Executes the `'delete'` command for `old.*` followed immediately by an `INSERT` of `new.*` (crucial when `--autotag` updates `books.subjects`).

During [`search_catalog()`](epub_indexer.py#L918-L965), queries execute `WHERE books_fts MATCH ? ORDER BY rank LIMIT ?`. In SQLite FTS5, ordering by the hidden `rank` column invokes the built-in **Okapi BM25** scoring function. If the user provides raw punctuation or unbalanced quotes that raise `sqlite3.OperationalError`, the search engine automatically wraps the query in double quotes (`f'"{query}"'`) and retries as a literal phrase match.

---

## 4. Dense Vector Representation & Cosine Similarity Engine

### 4.1 Asymmetric Task Prefixes (`nomic-embed-text`)
`nomic-embed-text` is trained with asymmetric task prefixes to distinguish documents from search queries in latent space:

- **Document Formatting** ([`format_doc_text()`](epub_indexer.py#L368-L376)):
  ```text
  search_document: Title: <title> | Author: <author> | Subjects: <subjects> | Synopsis: <description[:1000]>
  ```
  (Empty optional fields are omitted; synopses are truncated to 1,000 characters to preserve high signal-to-noise ratio and prevent token dilution.)
- **Query Formatting** ([`get_top_semantic_candidates()`](epub_indexer.py#L520-L545) & [`semantic_search()`](epub_indexer.py#L857-L916)):
  ```text
  search_query: <user_query>
  ```

### 4.2 L2 Normalization & Binary Float32 Serialization
When [`embed_catalog()`](epub_indexer.py#L428-L501) receives 768-dimensional float vectors from Ollama, each vector $\mathbf{v} \in \mathbb{R}^{768}$ is normalized to unit length ($\|\mathbf{\hat{v}}\|_2 = 1$) prior to storage via [`normalize_vector()`](epub_indexer.py#L378-L382):

$$\mathbf{\hat{v}} = \frac{\mathbf{v}}{\sqrt{\sum_{i=1}^{768} v_i^2}}$$

The normalized vector is serialized into a compact IEEE 754 single-precision (`float32`) binary buffer using Python's `array` module:

```python
blob = array.array("f", norm_emb).tobytes()  # 768 * 4 bytes = 3,072 bytes per book
```

Storing raw `float32` BLOBs instead of JSON text arrays reduces per-book vector storage by ~75% (3 KB vs ~12 KB) and eliminates JSON parsing overhead during full-table scans.

### 4.3 Exact Cosine Similarity via Unit Dot Product
Because both stored document vectors $\mathbf{\hat{d}}$ and query vectors $\mathbf{\hat{q}}$ are pre-normalized to unit length, their cosine similarity reduces mathematically to their inner (dot) product, avoiding two square-root norms per row during retrieval:

$$\cos(\theta) = \frac{\mathbf{q} \cdot \mathbf{d}}{\|\mathbf{q}\|_2 \|\mathbf{d}\|_2} = \mathbf{\hat{q}} \cdot \mathbf{\hat{d}} = \sum_{i=1}^{768} \hat{q}_i \hat{d}_i$$

During search, each 3,072-byte BLOB is unpacked directly into a C-backed `array.array("f")` buffer via `v.frombytes(blob)` and scored via `sum(x * y for x, y in zip(q_arr, v))`.

---

## 5. Local LLM/VLM Inference Contracts & RAG Pipeline

All inference calls communicate with the local Ollama server over standard HTTP (`urllib.request`) with automatic retry loops:

| Endpoint | Function | Timeout | Retry Policy |
|---|---|---|---|
| `POST http://127.0.0.1:11434/api/embed` | [`call_ollama_embed()`](epub_indexer.py#L384-L399) | `120s` | 3 attempts, linear backoff (`2 * (attempt + 1)` sec) |
| `POST http://127.0.0.1:11434/api/generate` | [`call_ollama_generate()`](epub_indexer.py#L401-L426) | `180s` | 2 attempts, fixed `2s` backoff, `"stream": False` |

### 5.1 RAG Recommender (`ask_sommelier`)
1. **Cache Lookup**: Normalizes the query (`query.strip().lower()`) and checks `recommendation_cache`.
2. **Vector Retrieval**: Calls [`get_top_semantic_candidates(conn, query, top_k=limit)`](epub_indexer.py#L520-L545) (capped at `min(args.limit, 6)` in `main()`, defaulting to 4 candidates).
3. **Context Assembly**: Formats each candidate with its rank, title, author, subject tags, and a 320-character synopsis snippet.
4. **Persona Generation**: Prompts `llama3.2:1b` as Dr. John H. Watson to evaluate the candidates, remark on each, and advise which volume to open first.
5. **Persistence**: Stores `(cache_key, recommendation, json.dumps(matched_ids), REASONING_MODEL)` in `recommendation_cache`.

### 5.2 Multimodal Cover Extraction & Vision Inspection (`book_cover_analysis`)
[`extract_cover_bytes()`](epub_indexer.py#L712-L726) locates cover art inside the EPUB ZIP archive without relying on inconsistent OPF `<meta name="cover">` tags:
1. Filters `ZipFile.namelist()` for image extensions (`.jpg`, `.jpeg`, `.png`, `.webp`).
2. Partition priority:
   - **Priority 1**: Entries containing `"cover"` (case-insensitive) in their internal path, sorted descending by uncompressed `file_size`.
   - **Priority 2**: All image entries in the archive, sorted descending by uncompressed `file_size` (selecting the highest-resolution asset).
3. Base64-encodes the raw image bytes and dispatches them in the `"images": [img_b64]` array to `moondream` via `/api/generate`.

### 5.3 Constrained JSON Auto-Tagging (`autotag_book`)
[`autotag_book()`](epub_indexer.py#L794-L855) invokes `qwen2.5:1.5b` with `format_json=True` (`"format": "json"` in the Ollama request payload), constraining token sampling to valid JSON matching `{"tags": ["Genre1", "Genre2", "Theme1"]}`.
- Extracted tags are merged with existing `; `-delimited `books.subjects` via a deduplicated set union (`existing_set.union(new_tags)`).
- Executing `UPDATE books SET subjects = ? WHERE id = ?` automatically fires the `books_au` trigger, re-indexing the volume in `books_fts` immediately.

---

## 6. Entity Resolution, Caching & Extension Guide

### 6.1 Multi-Tier Book Resolution (`resolve_book`)
Commands accepting a `<TARGET>` identifier (`--dossier`, `--cover`, `--autotag`) resolve the target against `books` in four deterministic stages via [`resolve_book()`](file:///media/mainmeister/120gbdata/epub_indexer.py#L503-L518):

1. **Primary Key ID**: If `target.isdigit()`, queries `WHERE id = ?`.
2. **Exact Title (Case-Insensitive)**: Queries `WHERE title = ? COLLATE NOCASE`.
3. **Substring Title Match**: Queries `WHERE title LIKE ? COLLATE NOCASE LIMIT 1` (`%target%`).
4. **Substring Filename Match**: Queries `WHERE filename LIKE ? COLLATE NOCASE LIMIT 1` (`%target%`).

### 6.2 Cache Invalidation Semantics
| Table | Primary Key | Invalidated By `--refresh`? | Invalidated On Orphan Prune? |
|---|---|---|---|
| `book_embeddings` | `book_id` | No (use SQL delete or re-embed) | Yes |
| `book_dossiers` | `book_id` | Yes (`INSERT OR REPLACE`) | Yes |
| `book_covers` | `book_id` | Yes (`INSERT OR REPLACE`) | Yes |
| `recommendation_cache` | `query` (lowercased) | Yes (`INSERT OR REPLACE`) | Retains text; resolves surviving `matched_book_ids` dynamically |

### 6.3 Extending the Suite
- **Swapping Local Models**: Modify the module constants [`EMBED_MODEL`](file:///media/mainmeister/120gbdata/epub_indexer.py#L39), [`REASONING_MODEL`](file:///media/mainmeister/120gbdata/epub_indexer.py#L40), [`VISION_MODEL`](file:///media/mainmeister/120gbdata/epub_indexer.py#L41), and [`TAGGER_MODEL`](file:///media/mainmeister/120gbdata/epub_indexer.py#L42) at the top of [`epub_indexer.py`](file:///media/mainmeister/120gbdata/epub_indexer.py#L39-L42). Note that if you change `EMBED_MODEL` to a model with a different dimensionality or without `search_document:` / `search_query:` prefixes, you should truncate `book_embeddings` and re-run `--embed`.
- **Adding Custom Metadata Fields**:
  1. Extract the desired Dublin Core or OPF tag inside [`parse_single_epub()`](file:///media/mainmeister/120gbdata/epub_indexer.py#L76-L163).
  2. Add the column to `books` (and optionally `books_fts` + its three triggers `books_ai`, `books_ad`, `books_au`) inside [`init_db()`](file:///media/mainmeister/120gbdata/epub_indexer.py#L165-L265).
  3. Include the field in [`format_doc_text()`](file:///media/mainmeister/120gbdata/epub_indexer.py#L368-L376) if it should influence dense semantic representations.
