#!/usr/bin/env python3
"""
epub_indexer.py - High-performance EPUB Cataloguer, Vector Search, and Literary Sleuth
Crafted for the library at /media/mainmeister/120gbdata/epub

Capabilities:
- Full-Text Search (SQLite FTS5)
- Semantic Vector Search (nomic-embed-text)
- The Literary Sommelier / RAG Recommender (llama3.2:1b)
- The Reader's Dossier (llama3.2:1b)
- On-Demand Visual Cover Art Analysis (moondream)
- Structured JSON Auto-Tagger (qwen2.5:1.5b)
- Persistent SQLite Result Caching
"""

import os
import sys
import re
import time
import math
import array
import sqlite3
import argparse
import html
import zipfile
import base64
import urllib.request
import json
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_EPUB_DIR = os.path.join(BASE_DIR, "epub")
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "epub_catalog.db")

OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embed"
OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"

EMBED_MODEL = "nomic-embed-text"
REASONING_MODEL = "llama3.2:1b"
VISION_MODEL = "moondream"
TAGGER_MODEL = "qwen2.5:1.5b"

NAMESPACES = {
    "n": "urn:oasis:names:tc:opendocument:xmlns:container",
    "pkg": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/"
}

TAG_CLEANER = re.compile(r"<[^>]+>")
WHITESPACE_CLEANER = re.compile(r"\s+")

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = TAG_CLEANER.sub(" ", text)
    text = html.unescape(text)
    text = WHITESPACE_CLEANER.sub(" ", text).strip()
    return text

def export_file_list(paths: list, output_file: str):
    """Writes a list of EPUB file paths to a specified output file, one per line."""
    if not output_file:
        return
    try:
        abs_output_path = os.path.abspath(output_file)
        os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
        with open(abs_output_path, "w", encoding="utf-8") as f:
            for p in paths:
                if p:
                    f.write(f"{p}\n")
        print(f"[+] Saved {len(paths)} matching EPUB path(s) to '{output_file}'.")
    except Exception as e:
        print(f"[!] Error writing output file '{output_file}': {e}")

def parse_single_epub(file_path: str):
    """Parses metadata from an individual EPUB archive."""
    try:
        stat = os.stat(file_path)
        filesize = stat.st_size
    except Exception:
        filesize = 0

    record = {
        "path": file_path,
        "filename": os.path.basename(file_path),
        "filesize": filesize,
        "title": os.path.splitext(os.path.basename(file_path))[0],
        "author": "",
        "publisher": "",
        "pubdate": "",
        "language": "",
        "identifiers": "",
        "subjects": "",
        "description": ""
    }

    try:
        with zipfile.ZipFile(file_path, "r") as z:
            try:
                container_data = z.read("META-INF/container.xml")
                c_root = ET.fromstring(container_data)
                rootfile = c_root.find(".//n:rootfile", NAMESPACES)
                if rootfile is None:
                    rootfile = c_root.find(".//{*}rootfile")
                if rootfile is None or "full-path" not in rootfile.attrib:
                    return record
                opf_path = rootfile.attrib["full-path"]
            except Exception:
                opf_candidates = [n for n in z.namelist() if n.lower().endswith(".opf")]
                if not opf_candidates:
                    return record
                opf_path = opf_candidates[0]

            opf_data = z.read(opf_path)
            opf_root = ET.fromstring(opf_data)

            metadata = opf_root.find(".//pkg:metadata", NAMESPACES)
            if metadata is None:
                metadata = opf_root.find(".//{*}metadata")
            if metadata is None:
                return record

            def get_all_texts(tag_name):
                els = metadata.findall(f"dc:{tag_name}", NAMESPACES)
                if not els:
                    els = [e for e in metadata if e.tag.endswith(tag_name)]
                results = []
                for e in els:
                    if e.text and e.text.strip():
                        results.append(e.text.strip())
                return results

            titles = get_all_texts("title")
            if titles:
                record["title"] = titles[0]

            authors = get_all_texts("creator")
            record["author"] = "; ".join(authors)

            publishers = get_all_texts("publisher")
            record["publisher"] = "; ".join(publishers)

            dates = get_all_texts("date")
            record["pubdate"] = dates[0] if dates else ""

            languages = get_all_texts("language")
            record["language"] = "; ".join(languages)

            identifiers = get_all_texts("identifier")
            record["identifiers"] = "; ".join(identifiers)

            subjects = get_all_texts("subject")
            record["subjects"] = "; ".join(subjects)

            descriptions = get_all_texts("description")
            if descriptions:
                record["description"] = clean_text(" ".join(descriptions))

    except Exception:
        pass

    return record

def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    cur.execute("PRAGMA cache_size = -64000;")

    cur.execute("""
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
    """)

    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);")

    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS books_fts USING fts5(
        title,
        author,
        subjects,
        description,
        content='books',
        content_rowid='id'
    );
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS books_ai AFTER INSERT ON books BEGIN
        INSERT INTO books_fts(rowid, title, author, subjects, description)
        VALUES (new.id, new.title, new.author, new.subjects, new.description);
    END;
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS books_ad AFTER DELETE ON books BEGIN
        INSERT INTO books_fts(books_fts, rowid, title, author, subjects, description)
        VALUES('delete', old.id, old.title, old.author, old.subjects, old.description);
    END;
    """)

    cur.execute("""
    CREATE TRIGGER IF NOT EXISTS books_au AFTER UPDATE ON books BEGIN
        INSERT INTO books_fts(books_fts, rowid, title, author, subjects, description)
        VALUES('delete', old.id, old.title, old.author, old.subjects, old.description);
        INSERT INTO books_fts(rowid, title, author, subjects, description)
        VALUES (new.id, new.title, new.author, new.subjects, new.description);
    END;
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS book_embeddings (
        book_id INTEGER PRIMARY KEY,
        embedding BLOB,
        FOREIGN KEY(book_id) REFERENCES books(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS book_dossiers (
        book_id INTEGER PRIMARY KEY,
        dossier TEXT,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(book_id) REFERENCES books(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS book_covers (
        book_id INTEGER PRIMARY KEY,
        cover_analysis TEXT,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(book_id) REFERENCES books(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_cache (
        query TEXT PRIMARY KEY,
        recommendation TEXT,
        matched_book_ids TEXT,
        model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

def scan_and_index(epub_dir: str, db_path: str, num_workers: int = None):
    print(f"[*] Discovering EPUB files in: {epub_dir}")
    t0 = time.time()
    epub_files = []
    for root, _, files in os.walk(epub_dir):
        for f in files:
            if f.lower().endswith(".epub"):
                epub_files.append(os.path.join(root, f))

    total_found = len(epub_files)
    print(f"[*] Found {total_found} EPUB files in {time.time() - t0:.2f}s.")
    if total_found == 0:
        print("[!] No files found. Exiting.")
        return

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    existing_map = dict(cur.execute("SELECT path, id FROM books").fetchall())

    current_disk_paths = set(epub_files)
    deleted_paths = [p for p in existing_map if p not in current_disk_paths]
    if deleted_paths:
        print(f"[*] Discovered {len(deleted_paths)} removed volumes. Pruning from catalogue...")
        deleted_ids = [existing_map[p] for p in deleted_paths]
        for i in range(0, len(deleted_ids), 500):
            chunk = deleted_ids[i:i + 500]
            cur.executemany("DELETE FROM book_embeddings WHERE book_id = ?;", [(cid,) for cid in chunk])
            cur.executemany("DELETE FROM book_dossiers WHERE book_id = ?;", [(cid,) for cid in chunk])
            cur.executemany("DELETE FROM book_covers WHERE book_id = ?;", [(cid,) for cid in chunk])
            cur.executemany("DELETE FROM books WHERE id = ?;", [(cid,) for cid in chunk])
            conn.commit()
        print(f"[+] Pruned {len(deleted_paths)} records from metadata, FTS, vectors, and cache tables.")

    to_process = [p for p in epub_files if p not in existing_map]
    print(f"[*] Retained catalogue: {len(existing_map) - len(deleted_paths)} | Pending extraction: {len(to_process)}")

    if not to_process:
        print("[+] All existing volumes are up to date.")
        conn.close()
        return

    conn.close()

    if num_workers is None:
        num_workers = max(1, os.cpu_count() or 4)

    print(f"[*] Launching {num_workers} parallel workers for metadata extraction...")
    t_start = time.time()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")

    batch = []
    count = 0
    batch_size = 500

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        for record in executor.map(parse_single_epub, to_process, chunksize=50):
            batch.append((
                record["path"], record["filename"], record["filesize"],
                record["title"], record["author"], record["publisher"],
                record["pubdate"], record["language"], record["identifiers"],
                record["subjects"], record["description"]
            ))
            count += 1

            if len(batch) >= batch_size:
                cur.executemany("""
                INSERT OR REPLACE INTO books (
                    path, filename, filesize, title, author, publisher,
                    pubdate, language, identifiers, subjects, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, batch)
                conn.commit()
                batch.clear()

                elapsed = time.time() - t_start
                rate = count / elapsed if elapsed > 0 else 0
                eta = (len(to_process) - count) / rate if rate > 0 else 0
                print(f"    Progress: {count}/{len(to_process)} ({count/len(to_process)*100:.1f}%) "
                      f"at {rate:.1f} files/sec | ETA: {eta:.0f}s", end="\r", flush=True)

    if batch:
        cur.executemany("""
        INSERT OR REPLACE INTO books (
            path, filename, filesize, title, author, publisher,
            pubdate, language, identifiers, subjects, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, batch)
        conn.commit()

    conn.close()
    t_end = time.time()
    print(f"\n[+] Indexing complete: {count} books processed in {t_end - t_start:.2f} seconds.")

def format_doc_text(title: str, author: str, subjects: str, desc: str) -> str:
    parts = [f"Title: {title}"]
    if author:
        parts.append(f"Author: {author}")
    if subjects:
        parts.append(f"Subjects: {subjects}")
    if desc:
        parts.append(f"Synopsis: {desc[:1000]}")
    return "search_document: " + " | ".join(parts)

def normalize_vector(vec):
    mag = math.sqrt(sum(x * x for x in vec))
    if mag == 0:
        return vec
    return [x / mag for x in vec]

def call_ollama_embed(texts, retries=3):
    payload = json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA_EMBED_URL,
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                return data["embeddings"]
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(2 * (attempt + 1))

def call_ollama_generate(model: str, prompt: str, images=None, format_json=False, retries=2):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    if images:
        payload["images"] = images
    if format_json:
        payload["format"] = "json"

    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OLLAMA_GENERATE_URL,
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=180) as resp:
                res = json.loads(resp.read().decode())
                return res.get("response", "").strip()
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(2)

def embed_catalog(db_path: str, batch_size: int = 50, limit: int = None):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")

    embedded_count = cur.execute("SELECT count(*) FROM book_embeddings").fetchone()[0]
    total_books = cur.execute("SELECT count(*) FROM books").fetchone()[0]
    print(f"[*] Total Books in Library: {total_books:,}")
    print(f"[*] Already Embedded:       {embedded_count:,}")

    query = """
    SELECT id, title, author, subjects, description
    FROM books
    WHERE id NOT IN (SELECT book_id FROM book_embeddings)
    ORDER BY id
    """
    if limit:
        query += f" LIMIT {limit}"

    rows = cur.execute(query).fetchall()
    pending = len(rows)

    if pending == 0:
        print("[+] All books have already been embedded!")
        conn.close()
        return

    print(f"[*] Commencing embedding generation for {pending:,} volumes using {EMBED_MODEL}...")
    print(f"[*] Batch size: {batch_size} | SQLite WAL enabled\n")

    t_start = time.time()
    processed = 0

    try:
        for i in range(0, pending, batch_size):
            chunk = rows[i:i + batch_size]
            texts = [format_doc_text(r[1], r[2], r[3], r[4]) for r in chunk]

            embeddings = call_ollama_embed(texts)

            insert_batch = []
            for r, emb in zip(chunk, embeddings):
                book_id = r[0]
                norm_emb = normalize_vector(emb)
                blob = array.array("f", norm_emb).tobytes()
                insert_batch.append((book_id, blob))

            cur.executemany("INSERT OR REPLACE INTO book_embeddings (book_id, embedding) VALUES (?, ?);", insert_batch)
            conn.commit()

            processed += len(chunk)
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            eta_sec = (pending - processed) / rate if rate > 0 else 0
            eta_min = eta_sec / 60

            print(f"    Progress: {processed}/{pending} ({processed/pending*100:.1f}%) "
                  f"| {rate:.1f} books/sec | ETA: {eta_min:.1f} min", end="\r", flush=True)

    except KeyboardInterrupt:
        print(f"\n[!] Paused by user. Successfully saved {processed} embeddings so far. Resume anytime with --embed.")
        conn.close()
        return
    except Exception as e:
        print(f"\n[!] Encountered error: {e}. Successfully saved {processed} embeddings before interruption.")
        conn.close()
        raise e

    conn.close()
    t_end = time.time()
    total_elapsed = t_end - t_start
    print(f"\n\n[+] Successfully embedded {processed:,} volumes in {total_elapsed/60:.2f} minutes ({processed/total_elapsed:.1f} books/sec).")

def resolve_book(conn, target: str):
    """Finds a book by ID, exact title, partial title, or filename."""
    cur = conn.cursor()
    target = target.strip()
    if target.isdigit():
        row = cur.execute("SELECT id, title, author, subjects, description, path FROM books WHERE id = ?", (int(target),)).fetchone()
        if row:
            return row
    row = cur.execute("SELECT id, title, author, subjects, description, path FROM books WHERE title = ? COLLATE NOCASE", (target,)).fetchone()
    if row:
        return row
    row = cur.execute("SELECT id, title, author, subjects, description, path FROM books WHERE title LIKE ? COLLATE NOCASE LIMIT 1", (f"%{target}%",)).fetchone()
    if row:
        return row
    row = cur.execute("SELECT id, title, author, subjects, description, path FROM books WHERE filename LIKE ? COLLATE NOCASE LIMIT 1", (f"%{target}%",)).fetchone()
    return row

def get_top_semantic_candidates(conn, query: str, top_k: int = 4):
    """Returns top_k book records matching query semantically."""
    query_text = f"search_query: {query}"
    raw_query_emb = call_ollama_embed([query_text])[0]
    norm_query_emb = normalize_vector(raw_query_emb)
    q_arr = array.array("f", norm_query_emb)

    cur = conn.cursor()
    cur.execute("SELECT book_id, embedding FROM book_embeddings;")

    scores = []
    for bid, blob in cur.fetchall():
        v = array.array("f")
        v.frombytes(blob)
        dot = sum(x * y for x, y in zip(q_arr, v))
        scores.append((dot, bid))

    scores.sort(reverse=True, key=lambda x: x[0])
    top_matches = scores[:top_k]

    results = []
    for sim, bid in top_matches:
        book = cur.execute("SELECT id, title, author, subjects, description, path FROM books WHERE id = ?", (bid,)).fetchone()
        if book:
            results.append((sim, book))
    return results

def ask_sommelier(db_path: str, query: str, refresh: bool = False, limit: int = 4, output_file: str = None):
    """The Literary Sommelier: Conversational book recommendations using RAG with caching."""
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cache_key = query.strip().lower()

    if not refresh:
        cached = cur.execute("SELECT recommendation, matched_book_ids, created_at FROM recommendation_cache WHERE query = ?", (cache_key,)).fetchone()
        if cached:
            rec, book_ids_json, created_at = cached
            print("=" * 80)
            print(f"      DR. WATSON'S LITERARY RECOMMENDATION  [Cached: {created_at}]")
            print("=" * 80)
            print(f"\n{rec}\n")
            print("=" * 80)
            cached_paths = []
            try:
                book_ids = json.loads(book_ids_json)
                print("Referenced Volumes in Catalogue:")
                for idx, bid in enumerate(book_ids, 1):
                    b = cur.execute("SELECT title, author, path FROM books WHERE id = ?", (bid,)).fetchone()
                    if b:
                        cached_paths.append(b[2])
                        print(f"  {idx}. {b[0]} — {b[1] or 'Unknown'}")
                        print(f"     Path: {b[2]}")
            except Exception:
                pass
            print("=" * 80)
            conn.close()
            if output_file:
                export_file_list(cached_paths, output_file)
            return

    print(f"[*] Consulting catalogue for: '{query}'...")
    candidates = get_top_semantic_candidates(conn, query, top_k=limit)
    if not candidates:
        print("[!] No candidate books found. Ensure embeddings exist.")
        conn.close()
        if output_file:
            export_file_list([], output_file)
        return

    candidate_text_blocks = []
    matched_ids = []
    matched_paths = []
    for rank, (sim, b) in enumerate(candidates, 1):
        bid, title, author, subjects, desc, path = b
        matched_ids.append(bid)
        matched_paths.append(path)
        desc_snippet = (desc[:320] + "...") if len(desc) > 320 else desc
        block = f"Book {rank}: \"{title}\" by {author or 'Unknown'}\nTags: {subjects or 'None'}\nSynopsis: {desc_snippet or 'None'}"
        candidate_text_blocks.append(block)

    joined_candidates = "\n\n".join(candidate_text_blocks)

    prompt = f"""You are Doctor John H. Watson, late of the Army Medical Department, devoted friend and literary companion.
A fellow reader and esteemed companion has approached you with this inquiry:
"{query}"

Our library catalogue has retrieved the following candidate volumes from the collection:
{joined_candidates}

In your characteristic gentlemanly, warm, observant, and articulate Victorian voice:
1. Recommend which of these works best satisfies their request and why.
2. Offer a brief, discerning remark on each candidate volume.
3. Conclude with encouraging, practical advice on which volume to open first.
Keep your response engaging, concise, and courteous."""

    print(f"[*] Engaging Dr. Watson ({REASONING_MODEL}) to review candidate volumes...")
    t0 = time.time()
    recommendation = call_ollama_generate(REASONING_MODEL, prompt)
    t1 = time.time()

    # Cache recommendation
    cur.execute("""
    INSERT OR REPLACE INTO recommendation_cache (query, recommendation, matched_book_ids, model)
    VALUES (?, ?, ?, ?);
    """, (cache_key, recommendation, json.dumps(matched_ids), REASONING_MODEL))
    conn.commit()

    print("=" * 80)
    print(f"      DR. WATSON'S LITERARY RECOMMENDATION  (Generated in {t1 - t0:.1f}s)")
    print("=" * 80)
    print(f"\n{recommendation}\n")
    print("=" * 80)
    print("Referenced Volumes:")
    for idx, (sim, b) in enumerate(candidates, 1):
        pct = sim * 100
        print(f"  {idx}. [{pct:.1f}% Match] {b[1]} — {b[2] or 'Unknown'}")
        print(f"     Path: {b[5]}")
    print("=" * 80)
    conn.close()
    if output_file:
        export_file_list(matched_paths, output_file)

def book_dossier(db_path: str, target: str, refresh: bool = False):
    """Generates and caches an instant Reader's Dossier for a book."""
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    book = resolve_book(conn, target)
    if not book:
        print(f"[!] Could not locate book matching: '{target}'")
        conn.close()
        return

    bid, title, author, subjects, desc, path = book

    if not refresh:
        cached = cur.execute("SELECT dossier, created_at FROM book_dossiers WHERE book_id = ?", (bid,)).fetchone()
        if cached:
            dossier_text, created_at = cached
            print("=" * 80)
            print(f"      READER'S DOSSIER: {title.upper()}  [Cached: {created_at}]")
            print("=" * 80)
            print(f"Author:   {author or 'Unknown'}")
            if subjects:
                print(f"Subjects: {subjects}")
            print(f"Path:     {path}\n" + "-" * 80)
            print(dossier_text)
            print("=" * 80)
            conn.close()
            return

    print(f"[*] Compiling Reader's Dossier for \"{title}\" via {REASONING_MODEL}...")
    prompt = f"""You are an expert literary curator and reviewer. Analyze this book and prepare a concise, high-impact Reader's Dossier:
Title: {title}
Author: {author or 'Unknown'}
Subjects: {subjects or 'None specified'}
Synopsis: {desc or 'No publisher synopsis available.'}

Format your response strictly under these three headings:
• PREMISE & HOOK: (2-3 sentences explaining the central mystery, plot, or scientific problem)
• TONE & ATMOSPHERE: (Key descriptors: pacing, mood, literary/scientific style)
• RECOMMENDED FOR: (Who will enjoy this, and 2-3 comparable authors or landmark books)"""

    t0 = time.time()
    dossier_text = call_ollama_generate(REASONING_MODEL, prompt)
    t1 = time.time()

    cur.execute("INSERT OR REPLACE INTO book_dossiers (book_id, dossier, model) VALUES (?, ?, ?);", (bid, dossier_text, REASONING_MODEL))
    conn.commit()

    print("=" * 80)
    print(f"      READER'S DOSSIER: {title.upper()}  (Generated in {t1 - t0:.1f}s)")
    print("=" * 80)
    print(f"Author:   {author or 'Unknown'}")
    if subjects:
        print(f"Subjects: {subjects}")
    print(f"Path:     {path}\n" + "-" * 80)
    print(dossier_text)
    print("=" * 80)
    conn.close()

def extract_cover_bytes(epub_path: str):
    """Extracts the cover image bytes from an EPUB archive."""
    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            names = [n for n in z.namelist() if n.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            if not names:
                return None, ""
            covers = [n for n in names if "cover" in n.lower()]
            if covers:
                chosen = sorted(covers, key=lambda n: z.getinfo(n).file_size, reverse=True)[0]
                return z.read(chosen), chosen
            chosen = sorted(names, key=lambda n: z.getinfo(n).file_size, reverse=True)[0]
            return z.read(chosen), chosen
    except Exception:
        return None, ""

def book_cover_analysis(db_path: str, target: str, refresh: bool = False):
    """Uses Moondream to visually inspect, describe, and transcribe book cover art with caching."""
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    book = resolve_book(conn, target)
    if not book:
        print(f"[!] Could not locate book matching: '{target}'")
        conn.close()
        return

    bid, title, author, subjects, desc, path = book

    if not refresh:
        cached = cur.execute("SELECT cover_analysis, created_at FROM book_covers WHERE book_id = ?", (bid,)).fetchone()
        if cached:
            analysis, created_at = cached
            print("=" * 80)
            print(f"      COVER ART ANALYSIS: {title.upper()}  [Cached: {created_at}]")
            print("=" * 80)
            print(f"Author:   {author or 'Unknown'}")
            print(f"Path:     {path}\n" + "-" * 80)
            print(analysis)
            print("=" * 80)
            conn.close()
            return

    print(f"[*] Extracting cover image from archive for \"{title}\"...")
    img_bytes, img_name = extract_cover_bytes(path)
    if not img_bytes:
        print(f"[!] No cover or jacket images could be located inside: {path}")
        conn.close()
        return

    print(f"[*] Image found: '{img_name}' ({len(img_bytes)/1024:.1f} KB).")
    print(f"[*] Inspecting cover art with {VISION_MODEL}...")

    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    prompt = (
        "Analyze this book cover. "
        "1. Describe the artwork, visual style, palette, and atmosphere. "
        "2. Transcribe any titles, subtitles, author names, quotes, or award text visible on the cover."
    )

    t0 = time.time()
    analysis = call_ollama_generate(VISION_MODEL, prompt, images=[img_b64])
    t1 = time.time()

    cur.execute("INSERT OR REPLACE INTO book_covers (book_id, cover_analysis, model) VALUES (?, ?, ?);", (bid, analysis, VISION_MODEL))
    conn.commit()

    print("=" * 80)
    print(f"      COVER ART ANALYSIS: {title.upper()}  (Generated in {t1 - t0:.1f}s)")
    print("=" * 80)
    print(f"Author:   {author or 'Unknown'}")
    print(f"Image:    {img_name}")
    print(f"Path:     {path}\n" + "-" * 80)
    print(analysis)
    print("=" * 80)
    conn.close()

def autotag_book(db_path: str, target: str):
    """Uses Qwen2.5 to extract structured genre and thematic tags and stores them in SQLite."""
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    book = resolve_book(conn, target)
    if not book:
        print(f"[!] Could not locate book matching: '{target}'")
        conn.close()
        return

    bid, title, author, existing_subjects, desc, path = book

    print(f"[*] Auto-tagging \"{title}\" using {TAGGER_MODEL}...")
    prompt = f"""You are a master book cataloguer. Extract 3 to 6 concise, standard genre and thematic tags for this volume:
Title: {title}
Author: {author or 'Unknown'}
Existing Tags: {existing_subjects or 'None'}
Synopsis: {desc or 'No synopsis available.'}

Respond strictly with a JSON object in this format:
{{"tags": ["Genre1", "Genre2", "Theme1"]}}"""

    t0 = time.time()
    raw_json = call_ollama_generate(TAGGER_MODEL, prompt, format_json=True)
    t1 = time.time()

    try:
        parsed = json.loads(raw_json)
        new_tags = parsed.get("tags", [])
    except Exception as e:
        print(f"[!] JSON parsing error: {e}. Raw response: {raw_json}")
        conn.close()
        return

    if not new_tags:
        print("[!] No tags could be extracted.")
        conn.close()
        return

    existing_set = set(s.strip() for s in existing_subjects.split(";") if s.strip())
    combined_tags = list(existing_set.union(new_tags))
    combined_str = "; ".join(combined_tags)

    cur.execute("UPDATE books SET subjects = ? WHERE id = ?", (combined_str, bid))
    conn.commit()

    print("=" * 80)
    print(f"      AUTO-TAGGING COMPLETE: {title.upper()}  ({t1 - t0:.1f}s)")
    print("=" * 80)
    print(f"Author:            {author or 'Unknown'}")
    print(f"Previous Subjects: {existing_subjects or '(None)'}")
    print(f"New Tags Added:    {', '.join(new_tags)}")
    print(f"Updated Catalogue: {combined_str}")
    print("=" * 80)
    print("[+] SQLite catalogue and Full-Text Search index (FTS5) updated permanently.")
    conn.close()

def semantic_search(db_path: str, query: str, limit: int = 30, output_file: str = None):
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    count = cur.execute("SELECT count(*) FROM book_embeddings").fetchone()[0]
    if count == 0:
        print("[!] No embeddings found. Please run --embed first.")
        conn.close()
        if output_file:
            export_file_list([], output_file)
        return

    print(f"[*] Embedding query: '{query}'...")
    query_text = f"search_query: {query}"
    raw_query_emb = call_ollama_embed([query_text])[0]
    norm_query_emb = normalize_vector(raw_query_emb)
    q_arr = array.array("f", norm_query_emb)

    print(f"[*] Scanning {count:,} vector embeddings...")
    t0 = time.time()
    cur.execute("SELECT book_id, embedding FROM book_embeddings;")

    scores = []
    for bid, blob in cur.fetchall():
        v = array.array("f")
        v.frombytes(blob)
        dot = sum(x * y for x, y in zip(q_arr, v))
        scores.append((dot, bid))

    scores.sort(reverse=True, key=lambda x: x[0])
    top_matches = scores[:limit]
    t1 = time.time()

    print(f"[+] Scanned in {t1 - t0:.3f}s. Top {len(top_matches)} results for: '{query}'\n" + "=" * 80)

    matching_paths = []
    for rank, (sim, bid) in enumerate(top_matches, 1):
        book = cur.execute("SELECT title, author, subjects, description, path FROM books WHERE id = ?", (bid,)).fetchone()
        if not book:
            continue
        title, author, subjects, desc, path = book
        matching_paths.append(path)
        pct = sim * 100
        print(f"{rank}. [{pct:.1f}% Match] {title}")
        print(f"    Author:   {author or 'Unknown'}")
        if subjects:
            print(f"    Subjects: {subjects}")
        if desc:
            short_desc = (desc[:180] + "...") if len(desc) > 180 else desc
            print(f"    Synopsis: {short_desc}")
        print(f"    Path:     {path}")
        print("-" * 80)

    conn.close()
    if output_file:
        export_file_list(matching_paths, output_file)

def search_catalog(db_path: str, query: str, limit: int = 50, output_file: str = None):
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}. Please run --scan first.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    sql = """
    SELECT b.id, b.title, b.author, b.subjects, b.description, b.path
    FROM books_fts f
    JOIN books b ON b.id = f.rowid
    WHERE books_fts MATCH ?
    ORDER BY rank
    LIMIT ?;
    """

    try:
        rows = cur.execute(sql, (query, limit)).fetchall()
    except sqlite3.OperationalError:
        safe_query = f'"{query}"'
        try:
            rows = cur.execute(sql, (safe_query, limit)).fetchall()
        except Exception as e2:
            print(f"[!] Search query error: {e2}")
            conn.close()
            if output_file:
                export_file_list([], output_file)
            return

    conn.close()

    matching_paths = []
    print(f"\n[+] Found {len(rows)} results for query: '{query}' (limit {limit})\n" + "="*80)
    for idx, (book_id, title, author, subjects, desc, path) in enumerate(rows, 1):
        matching_paths.append(path)
        print(f"{idx}. {title}")
        print(f"   Author:   {author or 'Unknown'}")
        if subjects:
            print(f"   Subjects: {subjects}")
        if desc:
            short_desc = (desc[:160] + "...") if len(desc) > 160 else desc
            print(f"   Summary:  {short_desc}")
        print(f"   Path:     {path}")
        print("-" * 80)

    if output_file:
        export_file_list(matching_paths, output_file)

def show_stats(db_path: str):
    if not os.path.exists(db_path):
        print(f"[!] Database not found at {db_path}.")
        return

    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    total_books = cur.execute("SELECT count(*) FROM books").fetchone()[0]
    with_authors = cur.execute("SELECT count(*) FROM books WHERE author != ''").fetchone()[0]
    with_subjects = cur.execute("SELECT count(*) FROM books WHERE subjects != ''").fetchone()[0]
    with_desc = cur.execute("SELECT count(*) FROM books WHERE description != ''").fetchone()[0]
    total_size_mb = cur.execute("SELECT sum(filesize) / (1024*1024) FROM books").fetchone()[0] or 0

    try:
        embedded_count = cur.execute("SELECT count(*) FROM book_embeddings").fetchone()[0]
    except Exception:
        embedded_count = 0

    try:
        dossier_count = cur.execute("SELECT count(*) FROM book_dossiers").fetchone()[0]
    except Exception:
        dossier_count = 0

    try:
        cover_count = cur.execute("SELECT count(*) FROM book_covers").fetchone()[0]
    except Exception:
        cover_count = 0

    try:
        rec_count = cur.execute("SELECT count(*) FROM recommendation_cache").fetchone()[0]
    except Exception:
        rec_count = 0

    print("=" * 60)
    print("           EPUB LIBRARY CATALOGUE STATISTICS")
    print("=" * 60)
    print(f"Total Volumes:           {total_books:,}")
    print(f"Total Disk Size:         {total_size_mb:,} MB (~{total_size_mb/1024:.1f} GB)")
    print(f"Volumes with Author:     {with_authors:,} ({with_authors/max(1, total_books)*100:.1f}%)")
    print(f"Volumes with Subjects:   {with_subjects:,} ({with_subjects/max(1, total_books)*100:.1f}%)")
    print(f"Volumes with Blurb/Desc: {with_desc:,} ({with_desc/max(1, total_books)*100:.1f}%)")
    print(f"Vector Embeddings Ready: {embedded_count:,} ({embedded_count/max(1, total_books)*100:.1f}%)")
    print("-" * 60)
    print("           AI INTELLIGENCE & CACHE STATUS")
    print("-" * 60)
    print(f"Cached Reader Dossiers:  {dossier_count:,}")
    print(f"Cached Cover Analyses:   {cover_count:,}")
    print(f"Cached Recommendations:  {rec_count:,}")
    print("=" * 60)

    cur.execute("SELECT subjects FROM books WHERE subjects != '' LIMIT 5000;")
    subject_counts = {}
    for (sub_str,) in cur.fetchall():
        for s in sub_str.split(";"):
            s_clean = s.strip()
            if s_clean and len(s_clean) > 2:
                subject_counts[s_clean] = subject_counts.get(s_clean, 0) + 1

    top_subjects = sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    if top_subjects:
        print("\nTop Embedded Subject Tags:")
        for tag, cnt in top_subjects:
            print(f" - {tag}: {cnt} volumes")
    print("=" * 60)
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="EPUB Cataloguer, Vector Search, and Literary Sleuth")
    parser.add_argument("--scan", action="store_true", help="Scan and catalogue EPUBs into SQLite")
    parser.add_argument("--embed", action="store_true", help="Generate vector embeddings via Ollama nomic-embed-text")
    parser.add_argument("--semantic-search", type=str, help="Semantic vector search using natural language")
    parser.add_argument("--dir", default=DEFAULT_EPUB_DIR, help="Directory containing EPUB files")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database")
    parser.add_argument("--search", type=str, help="Search query (FTS5 syntax or keyword)")
    parser.add_argument("--limit", type=int, default=30, help="Max results for search")
    parser.add_argument("--output", "-o", "--output-file", "--out", "--export", type=str, default=None, dest="output", help="Write matching EPUB file paths to the specified file")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size for embedding")
    parser.add_argument("--update", action="store_true", help="Incrementally scan new EPUBs and generate embeddings in one step")
    parser.add_argument("--stats", action="store_true", help="Display catalog and cache statistics")
    parser.add_argument("--workers", type=int, default=None, help="Number of worker processes")

    # New AI and Caching capabilities
    parser.add_argument("--ask", type=str, help="The Literary Sommelier: Ask Dr. Watson for reading recommendations (RAG)")
    parser.add_argument("--dossier", type=str, help="Generate/view Reader's Dossier for a book (by Title or ID)")
    parser.add_argument("--cover", type=str, help="Visually inspect and analyze cover artwork via Moondream (by Title or ID)")
    parser.add_argument("--autotag", type=str, help="Extract structured tags via Qwen2.5 and save to database (by Title or ID)")
    parser.add_argument("--refresh", action="store_true", help="Force refresh of cached AI outputs")

    args = parser.parse_args()

    if args.ask:
        ask_sommelier(args.db, args.ask, args.refresh, limit=min(args.limit, 6), output_file=args.output)
    elif args.dossier:
        book_dossier(args.db, args.dossier, args.refresh)
    elif args.cover:
        book_cover_analysis(args.db, args.cover, args.refresh)
    elif args.autotag:
        autotag_book(args.db, args.autotag)
    elif args.update:
        print("[*] Running incremental update...")
        scan_and_index(args.dir, args.db, args.workers)
        embed_catalog(args.db, args.batch_size)
    elif args.scan:
        scan_and_index(args.dir, args.db, args.workers)
    elif args.embed:
        embed_catalog(args.db, args.batch_size, args.limit if args.limit != 30 else None)
    elif args.semantic_search:
        semantic_search(args.db, args.semantic_search, args.limit, output_file=args.output)
    elif args.search:
        search_catalog(args.db, args.search, args.limit, output_file=args.output)
    elif args.stats:
        show_stats(args.db)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
