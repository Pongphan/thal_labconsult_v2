[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9._-]*$')]
    [string]$Repository,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9._/-]*$')]
    [string]$Branch,
    [string]$OutputDirectory
)

# Prepare reviewable local artifacts only. Never invoke gh, add a remote, stage,
# commit, push, copy a workflow into another repository, or alter protection.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
& git check-ref-format --branch $Branch | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Invalid Git branch name.' }
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $projectRoot ('artifacts\ci-activation-' + [guid]::NewGuid().ToString('N'))
}
if (Test-Path -LiteralPath $OutputDirectory) { throw 'Choose a new output directory; existing files are preserved.' }

$gitRoot = & git -C $projectRoot rev-parse --show-toplevel 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine Git root; run this from the intended checkout.' }
$remotes = @(& git -C $projectRoot remote)
if ($LASTEXITCODE -ne 0) { throw 'Cannot read checkout remotes.' }
$origin = $null
if ($remotes -contains 'origin') {
    $origin = & git -C $projectRoot remote get-url origin
    if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve origin.' }
}
if ($origin) {
    $remoteRepository = $null
    if ($origin -match '^https://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$') { $remoteRepository = $Matches[1] }
    elseif ($origin -match '^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$') { $remoteRepository = $Matches[1] }
    if (-not $remoteRepository -or $remoteRepository -ine $Repository) {
        throw 'The explicit repository does not match the current GitHub origin. Use the intended checkout; no files were written.'
    }
}

$ruleset = Get-Content -LiteralPath (Join-Path $projectRoot '.github\required-checks.ruleset.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$ruleset.conditions.ref_name.include = @('refs/heads/' + $Branch)
New-Item -ItemType Directory -Path $OutputDirectory | Out-Null
$rulesetPath = Join-Path ([IO.Path]::GetFullPath($OutputDirectory)) 'required-checks.ruleset.json'
[IO.File]::WriteAllText($rulesetPath, ($ruleset | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
$quotedRuleset = $rulesetPath.Replace("'", "''")
$encodedBranch = [Uri]::EscapeDataString($Branch)
$commands = @"
# Target: https://github.com/$Repository ; branch: $Branch
# PRECONDITIONS: commit/push only the reviewed project and correct root workflow;
# confirm a successful hosted thallink-quality run, inspect existing rulesets,
# and ensure no equivalent ruleset already exists. These commands are not executed.
gh repo view '$Repository' --json nameWithOwner,url,defaultBranchRef
gh api 'repos/$Repository/branches/$encodedBranch'
gh api 'repos/$Repository/rulesets'
gh run list --repo '$Repository' --branch '$Branch' --limit 10
# Only after the preconditions and repository authorization are satisfied:
gh api --method POST 'repos/$Repository/rulesets' --input '$quotedRuleset'
# Inspect returned ID, then prove an intentionally failing PR is blocked and a
# corrected PR passes. A successful POST alone does not prove enforcement.
"@
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'REVIEW_COMMANDS.txt'), $commands, [Text.UTF8Encoding]::new($false))
$record = [ordered]@{
    status = 'prepared_only_not_activated'
    repository = $Repository
    branch = $Branch
    git_root = $gitRoot
    origin = $origin
    origin_matches_target = [bool]$origin
    required_check = 'thallink-quality'
    workflow_source = Join-Path $projectRoot '.github\workflows\quality.yml'
    workflow_root = Join-Path $gitRoot '.github\workflows'
    hosted_run_url = $null
    ruleset_id = $null
    failing_pr_evidence = $null
    passing_pr_evidence = $null
}
[IO.File]::WriteAllText((Join-Path $OutputDirectory 'ACTIVATION_STATUS.json'), ($record | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
Write-Output "Prepared local activation package: $OutputDirectory"
if (-not $origin) { Write-Warning 'No origin configured. Target repository ownership and checkout remain unverified.' }
Write-Output 'No hosted action was executed. Review REVIEW_COMMANDS.txt and record hosted evidence before claiming enforcement.'
