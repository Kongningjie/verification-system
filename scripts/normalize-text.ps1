[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$repoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repoRoot) {
    throw "The current directory is not inside a Git repository."
}

$repoRoot = [System.IO.Path]::GetFullPath($repoRoot)
$repoPrefix = $repoRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar
$frozenDirectory = Join-Path $repoRoot "docs/implementation0plan"
$frozenCandidates = @(Get-ChildItem -LiteralPath $frozenDirectory -Filter "00_*.md" -File)
if ($frozenCandidates.Count -ne 1) {
    throw "Expected exactly one frozen plan matching docs/implementation0plan/00_*.md."
}

$frozenPath = $frozenCandidates[0].FullName
$frozenSha256 = "B22EEEA0F7A1AE32CA93B99F459AB249FE65625A1AA70590613B237E0CA4A7F7"

function Assert-FrozenPlanUnchanged {
    $actualHash = (Get-FileHash -LiteralPath $frozenPath -Algorithm SHA256).Hash
    if ($actualHash -ne $frozenSha256) {
        throw "The frozen plan SHA-256 changed. Text normalization was stopped."
    }
}

Assert-FrozenPlanUnchanged

$textExtensions = @(
    ".css", ".html", ".ini", ".js", ".json", ".jsx", ".md", ".ps1",
    ".py", ".toml", ".ts", ".tsx", ".txt", ".vue", ".xml", ".yaml", ".yml"
)
$textFileNames = @(".editorconfig", ".gitattributes", ".gitignore", "pre-commit")

$trackedFiles = @(& git -C $repoRoot -c core.quotepath=false ls-files)
$untrackedFiles = @(& git -C $repoRoot -c core.quotepath=false ls-files --others --exclude-standard)
$candidateFiles = @($trackedFiles + $untrackedFiles | Sort-Object -Unique)
$changedFiles = [System.Collections.Generic.List[string]]::new()

foreach ($relativePath in $candidateFiles) {
    $fileName = [System.IO.Path]::GetFileName($relativePath)
    $extension = [System.IO.Path]::GetExtension($relativePath).ToLowerInvariant()
    if (($textFileNames -notcontains $fileName) -and ($textExtensions -notcontains $extension)) {
        continue
    }

    $fullPath = [System.IO.Path]::GetFullPath((Join-Path $repoRoot $relativePath))
    if (-not $fullPath.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "A path outside the repository was rejected: $relativePath"
    }
    if ($fullPath -eq $frozenPath) {
        continue
    }
    if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
        continue
    }

    $original = [System.IO.File]::ReadAllText($fullPath)
    $normalized = $original.Replace("`r`n", "`n").Replace("`r", "`n")
    $normalized = [System.Text.RegularExpressions.Regex]::Replace($normalized, "[ `t]+(?=`n|$)", "")
    $normalized = $normalized.TrimEnd([char[]]@("`n")) + "`n"

    if ($original -ceq $normalized) {
        continue
    }

    $gitPath = $relativePath.Replace("\", "/")
    $changedFiles.Add($gitPath)
    if (-not $Check) {
        $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($fullPath, $normalized, $utf8WithoutBom)
    }
}

Assert-FrozenPlanUnchanged

if ($Check -and $changedFiles.Count -gt 0) {
    Write-Host "Text files that need normalization:" -ForegroundColor Red
    $changedFiles | ForEach-Object { Write-Host "  $_" }
    Write-Host "Run: powershell -ExecutionPolicy Bypass -File scripts/normalize-text.ps1" -ForegroundColor Yellow
    exit 1
}

if ($Check) {
    Write-Host "Text quality check passed; frozen plan SHA-256 passed."
} else {
    Write-Host "Normalized $($changedFiles.Count) text file(s); frozen plan was unchanged."
}
