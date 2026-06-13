$ErrorActionPreference = "Stop"

Write-Host "Building Python Backend..."
cd "c:\Users\hagep\PROJECTS\MY APP\file-intelligence\python-backend"
& .\venv\Scripts\pyinstaller.exe file-intelligence-backend-x86_64-pc-windows-msvc.spec

Write-Host "Copying compiled backend to Tauri..."
Copy-Item "dist\file-intelligence-backend-x86_64-pc-windows-msvc.exe" "..\src-tauri\binaries\" -Force

Write-Host "Signing Python backend..."
$certPath = "C:\certificate.pfx"
$certPassword = "YourPassword123"

$signtool = Get-ChildItem "C:\Program Files (x86)\Windows Kits" -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -like "*x64*" } |
            Select-Object -First 1 -ExpandProperty FullName

if ($signtool) {
    Write-Host "Found signtool: $signtool"
    & $signtool sign /fd SHA256 /p $certPassword /f $certPath /t http://timestamp.sectigo.com "..\src-tauri\binaries\file-intelligence-backend-x86_64-pc-windows-msvc.exe"
    Write-Host "Backend signed!"
} else {
    Write-Host "signtool not found, skipping..."
}

Write-Host "Building Tauri Installer..."
cd "c:\Users\hagep\PROJECTS\MY APP\file-intelligence"
npm run tauri build

if ($signtool) {
    $msiPath = Get-ChildItem "src-tauri\target\release\bundle\msi\*.msi" | Select-Object -First 1 -ExpandProperty FullName
    if ($msiPath) {
        & $signtool sign /fd SHA256 /p $certPassword /f $certPath /t http://timestamp.sectigo.com $msiPath
        Write-Host "Installer signed: $msiPath"
    }
}

Write-Host "Build complete!"