$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (Get-Command py -ErrorAction SilentlyContinue) {
  py -3 "$repoRoot/scripts/bootstrap.py" @args
} else {
  python "$repoRoot/scripts/bootstrap.py" @args
}
