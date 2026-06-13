$ErrorActionPreference = "Stop"

Write-Host "Building Python Backend..."
cd "c:\Users\hagep\PROJECTS\MY APP\file-intelligence\python-backend"
& .\venv\Scripts\pyinstaller.exe file-intelligence-backend-x86_64-pc-windows-msvc.spec

Write-Host "Copying compiled backend to Tauri..."
Copy-Item "dist\file-intelligence-backend-x86_64-pc-windows-msvc.exe" "..\src-tauri\binaries\" -Force

Write-Host "Building Tauri Installer..."
cd "c:\Users\hagep\PROJECTS\MY APP\file-intelligence"
npm run tauri build

Write-Host "Build complete! Check src-tauri\target\release\bundle\msi\"
