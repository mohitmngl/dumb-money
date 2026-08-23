$ErrorActionPreference = "Stop"

$dir = "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\dumbmoney\agy testing\mimo_to_antigravity_realistic_3d_solar_system"
$promptFile = Join-Path $dir "ANTIGRAVITY_BUILDER_PROMPT.md"
$log = Join-Path $dir "antigravity-run.log"

Set-Location -LiteralPath $dir
$env:Path = "$env:LOCALAPPDATA\agy\bin;$env:Path"

"[$(Get-Date -Format o)] Starting Antigravity builder run in $dir" | Set-Content -LiteralPath $log

$prompt = Get-Content -LiteralPath $promptFile -Raw

agy --model "Gemini 3.1 Pro (High)" `
  --dangerously-skip-permissions `
  --print-timeout 60m `
  --print $prompt

$exitCode = $LASTEXITCODE
"[$(Get-Date -Format o)] Antigravity exited with code $exitCode" | Add-Content -LiteralPath $log

if ($exitCode -ne 0) {
  exit $exitCode
}

Get-ChildItem -LiteralPath $dir -Force | Select-Object Mode,Length,LastWriteTime,Name | Format-Table -AutoSize | Out-String | Add-Content -LiteralPath $log
