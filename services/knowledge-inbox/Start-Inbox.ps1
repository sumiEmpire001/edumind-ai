param(
    [string]$Backend = "https://edumind-test-api.onrender.com",
    [string]$Folder = "$PSScriptRoot\EduMind-Knowledge-Inbox",
    [switch]$Once,
    [switch]$RetryFailed
)
$ErrorActionPreference = "Stop"
$secureToken = Read-Host "Paste your submission-only EduMind inbox credential" -AsSecureString
$tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
try {
    $env:EDUMIND_INBOX_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    $inboxArgs = @("$PSScriptRoot\inbox.py", "--backend", $Backend, "--folder", $Folder)
    if ($Once) { $inboxArgs += "--once" }
    if ($RetryFailed) { $inboxArgs += "--retry-failed" }
    python @inboxArgs
    if ($LASTEXITCODE -ne 0) { throw "Inbox stopped. Review its safe error messages." }
} finally {
    Remove-Item Env:EDUMIND_INBOX_TOKEN -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    $secureToken.Dispose()
}
