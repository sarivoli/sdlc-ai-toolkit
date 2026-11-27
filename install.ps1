# SDLC AI Toolkit - one-line installer for Windows (PowerShell).
#   irm https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.ps1 | iex
# With arguments (install.py options such as --target all --workspace C:\work):
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/sarivoli/sdlc-ai-toolkit/main/install.ps1))) --target all
$ErrorActionPreference = 'Stop'

$RepoUrl = if ($env:SDLC_REPO_URL) { $env:SDLC_REPO_URL } else { 'https://github.com/sarivoli/sdlc-ai-toolkit.git' }
$Dest = if ($env:SDLC_HOME) { $env:SDLC_HOME } else { Join-Path $HOME '.sdlc-ai-toolkit' }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is required but not installed." }

$py = $null
foreach ($c in @(@('py', '-3'), @('python3'), @('python'))) {
    if (Get-Command $c[0] -ErrorAction SilentlyContinue) {
        $extra = @($c | Select-Object -Skip 1)
        & $c[0] @extra -c "import sys; sys.exit(sys.version_info < (3, 8))" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
}
if (-not $py) { throw "Python 3.8+ is required." }

if (Test-Path (Join-Path $Dest '.git')) {
    Write-Host "Updating $Dest ..."
    git -C $Dest pull --ff-only
} else {
    Write-Host "Cloning $RepoUrl -> $Dest ..."
    git clone --depth 1 $RepoUrl $Dest
}

$extra = @($py | Select-Object -Skip 1)
& $py[0] @extra (Join-Path $Dest 'install.py') @args
