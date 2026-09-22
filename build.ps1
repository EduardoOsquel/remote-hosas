.\.venv\Scripts\python.exe -m PyInstaller --noconfirm RemoteHosas.spec
if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
