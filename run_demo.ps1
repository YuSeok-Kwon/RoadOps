$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$Runner = Join-Path $ProjectDir "07_scripts\20261113_roadops_run_agent_flow_v0_1.py"

if (Test-Path $VenvPython) {
    & $VenvPython $Runner --strict @args
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $Runner --strict @args
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python $Runner --strict @args
} else {
    Write-Error "Python 3.11 or newer is required. / Python 3.11 이상이 필요합니다."
    exit 1
}

exit $LASTEXITCODE
