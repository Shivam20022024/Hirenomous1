# start_pipeline.ps1
# This script validates environment, checks database connectivity, and starts the backend server.

echo "`n--- [PIPELINE STARTUP CLOUD-READY] ---"
$port = 8001
$host_addr = "0.0.0.0"
$check_url = "http://localhost:$port/"

# 1. Validate Environment
echo "Checking environment configuration..."
if (-not (Test-Path ".env.local")) {
    echo "ERROR: .env.local not found! Please create it from .env.example"
    exit 1
}
echo "Environment file found."

# 2. Check MongoDB Connectivity
echo "Verifying MongoDB connectivity..."
$python_cmd = "python"
if (Test-Path "venv\Scripts\python.exe") {
    $python_cmd = ".\venv\Scripts\python.exe"
}

# Use the existing diag_mongo.py to check connection
$mongoCheck = & $python_cmd diag_mongo.py | Out-String
echo $mongoCheck

if ($mongoCheck -match "Ping successful") {
    echo "MongoDB is ONLINE."
} else {
    echo "WARNING: MongoDB might be offline or unreachable. Check your MONGODB_URI."
}

# 3. Kill any existing process on port 8001
echo "Cleaning up port $port..."
$processId = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -First 1

if ($processId) {
    echo "Found process $processId using port $port. Terminating..."
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# 4. Start the FastAPI backend
echo "Starting Backend Server (app.main:app) on port $port..."
$env:PYTHONPATH = "."

$logFile = "server_8001_log.txt"
$errFile = "server_8001_err.txt"

if (Test-Path $logFile) { Remove-Item $logFile }
if (Test-Path $errFile) { Remove-Item $errFile }

Start-Process -NoNewWindow -FilePath $python_cmd -ArgumentList "-m uvicorn app.main:app --host $host_addr --port $port --reload" -RedirectStandardOutput $logFile -RedirectStandardError $errFile

# 5. Wait and verify with Health Check
echo "Waiting for API initialization (Max 30s)..."
$maxAttempts = 15
$attempt = 1
$success = $false

while ($attempt -le $maxAttempts) {
    echo "Health check attempt $attempt/$maxAttempts..."
    try {
        $response = Invoke-RestMethod -Uri $check_url -Method Get -TimeoutSec 2 -ErrorAction Stop
        if ($response) {
            echo "SUCCESS: Backend is responding at $check_url"
            $success = $true
            break
        }
    } catch {
        # Wait before next attempt
        Start-Sleep -Seconds 2
    }
    $attempt++
}

if ($success) {
    echo "--- [STABLE BOOT COMPLETE] ---"
    echo "Backend is now RUNNING on port $port."
    echo "Logs are being written to $logFile"
} else {
    echo "--- [BOOT FAILED] ---"
    echo "ERROR: Backend failed to respond."
    echo "LAST ERROR LOG ENTRIES:"
    if (Test-Path $errFile) {
        Get-Content $errFile -Tail 20
    }
}
echo "`n"

