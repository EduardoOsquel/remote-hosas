.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --onefile --windowed --name RemoteHosas --icon assets/remote-hosas.ico --add-data "assets;assets" --exclude-module pytest launcher.py
if ($LASTEXITCODE -ne 0) { throw "Executable build failed." }
