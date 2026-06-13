import os
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import sys

from file_reader import extract_text, is_supported

# ── Watchdog ──────────────────────────────────────────────────────────────────
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ── Persistent data directory ─────────────────────────────────────────────────
# When frozen by PyInstaller, __file__ points to a temp extraction folder that
# is wiped on every launch. We must use %APPDATA% for persistent storage.
def _get_data_dir() -> str:
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    data_dir = os.path.join(appdata, "FileIntelligence")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DATA_DIR = _get_data_dir()
SQLITE_PATH = os.path.join(DATA_DIR, "metadata.db")

IGNORE_DIRS = {
    "Windows", "Program Files", "Program Files (x86)", "ProgramData",
    "System Volume Information", "$Recycle.Bin", "Boot", "boot",
    "Recovery", "MSOCache", "WindowsApps",
    "AppData", "Local Settings", "Application Data",
    "node_modules", "venv", ".venv", "env", ".env",
    "__pycache__", ".git", ".svn", ".hg", ".idea", ".vscode",
    ".npm", ".cache", ".tox", "dist", "build",
}

# High-value folders to index first for instant search availability
PRIORITY_FOLDERS = {"Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"}

# Skip files larger than 500MB
MAX_FILE_SIZE = 500 * 1024 * 1024

# Skip these file extensions
SKIP_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".obj", ".bin",
    ".iso", ".img", ".dmg", ".zip", ".rar", ".7z",
    ".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv",
    ".tar", ".gz", ".bz2", ".xz",
    ".crdownload", ".part", ".tmp", ".download", ".pending"
}

# Use the persistent data dir (not __file__) so we never accidentally index our own DB
_SELF_DIR = DATA_DIR

class FileIndexer:
    def __init__(self, folders: List[str] = None):
        self.folders: List[str] = folders or []
        self._lock = threading.Lock()
        self._is_indexing = False
        self._observer: Observer = None
        self._batch_size = 100
        
        self._pending_files = {}
        self._pending_lock = threading.Lock()
        
        self._init_sqlite()
        
        self._worker_thread = threading.Thread(target=self._process_pending_files, daemon=True)
        self._worker_thread.start()

    def _process_pending_files(self):
        while True:
            time.sleep(1.0)
            now = time.time()
            to_process = []
            with self._pending_lock:
                for filepath, timestamp in list(self._pending_files.items()):
                    if now - timestamp > 2.0:
                        to_process.append(filepath)
                        del self._pending_files[filepath]
            
            for filepath in to_process:
                self.index_single_file(filepath)

    def queue_file(self, filepath: str):
        with self._pending_lock:
            self._pending_files[filepath] = time.time()

    def remove_from_queue(self, filepath: str):
        with self._pending_lock:
            self._pending_files.pop(filepath, None)

    def _init_sqlite(self):
        """Initialize the original SQLite schema."""
        con = sqlite3.connect(SQLITE_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT UNIQUE,
                filename TEXT,
                date_indexed TEXT,
                file_size INTEGER,
                snippet TEXT
            )
        """)
        con.execute("CREATE TABLE IF NOT EXISTS watched_folders (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE)")
        con.execute("CREATE TABLE IF NOT EXISTS indexing_progress (id INTEGER PRIMARY KEY, folder TEXT UNIQUE, indexed_count INTEGER, last_updated TEXT)")
        
        # Create FTS5 table for lightning-fast keyword search
        con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS file_search_index USING fts5(filename, snippet, content='indexed_files', content_rowid='id')")
        
        # Add indexes for faster queries
        con.execute("CREATE INDEX IF NOT EXISTS idx_filename ON indexed_files(filename)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_filepath ON indexed_files(filepath)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_file_size ON indexed_files(file_size)")
        
        con.commit()
        con.close()

    def _save_folder(self, folder: str):
        con = sqlite3.connect(SQLITE_PATH)
        con.execute("INSERT OR IGNORE INTO watched_folders (path) VALUES (?)", (folder,))
        con.commit()
        con.close()

    def load_saved_folders(self) -> List[str]:
        con = sqlite3.connect(SQLITE_PATH)
        rows = con.execute("SELECT path FROM watched_folders").fetchall()
        con.close()
        return [r[0] for r in rows if os.path.isdir(r[0])]

    def process_file_item_fast(self, filepath: str) -> Dict[str, Any]:
        """Phase 1: Index filename + path only — NO file I/O. Extremely fast."""
        try:
            if os.path.abspath(filepath).startswith(_SELF_DIR):
                return None
            if not os.path.isfile(filepath):
                return None
            filename = os.path.basename(filepath)
            if filename.startswith(".") or filename.startswith("~$"):
                return None
            stat = os.stat(filepath)
            if stat.st_size > MAX_FILE_SIZE:
                return None
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in SKIP_EXTENSIONS:
                return None
            return {
                "filepath": filepath,
                "filename": filename,
                "date_indexed": datetime.now().isoformat(),
                "file_size": stat.st_size,
                "snippet": ""  # No text extraction in Phase 1
            }
        except:
            return None

    def process_file_item(self, filepath: str) -> Dict[str, Any]:
        """Phase 2: Full extraction including text snippet."""
        try:
            if os.path.abspath(filepath).startswith(_SELF_DIR):
                return None
            if not os.path.isfile(filepath):
                return None
            filename = os.path.basename(filepath)
            if filename.startswith(".") or filename.startswith("~$"):
                return None
            stat = os.stat(filepath)
            if stat.st_size > MAX_FILE_SIZE:
                return None
            file_ext = os.path.splitext(filename)[1].lower()
            if file_ext in SKIP_EXTENSIONS:
                return None
            text = extract_text(filepath)[:500]
            return {
                "filepath": filepath,
                "filename": filename,
                "date_indexed": datetime.now().isoformat(),
                "file_size": stat.st_size,
                "snippet": text
            }
        except:
            return None

    def flush_batch(self, batch: List[Dict]):
        """Commit batch to SQLite and sync FTS index."""
        if not batch: return
        con = sqlite3.connect(SQLITE_PATH)
        try:
            for item in batch:
                # 1. Update main table
                cursor = con.execute("""
                    INSERT OR REPLACE INTO indexed_files (filepath, filename, date_indexed, file_size, snippet)
                    VALUES (?, ?, ?, ?, ?)
                """, (item["filepath"], item["filename"], item["date_indexed"], item["file_size"], item["snippet"]))
                
                row_id = cursor.lastrowid
                
                # 2. Update FTS table incrementally
                # Delete old entry if exists
                con.execute("DELETE FROM file_search_index WHERE rowid = ?", (row_id,))
                # Insert new entry
                con.execute("""
                    INSERT INTO file_search_index (rowid, filename, snippet)
                    VALUES (?, ?, ?)
                """, (row_id, item["filename"], item["snippet"]))
            
            con.commit()
        except Exception as e:
            print(f"[indexer] DB Error: {e}")
        finally:
            con.close()

    def index_all_files(self):
        """Two-phase indexing:
        Phase 1 — filename-only walk (no file I/O). Search available in seconds.
        Phase 2 — text snippet extraction in background (slow, enriches results).
        """
        def _collect_folders():
            priority_folders = []
            for folder in self.folders:
                if not os.path.isdir(folder):
                    continue
                try:
                    for item in os.listdir(folder):
                        if item in PRIORITY_FOLDERS:
                            p = os.path.join(folder, item)
                            if os.path.isdir(p):
                                priority_folders.append(p)
                except Exception:
                    pass
            regular_folders = [f for f in self.folders if os.path.isdir(f)]
            # priority first, then full drives (de-duplicate order)
            seen = set()
            result = []
            for f in priority_folders + regular_folders:
                if f not in seen:
                    seen.add(f)
                    result.append(f)
            return result

        def _phase1():
            """Rapidly index filenames only — makes search available in seconds."""
            self._is_indexing = True
            indexed_count = 0
            all_folders = _collect_folders()
            all_file_paths = []  # collect for Phase 2

            with ThreadPoolExecutor(max_workers=16) as executor:
                batch = []
                for folder in all_folders:
                    if not os.path.isdir(folder):
                        continue
                    print(f"[indexer] Phase 1 scanning: {folder}")
                    for root, dirs, files in os.walk(folder):
                        dirs[:] = [d for d in dirs
                                   if d not in IGNORE_DIRS and not d.startswith(".")]
                        file_paths = [
                            os.path.join(root, f)
                            for f in files
                            if not f.startswith(".") and not f.startswith("~$")
                        ]
                        all_file_paths.extend(file_paths)
                        results = executor.map(self.process_file_item_fast, file_paths)
                        for item in results:
                            if item:
                                batch.append(item)
                                indexed_count += 1
                                if len(batch) >= self._batch_size:
                                    self.flush_batch(batch)
                                    batch = []
                if batch:
                    self.flush_batch(batch)

            self._is_indexing = False
            print(f"[indexer] Phase 1 complete: {indexed_count} files indexed. Search is ready!")

            # Kick off Phase 2 now that search is available
            threading.Thread(target=_phase2, args=(all_file_paths,), daemon=True).start()

        def _phase2(file_paths):
            """Enrich existing records with text snippets (background, non-blocking)."""
            print(f"[indexer] Phase 2 starting: extracting snippets for {len(file_paths)} files...")
            enriched = 0
            con = sqlite3.connect(SQLITE_PATH)
            try:
                for filepath in file_paths:
                    try:
                        text = extract_text(filepath)[:500]
                        if text:
                            row = con.execute(
                                "SELECT id FROM indexed_files WHERE filepath=?", (filepath,)
                            ).fetchone()
                            if row:
                                con.execute(
                                    "UPDATE indexed_files SET snippet=? WHERE id=?",
                                    (text, row[0])
                                )
                                con.execute("DELETE FROM file_search_index WHERE rowid=?", (row[0],))
                                con.execute(
                                    "INSERT INTO file_search_index (rowid, filename, snippet) "
                                    "SELECT id, filename, snippet FROM indexed_files WHERE id=?",
                                    (row[0],)
                                )
                                enriched += 1
                                if enriched % 500 == 0:
                                    con.commit()
                                    print(f"[indexer] Phase 2 progress: {enriched} snippets added...")
                    except Exception:
                        pass
                con.commit()
            finally:
                con.close()
            print(f"[indexer] Phase 2 complete: {enriched} snippets added.")

        threading.Thread(target=_phase1, daemon=True).start()

    def index_single_file(self, filepath: str):
        item = self.process_file_item(filepath)
        if item: self.flush_batch([item])

    def delete_file(self, filepath: str):
        """Remove a file from both main and FTS tables."""
        con = sqlite3.connect(SQLITE_PATH)
        try:
            # Get ID first to delete from FTS
            row = con.execute("SELECT id FROM indexed_files WHERE filepath=?", (filepath,)).fetchone()
            if row:
                row_id = row[0]
                con.execute("DELETE FROM indexed_files WHERE id=?", (row_id,))
                con.execute("DELETE FROM file_search_index WHERE rowid=?", (row_id,))
            con.commit()
        finally:
            con.close()

    def start_watching(self):
        handler = _IndexEventHandler(self)
        self._observer = Observer()
        for folder in self.folders:
            if os.path.isdir(folder):
                self._observer.schedule(handler, folder, recursive=True)
        self._observer.start()

    def stop_watching(self):
        if self._observer:
            self._observer.stop()
            self._observer.join()

    def total_indexed(self) -> int:
        con = sqlite3.connect(SQLITE_PATH)
        res = con.execute("SELECT count(*) FROM indexed_files").fetchone()
        con.close()
        return res[0] if res else 0

    @property
    def is_indexing(self) -> bool:
        return self._is_indexing

class _IndexEventHandler(FileSystemEventHandler):
    def __init__(self, indexer: FileIndexer):
        self._indexer = indexer

    def on_created(self, event):
        if not event.is_directory: self._indexer.queue_file(event.src_path)

    def on_modified(self, event):
        if not event.is_directory: self._indexer.queue_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._indexer.remove_from_queue(event.src_path)
            self._indexer.delete_file(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._indexer.remove_from_queue(event.src_path)
            self._indexer.delete_file(event.src_path)
            self._indexer.queue_file(event.dest_path)
