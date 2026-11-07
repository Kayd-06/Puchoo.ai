$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
# Match application startup: default relative DATABASE_URL is rooted at the repo.
Push-Location $RepoRoot
try {
    & (Join-Path $RepoRoot "venv/Scripts/python.exe") -m alembic -c backend/alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migration failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}
