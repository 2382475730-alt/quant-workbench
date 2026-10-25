param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$workspaceRoot = [IO.Path]::GetFullPath((Join-Path $projectRoot '..'))
$baselineRoot = [IO.Path]::GetFullPath((Join-Path $workspaceRoot 'research_library\baseline_20261024'))
$libraryRoot = Join-Path $baselineRoot 'quant_workbench'
$auditRoot = Join-Path $projectRoot 'runtime\cleanup'
New-Item -ItemType Directory -Path $auditRoot -Force | Out-Null
$targets = [Collections.Generic.List[string]]::new()
$names = @('pork_stocks_v1', 'small_capital_pork_v1', 'small_capital_pork_v1r1', 'entry_timing_v1', 'standalone_sector_v1')
foreach ($name in $names) {
    foreach ($parent in @('artifacts', 'research', 'reports', 'src\quant_workbench', 'data')) {
        $targets.Add((Join-Path $libraryRoot "$parent\$name"))
    }
    $targets.Add((Join-Path $libraryRoot "config\$name.json"))
    $targets.Add((Join-Path $libraryRoot "tests\test_$name.py"))
}
$targets.Add((Join-Path $libraryRoot 'tests\test_small_capital_pork_adapter.py'))
foreach ($file in Get-ChildItem -LiteralPath (Join-Path $libraryRoot 'scripts') -File) {
    if ($file.Name -match '^(pork_|entry_timing_|standalone_sector_)') { $targets.Add($file.FullName) }
}
foreach ($name in @('Start_EntryTiming_Archived.bat','Start_EntryTiming.bat','Start_Pork_Research.bat','Start_StandaloneETF_Archived.bat','当前工作台说明.md')) {
    $targets.Add((Join-Path $libraryRoot $name))
}
# The superseded outer sector application contains only the old BK0882 research.
# Its session key and all existing environments are explicitly excluded.
foreach ($name in @('artifacts','config','data\market','data\raw','data\migrations','data\catalog.duckdb',
                    'data\management\management.sqlite3','data\management\desktop.log','docs','scripts','src','tests','tmp',
                    'FinancialAnalysis.bat','project_status.md','README.md','run_gui.ps1')) {
    $targets.Add((Join-Path $baselineRoot $name))
}
foreach ($relative in @('runtime\exports\pork','runtime\explorations\pork','runtime\verification_artifacts')) {
    $candidate = Join-Path $projectRoot $relative
    if ($relative -eq 'runtime\verification_artifacts') {
        foreach ($file in Get-ChildItem -LiteralPath $candidate -File -ErrorAction SilentlyContinue) {
            if ($file.Name -match 'pork|养殖|entry_timing|standalone') { $targets.Add($file.FullName) }
        }
    } else { $targets.Add($candidate) }
}
$resolvedTargets = @($targets | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object {
    $absolute = (Resolve-Path -LiteralPath $_).Path
    if (-not ($absolute.StartsWith($baselineRoot + '\', [StringComparison]::OrdinalIgnoreCase) -or
              $absolute.StartsWith((Join-Path $projectRoot 'runtime') + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw "Target escaped authorized roots: $absolute"
    }
    if ($absolute -match '(\.env|\.venv|session\.key)(\\|$)') { throw 'Protected target detected' }
    $item = Get-Item -LiteralPath $absolute -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Reparse point in target' }
    $absolute
} | Sort-Object -Unique)
$files = @()
foreach ($target in $resolvedTargets) {
    $item = Get-Item -LiteralPath $target -Force
    $items = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $target -Recurse -Force) } else { @($item) }
    foreach ($entry in $items) {
        if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Nested reparse point in target' }
        if (-not $entry.PSIsContainer) {
            $files += [pscustomobject][ordered]@{path=$entry.FullName; bytes=$entry.Length; sha256=(Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        }
    }
}
$manifestPath = Join-Path $auditRoot 'deletion_manifest.json'
if (Test-Path -LiteralPath $manifestPath) { throw 'Existing completed deletion manifest must not be overwritten' }
$record = [ordered]@{
    authorization='2026-10-25 user explicitly requested deletion of all former broad-livestock and pig research, including the baseline'
    status='planned'; created_at=(Get-Date -Format o); targets=$resolvedTargets; files=$files
    protected=@('workspace .env and existing environments','baseline data/management/session.key',
                'quant_workbench shared raw/normalized data and non-pork company/index/small-capital research')
}
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $auditRoot 'deletion_plan.json') -Encoding utf8
Write-Output "Planned targets: $($resolvedTargets.Count); files: $($files.Count); bytes: $(($files | Measure-Object bytes -Sum).Sum)"
if (-not $Apply) { return }
# Native PowerShell throughout: exact resolved targets only, no shell interpolation.
foreach ($target in $resolvedTargets) { Remove-Item -LiteralPath $target -Recurse -Force }
$remaining = @($resolvedTargets | Where-Object { Test-Path -LiteralPath $_ })
if ($remaining.Count) { throw 'Deletion incomplete; retain plan for recovery audit' }
$record.status='deleted'
$record['completed_at']=(Get-Date -Format o)
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8
Write-Output 'All listed targets absent; deletion manifest recorded.'
