import os
import sqlite3
import difflib
import re
from typing import List, Dict, Any
from pathlib import Path

# File extensions that should appear first in search results
PRIORITY_EXTENSIONS = {"pdf", "doc", "docx", "txt", "rtf", "jpg", "jpeg", "png", "gif", "svg", "bmp", "mp4", "mkv", "avi", "mov", "webm"}

# When frozen by PyInstaller, __file__ points to a temp folder wiped on every launch.
# Use %APPDATA% for persistent storage — same path as indexer.py uses.
def _get_data_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    data_dir = os.path.join(appdata, "FileIntelligence")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

SQLITE_PATH = os.path.join(_get_data_dir(), "metadata.db")

def search_files(query: str, top_k: int = 30) -> List[Dict[str, Any]]:
    """
    Highly optimized fuzzy and multi-term file search:
    1. Splits query into terms and searches for files containing ALL terms in the filename (high precision).
    2. Fallback to files matching ANY term in the filename.
    3. Fallback to files matching prefix of the query (handles typos towards the end of the word).
    4. Fallback to FTS index for content search.
    5. Scores and ranks candidates using Exact Match, Starts-with, Substring, and Fuzzy Similarity Ratio.
    """
    if not query or not query.strip():
        return []

    STOP_WORDS = {"find", "search", "show", "me", "the", "a", "an", "in", "inside", "under", "folder", "directory", "file", "named", "called", "with", "where"}

    query_clean = query.strip().lower()
    raw_terms = [t for t in query_clean.split() if t]
    query_terms = [t for t in raw_terms if t not in STOP_WORDS]
    if not query_terms:
        query_terms = raw_terms
    if not query_terms:
        return []

    con = sqlite3.connect(SQLITE_PATH)
    con.row_factory = sqlite3.Row
    
    results = []
    seen_paths = set()
    candidates = []

    try:
        # Pass 1: Try to find file paths matching ALL terms (Precise path search)
        like_clauses = " AND ".join(["filepath LIKE ?" for _ in query_terms])
        params = [f"%{t}%" for t in query_terms]
        
        sql_all = f"""
            SELECT id, filepath, filename, snippet
            FROM indexed_files 
            WHERE {like_clauses}
            LIMIT 500
        """
        rows = con.execute(sql_all, params).fetchall()
        for r in rows:
            if r["filepath"] not in seen_paths:
                candidates.append((r, "all_terms"))
                seen_paths.add(r["filepath"])

        # Pass 2: If we don't have enough candidates, find file paths matching ANY of the terms
        if len(candidates) < 150:
            or_clauses = " OR ".join(["filepath LIKE ?" for _ in query_terms])
            sql_any = f"""
                SELECT id, filepath, filename, snippet
                FROM indexed_files 
                WHERE {or_clauses}
                LIMIT 500
            """
            rows = con.execute(sql_any, params).fetchall()
            for r in rows:
                if r["filepath"] not in seen_paths:
                    candidates.append((r, "any_terms"))
                    seen_paths.add(r["filepath"])

        # Pass 3: If still low on candidates, fetch files containing the first 3 chars of the query
        # (Catches typos near the end of the word like 'resme' -> 'resume')
        if len(candidates) < 100 and len(query_clean) >= 3:
            prefix_3 = query_clean[:3]
            sql_prefix = """
                SELECT id, filepath, filename, snippet
                FROM indexed_files 
                WHERE filename LIKE ?
                LIMIT 300
            """
            rows = con.execute(sql_prefix, (f"%{prefix_3}%",)).fetchall()
            for r in rows:
                if r["filepath"] not in seen_paths:
                    candidates.append((r, "typo_prefix"))
                    seen_paths.add(r["filepath"])

        # Pass 4: Content/Snippet FTS search (always run to include keyword matches in file contents)
        fts_query = " OR ".join([f"{t}*" for t in query_terms])
        sql_fts = """
            SELECT f.id, f.filepath, f.filename, f.snippet
            FROM indexed_files f
            JOIN file_search_index idx ON f.id = idx.rowid
            WHERE file_search_index MATCH ?
            LIMIT 300
        """
        rows = con.execute(sql_fts, (fts_query,)).fetchall()
        for r in rows:
            if r["filepath"] not in seen_paths:
                candidates.append((r, "content"))
                seen_paths.add(r["filepath"])

        # Score and rank candidates in Python
        scored_candidates = []
        for r, match_type in candidates:
            filename = r["filename"]
            filename_lower = filename.lower()
            
            # Base score from matching category
            if match_type == "all_terms":
                base_score = 1.0
            elif match_type == "any_terms":
                base_score = 0.5
            elif match_type == "typo_prefix":
                base_score = 0.3
            else:
                base_score = 0.1

            # Exact name match (ignoring extension)
            name_no_ext = os.path.splitext(filename_lower)[0]
            
            if name_no_ext == query_clean:
                relevance = 3.0
            elif filename_lower == query_clean:
                relevance = 2.8
            elif filename_lower.startswith(query_clean):
                relevance = 2.5
            elif query_clean in filename_lower:
                relevance = 2.0
            else:
                relevance = base_score
                
            # Exact word match boost – split filename into words (alphanumeric) and reward whole-word matches
            # Normalize filename: replace non-alphanumeric characters with spaces
            cleaned_name = re.sub(r"[^a-z0-9]+", " ", filename_lower)
            name_words = set([w for w in cleaned_name.split() if w])
            word_match_count = sum(1 for t in query_terms if t in name_words)
            if word_match_count:
                # Add up to 1.0 boost scaled by proportion of query terms that match whole words
                relevance += 1.0 * (word_match_count / len(query_terms))


            # Boost for priority file types (PDF, DOC, images, videos)
            ext = os.path.splitext(filename_lower)[1].lstrip(".")
            if ext in PRIORITY_EXTENSIONS:
                relevance += 0.5  # give a noticeable bump

            # Add snippet relevance boost – if query terms appear in snippet, increase relevance
            snippet_text = r["snippet"].lower() if r["snippet"] else ""
            if snippet_text:
                snippet_match_count = sum(1 for t in query_terms if t in snippet_text)
                if snippet_match_count:
                    # proportion of terms found in snippet, scaled up to 0.8
                    relevance += (snippet_match_count / len(query_terms)) * 0.8

            # Normalize query terms by stripping special characters for fuzzy matching
            cleaned_query = re.sub(r"[^a-z0-9]+", " ", query_clean)
            # Fuzzy ratio now compares cleaned versions to handle missing special chars
            fuzzy_ratio = difflib.SequenceMatcher(None, cleaned_query, cleaned_name.replace(" ", "")).ratio()
            
            # Combine relevance and fuzzy ratio (fuzzy contributes up to 0.5 points to avoid overpowering exact matches)
            final_score = relevance + (fuzzy_ratio * 0.5)
            
            # Score folder match
            folder_lower = str(Path(r["filepath"]).parent).lower()
            folder_match_count = sum(1 for t in query_terms if t in folder_lower)
            if folder_match_count:
                # Add up to 1.5 boost if folder matches query terms
                final_score += 1.5 * (folder_match_count / len(query_terms))
            
            # Apply extra multiplier for priority file types
            if ext in PRIORITY_EXTENSIONS:
                final_score *= 1.2

            scored_candidates.append({
                "filename": filename,
                "filepath": r["filepath"],
                "folder": str(Path(r["filepath"]).parent),
                "score": final_score,
                "snippet": r["snippet"] or "",
                "is_priority": ext in PRIORITY_EXTENSIONS
            })

        # Sort candidates: priority files first, then by score descending
        scored_candidates.sort(key=lambda x: (x["is_priority"], x["score"]), reverse=True)
        results = scored_candidates[:top_k]

    except Exception as e:
        print(f"[searcher] Optimized Search Error: {e}")
    finally:
        con.close()

    return results
