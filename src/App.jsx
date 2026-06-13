import { useState, useEffect, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import "./App.css";

const API = "http://127.0.0.1:8000";

const getTimeoutSignal = (ms) => {
  if (AbortSignal.timeout) return AbortSignal.timeout(ms);
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
};

function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

const Icons = {
  Search: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  ),
  Folder: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.93a2 2 0 0 1-1.66-.9l-.82-1.2A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13c0 1.1.9 2 2 2Z" />
    </svg>
  ),
  File: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  ),
  Copy: () => (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
      <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
    </svg>
  ),
  Check: () => (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
  Close: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  ),
  Image: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
      <circle cx="9" cy="9" r="2" />
      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
    </svg>
  ),
  Video: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="m22 8-6 4 6 4V8Z" />
      <rect width="14" height="12" x="2" y="6" rx="2" ry="2" />
    </svg>
  ),
  Code: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  ),
  Power: () => (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M18.36 6.64a9 9 0 1 1-12.73 0" />
      <line x1="12" y1="2" x2="12" y2="12" />
    </svg>
  ),
};

export default function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [backendReady, setBackendReady] = useState(false);
  // UI toggle controlling panel visibility only – does NOT affect background indexing/fetching
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(null);
  const [indexProgress, setIndexProgress] = useState({
    total_files: 0,
    is_indexing: false,
  });
  const searchRef = useRef(null);
  const debouncedQuery = useDebounce(query, 200);

  // Focus input when panel opens
  useEffect(() => {
    if (isExpanded && searchRef.current) {
      setTimeout(() => searchRef.current?.focus(), 300);
    }
    if (!isExpanded) {
      setQuery("");
      setResults([]);
    }
  }, [isExpanded]);

  // Adjust window size and layout when expand state changes
  useEffect(() => {
    try {
      invoke("set_expanded", { expanded: isExpanded });
    } catch (e) {
      console.warn("Failed to set window expansion:", e);
    }
  }, [isExpanded]);

  // ── Backend Connectivity & Status ──────────────────────────────────────────
  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${API}/status`, {
          signal: getTimeoutSignal(3000),
        });
        if (r.ok) {
          const data = await r.json();
          setBackendReady(data.ready_for_search ?? true);
          setIndexProgress(data);
        }
      } catch (e) {
        setBackendReady(false);
      }
      setTimeout(check, 2000);
    };
    check();
  }, []);

  // ── Search Logic ──────────────────────────────────────────────────────────
  useEffect(() => {
    if (!backendReady || !debouncedQuery.trim()) {
      setResults([]);
      return;
    }
    const doSearch = async () => {
      setLoading(true);
      try {
        const r = await fetch(`${API}/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: debouncedQuery, top_k: 20 }),
        });
        const data = await r.json();
        setResults(data.results || []);
      } catch (e) {
        setResults([]);
      }
      setLoading(false);
    };
    doSearch();
  }, [debouncedQuery, backendReady]);

  const handleCopy = useCallback((path) => {
    navigator.clipboard.writeText(path);
    setCopied(path);
    setTimeout(() => setCopied(null), 1500);
  }, []);

  const handleOpenFolder = useCallback(async (path) => {
    try {
      await invoke("open_folder", { path });
    } catch (e) {}
  }, []);

  const handleOpenFile = useCallback(
    async (path) => {
      try {
        await invoke("open_file", { path });
      } catch (e) {
        handleCopy(path);
      }
    },
    [handleCopy],
  );

  const handleClose = useCallback(async () => {
    try {
      const windowInstance = getCurrentWindow();
      await windowInstance.close();
    } catch (e) {
      console.warn("Failed to close window", e);
    }
  }, []);

  const getFileIcon = (filename) => {
    const ext = filename.split(".").pop().toLowerCase();
    if (["png", "jpg", "jpeg", "gif", "svg", "webp"].includes(ext))
      return <Icons.Image />;
    if (["mp4", "mkv", "avi", "mov"].includes(ext)) return <Icons.Video />;
    if (
      [
        "py",
        "js",
        "ts",
        "rs",
        "cpp",
        "c",
        "java",
        "go",
        "sql",
        "html",
        "css",
      ].includes(ext)
    )
      return <Icons.Code />;
    return <Icons.File />;
  };

  const getStatusText = () => {
    if (!backendReady && indexProgress.is_indexing) {
      return `Indexing... (${indexProgress.total_files} files)`;
    }
    if (!backendReady) return "Connecting...";
    if (indexProgress.is_indexing)
      return `Indexing (${indexProgress.total_files} files)`;
    return `Ready (${indexProgress.total_files} files indexed)`;
  };

  return (
    <div className="root-container">
      {/* ── Tab handle — always visible on the right edge ── */}
      <div
        className={`edge-tab ${isExpanded ? "tab-hidden" : ""}`}
        onClick={() => setIsExpanded(true)}
      >
        <div
          className="status-dot"
          style={{ background: backendReady ? "#00f5a0" : "#feb47b" }}
        />
        <div className="tab-icon">
          <Icons.Search />
        </div>
        <div className="tab-label">SEARCH</div>
      </div>

      {/* ── Slide-in panel ── */}
      <div
        className={`slide-panel ${isExpanded ? "panel-open" : "panel-closed"}`}
      >
        <div className="panel-header">
          <div className="panel-header-left">
            <div
              className="status-dot"
              style={{ background: backendReady ? "#00f5a0" : "#feb47b" }}
            />
            <span className="panel-title">File Intelligence</span>
            <span className="status-text">{getStatusText()}</span>
          </div>
          <div className="panel-header-actions">
            <button
              className="close-btn"
              onClick={() => setIsExpanded(false)}
              title="Collapse Drawer"
            >
              <Icons.Close />
            </button>
            <button
              className="close-btn exit-btn"
              onClick={handleClose}
              title="Exit Application"
            >
              <Icons.Power />
            </button>
          </div>
        </div>

        <div className="search-section">
          <input
            ref={searchRef}
            type="text"
            className="panel-input"
            placeholder={backendReady ? "Search files..." : "Connecting..."}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={!backendReady}
          />
          {loading && <div className="panel-spinner" />}
        </div>

        <div className="panel-results">
          {query && !loading && results.length > 0 && (
            <div className="results-count" style={{ padding: "0 4px 8px", fontSize: "11px", color: "var(--text-2)", fontWeight: 500 }}>
              Fetched {results.length} files
            </div>
          )}
          {results.map((res, i) => (
            <div key={res.filepath + i} className="panel-card">
              <div
                className="card-main"
                onClick={() => handleOpenFile(res.filepath)}
              >
                <span className="card-icon">{getFileIcon(res.filename)}</span>
                <div className="card-info">
                  <span className="card-name">{res.filename}</span>
                  <span className="card-path">{res.folder}</span>
                </div>
              </div>
              <div className="card-actions">
                <button
                  onClick={() => handleOpenFolder(res.filepath)}
                  title="Open Folder"
                >
                  <Icons.Folder />
                </button>
                <button
                  onClick={() => handleCopy(res.filepath)}
                  title="Copy Path"
                >
                  {copied === res.filepath ? <Icons.Check /> : <Icons.Copy />}
                </button>
              </div>
            </div>
          ))}
          {query && results.length === 0 && !loading && (
            <div className="panel-empty">No results found</div>
          )}
          {!query && backendReady && (
            <div className="panel-empty" style={{ opacity: 0.5 }}>
              Type to search your PC
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
