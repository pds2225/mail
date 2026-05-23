# customer_intake 공통 (D:\mail 고정, D:\mail\.env 는 Python이 자동 로드)
$ErrorActionPreference = "Stop"

$RepoRoot = "D:\mail"
if (-not (Test-Path $RepoRoot)) {
    $RepoRoot = $PSScriptRoot
}
Set-Location $RepoRoot

$script:CustomerIntakePython = $null

function Get-CustomerIntakePython {
    if ($script:CustomerIntakePython) {
        return $script:CustomerIntakePython
    }
    $candidates = @(
        (Join-Path $RepoRoot ".venv\Scripts\python.exe"),
        (Join-Path $RepoRoot "venv\Scripts\python.exe")
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $script:CustomerIntakePython = (Resolve-Path $c).Path
            return $script:CustomerIntakePython
        }
    }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py -and $py.Source -notmatch "WindowsApps\\python\.exe$") {
        $script:CustomerIntakePython = $py.Source
        return $script:CustomerIntakePython
    }
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        $ver = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($ver -and (Test-Path $ver.Trim())) {
            $script:CustomerIntakePython = $ver.Trim()
            return $script:CustomerIntakePython
        }
    }
    throw "Python을 찾을 수 없습니다. D:\mail 에서: python -m venv .venv 후 pip install -r requirements.txt"
}

$reportsDir = "D:\customer_intake_reports"
if (-not (Test-Path $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}
