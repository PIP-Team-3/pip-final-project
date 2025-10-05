# Example server startup script - Copy to start_server.ps1 and add your keys
# This file is safe to commit (no secrets)

# Load environment variables from .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$key" -Value $value
    }
}

# Start the server
& .venv\Scripts\python.exe -m uvicorn app.main:app --app-dir api --log-level info --workers 1
