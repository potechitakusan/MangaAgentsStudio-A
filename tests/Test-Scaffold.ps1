#requires -Version 5.1
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$maker = Join-Path $root 'scripts\New-MangaProject.ps1'
$resolver = Join-Path $root 'scripts\Resolve-ReviewProfile.ps1'
$testRoot = Join-Path $root ('.work\scaffold-' + [Guid]::NewGuid().ToString('N'))
$null = [IO.Directory]::CreateDirectory($testRoot)
$checks = [Collections.Generic.List[string]]::new()
function Check([bool]$Condition, [string]$Name) {
    if (-not $Condition) { throw "FAIL: $Name" }
    $checks.Add($Name)
}
function Must-Fail([scriptblock]$Action, [string]$Name) {
    $failed = $false
    try { $null = & $Action } catch { $failed = $true }
    Check $failed $Name
}
function Write-Json($Value, [string]$Path) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
}
$japaneseName = ([string][char]0x661f) + [char]0x6e21 + [char]0x308a + ' Test'
$result = & $maker -ProjectName $japaneseName -DestinationParent $testRoot
$projectRoot = (Resolve-Path -LiteralPath $result.Path).ProviderPath
$project = Get-Content -LiteralPath (Join-Path $projectRoot 'project.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Check ($project.name -ceq $japaneseName) 'Japanese project name survives JSON round trip'
Check ((Split-Path $projectRoot -Parent) -eq $testRoot) 'Project is a direct child of the selected parent'
Check (@(Get-ChildItem -LiteralPath (Join-Path $projectRoot '.agents\skills') -Directory).Count -eq 7) 'Seven discoverable skills are included'
Check ((Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\story-structure.md')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\japanese-manga-readability.md'))) 'Knowledge is included'
Check ((Get-FileHash -LiteralPath (Join-Path $projectRoot 'docs\toolkit-license.txt')).Hash -eq
       (Get-FileHash -LiteralPath (Join-Path $root 'LICENSE')).Hash) '同梱キットのライセンスが原本と一致する'
Check ($project.distributionVersion -eq (Get-Content -LiteralPath (Join-Path $root 'distribution-version.txt') -Raw).Trim()) '作品の配布版が原本の版と一致する'
Check (@(Get-ChildItem -LiteralPath (Join-Path $projectRoot '.secrets') -Force).Count -eq 0) 'Secret directory starts empty'
$snapshot = Get-Content -LiteralPath (Join-Path $projectRoot 'docs\distribution-snapshot.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$hashesValid = $true
foreach ($entry in $snapshot.files) {
    if ((Get-FileHash -LiteralPath (Join-Path $projectRoot $entry.path)).Hash -ne $entry.sha256) { $hashesValid = $false }
}
Check $hashesValid 'Every distributed file matches its recorded SHA-256'
$originalHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'project.json')).Hash
Must-Fail { & $maker -ProjectName $japaneseName -DestinationParent $testRoot } 'Existing project is rejected'
Check ((Get-FileHash -LiteralPath (Join-Path $projectRoot 'project.json')).Hash -eq $originalHash) 'Existing project remains unchanged'
$null = & $maker -ProjectName 'PreviewOnly' -DestinationParent $testRoot -WhatIf
Check (-not (Test-Path -LiteralPath (Join-Path $testRoot 'PreviewOnly'))) 'WhatIf does not create files'
$null = & $maker -ProjectName 'PreviewOnly' -WhatIf
Check (-not (Test-Path -LiteralPath (Join-Path (Split-Path $root -Parent) 'PreviewOnly'))) 'Default sibling destination preview is read only'
Must-Fail { & $maker -ProjectName '..\escape' -DestinationParent $testRoot } 'Path traversal is rejected'
Must-Fail { & $maker -ProjectName 'CON' -DestinationParent $testRoot } 'Windows reserved device name is rejected'
$reservedUnicode = 'COM' + [char]0x00b9
Must-Fail { & $maker -ProjectName $reservedUnicode -DestinationParent $testRoot -WhatIf } 'Unicode Windows reserved device name is rejected in PS5.1'
$null = & $maker -ProjectName 'CodexMangaPreviewOnly' -DestinationParent ([IO.Path]::GetPathRoot($root)) -WhatIf
Check $true 'Drive root is accepted as an output parent for preview'
$profilePath = Join-Path $projectRoot 'config\review-profiles.json'
$effective = & (Join-Path $projectRoot 'scripts\Resolve-ReviewProfile.ps1') -ConfigPath $profilePath -Preset 'battle'
Check ($effective.weights.cinema -eq 5 -and $effective.weights.story -eq 4) 'Distributed resolver applies preset and inherits defaults'
$config = Get-Content -LiteralPath $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json
$config.scenes | Add-Member -NotePropertyName 'scene-001' -NotePropertyValue ([pscustomobject]@{
    preset = 'confession'; weights = [pscustomobject]@{ cinema = 5; terminology = 1 }; reason = 'Test override'
})
Write-Json $config $profilePath
$effective = & $resolver -ConfigPath $profilePath -Preset 'daily' -SceneId 'scene-001'
Check ($effective.preset -eq 'confession' -and $effective.weights.story -eq 4 -and
       $effective.weights.cinema -eq 5 -and $effective.weights.terminology -eq 1) 'Scene preset overrides requested preset; scene weights apply last'
Must-Fail { & $resolver -ConfigPath $profilePath -SceneId 'missing' } 'Unknown scene is rejected'
Must-Fail { & $resolver -ConfigPath $profilePath -Preset 'missing' } 'Unknown preset is rejected'
$badPath = Join-Path $testRoot 'bad-profile.json'
foreach ($invalid in @(0, 6, 2.5, '5', $true)) {
    $config.defaults.immersion = $invalid
    Write-Json $config $badPath
    Must-Fail { & $resolver -ConfigPath $badPath } "Invalid weight rejected: $invalid"
}
$config.defaults.immersion = 5
$config.defaults | Add-Member -NotePropertyName 'misspelled' -NotePropertyValue 3
Write-Json $config $badPath
Must-Fail { & $resolver -ConfigPath $badPath } 'Misspelled weight key is rejected'

# Use an isolated packaging fixture to prove accidental secret files are rejected.
$fixture = Join-Path $testRoot 'source-fixture'
$null = [IO.Directory]::CreateDirectory($fixture)
foreach ($directory in @('scripts', 'templates', 'skills')) {
    Copy-Item -LiteralPath (Join-Path $root $directory) -Destination (Join-Path $fixture $directory) -Recurse
}
$null = [IO.Directory]::CreateDirectory((Join-Path $fixture 'docs'))
Copy-Item -LiteralPath (Join-Path $root 'docs\knowledge') -Destination (Join-Path $fixture 'docs\knowledge') -Recurse
Copy-Item -LiteralPath (Join-Path $root 'distribution-version.txt') -Destination (Join-Path $fixture 'distribution-version.txt')
Copy-Item -LiteralPath (Join-Path $root 'LICENSE') -Destination (Join-Path $fixture 'LICENSE')
[IO.File]::WriteAllText((Join-Path $fixture 'templates\manga-project\.env'), '# Empty accidental private config')
Must-Fail { & (Join-Path $fixture 'scripts\New-MangaProject.ps1') -ProjectName 'RejectedSecrets' -DestinationParent $testRoot } 'Accidental private configuration in template is rejected'
Check (-not (Test-Path -LiteralPath (Join-Path $testRoot 'RejectedSecrets'))) 'Invalid package leaves no target directory'
$report = [ordered]@{ passed = $checks.Count; checks = @($checks); pathBase = '.'; output = $japaneseName; testedAt = [DateTimeOffset]::Now.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString() }
Write-Json $report (Join-Path $testRoot 'result.json')
$report | ConvertTo-Json -Depth 10
