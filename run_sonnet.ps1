$ErrorActionPreference = "Stop"
$prompt = Get-Content "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\claude_sonnet_prompt.txt" -Raw
$result = claude -p $prompt --model sonnet --effort medium --dangerously-skip-permissions 2>&1
$result | Out-File -FilePath "C:\Users\Admin\Desktop\stock test\open code v5 claude prompt\sonnet_output.txt" -Encoding utf8
Write-Output "DONE"
