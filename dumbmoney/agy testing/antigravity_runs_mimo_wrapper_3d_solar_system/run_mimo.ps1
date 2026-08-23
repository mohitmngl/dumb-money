$ErrorActionPreference = "Stop"

$dir = "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\antigravity_runs_mimo_wrapper_3d_solar_system"
$prompt = Join-Path $dir "MIMO_PROMPT.md"
$log = Join-Path $dir "mimo-run.log"

Set-Location -LiteralPath $dir

"[$(Get-Date -Format o)] Starting Mimo run in $dir" | Set-Content -LiteralPath $log

mimo run `
  --dir "$dir" `
  --dangerously-skip-permissions `
  --title "Wrapper Realistic 3D Solar System" `
  "Read the attached MIMO_PROMPT.md and implement it completely. Keep every generated file inside the current directory only." `
  --file "$prompt"

$exitCode = $LASTEXITCODE
"[$(Get-Date -Format o)] Mimo exited with code $exitCode" | Add-Content -LiteralPath $log

if ($exitCode -ne 0) {
  exit $exitCode
}

Get-ChildItem -LiteralPath $dir -Force | Select-Object Mode,Length,LastWriteTime,Name | Format-Table -AutoSize | Out-String | Add-Content -LiteralPath $log
