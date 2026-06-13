# File Intelligence

File Intelligence is a lightning-fast, privacy-first, local desktop search application for Windows. It functions similarly to macOS Spotlight or Windows PowerToys Run, but integrates a highly optimized, custom file indexer that supports natural language queries and deep content parsing.

## 🚀 Key Features

- **Instant Search:** Returns search results in milliseconds using an advanced SQLite Full-Text Search (FTS5) engine.
- **Natural Language Parsing:** Automatically filters out stop words (e.g., "find", "in", "folder") and matches keywords against folder directory paths (e.g., searching for "resume in desktop").
- **Deep Content Parsing:** Extracts and indexes text from inside documents, including PDFs, Microsoft Word (`.docx`), Microsoft Excel (`.xlsx`), and plain text files.
- **Smart Background Indexing:** Actively watches your filesystem using native OS events. It intelligently debounces file operations (like active downloads) to prevent CPU spikes while keeping your search index seamlessly up to date.
- **Privacy First:** 100% of the processing, indexing, and searching happens locally on your machine. Your data never leaves your computer.
- **Standalone Application:** Bundled with a self-contained Python runtime inside the Tauri installer. No external dependencies are required for the end user.

## 🛠️ Technology Stack

**Frontend:**
- [Tauri](https://tauri.app/) (Application Shell & System integrations)
- [React](https://reactjs.org/) + [Vite](https://vitejs.dev/) (UI & Component Architecture)
- CSS (Glassmorphism aesthetics & dynamic animations)

**Backend:**
- [Python](https://www.python.org/)
- [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn (HTTP Server)
- [SQLite FTS5](https://sqlite.org/fts5.html) (Search Engine Database)
- `watchdog` (Filesystem monitoring)
- `slowapi` (Rate Limiting)

## 📦 Local Development Setup

### Prerequisites
Before you begin, ensure you have the following installed on your system:
- [Node.js](https://nodejs.org/) (v16 or newer)
- [Rust](https://www.rust-lang.org/) (Required for Tauri)
- [Python](https://www.python.org/downloads/) (3.9 or newer)

### 1. Backend Setup
1. Navigate to the Python backend directory:
   ```bash
   cd python-backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install the required Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Frontend Setup
1. Navigate back to the root project directory:
   ```bash
   cd ..
   ```
2. Install the Node modules:
   ```bash
   npm install
   ```

### 3. Running the Application locally
To start the application in development mode (which will automatically spawn both the Vite dev server and the Python FastAPI server):

```bash
npm run tauri dev
```

## 🔨 Building the Installer

The project includes a custom PowerShell script that fully automates the build pipeline. It compiles the Python backend into a standalone Windows executable (`.exe`) using PyInstaller, packages it into the Tauri binary folder, and builds the final installer MSI.

To generate a production build:
```powershell
.\build_installer.ps1
```

Once the process completes, your installers will be generated inside:
`src-tauri\target\release\bundle\`

## 🔒 Security

File Intelligence takes local security seriously:
- **Localhost Binding:** The backend API is strictly bound to `127.0.0.1`.
- **Input Sanitization:** Search inputs are heavily sanitized to prevent SQL Injection within the local database.
- **Rate Limiting:** Protects the FastAPI endpoints from localized spam requests that could otherwise freeze system resources.

## 📄 License
This project is licensed under the MIT License.
