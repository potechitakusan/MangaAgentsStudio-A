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
# 配布検証用の空プロジェクトだけを .work/ に作り、ここでは漫画を制作しない。
$result = & $maker -ProjectName $japaneseName -DestinationParent $testRoot -InformationVariable creationMessages
$projectRoot = (Resolve-Path -LiteralPath $result.Path).ProviderPath
Check (@($result).Count -eq 1) '開き直し案内がスクリプトの戻り値に混入しない'
Check (([IO.Path]::IsPathRooted($result.AbsolutePath)) -and ($result.AbsolutePath -eq $projectRoot) -and
       (-not [IO.Path]::IsPathRooted($result.Path))) '表示用の絶対パスが実在する作品と一致し、従来の相対パスも保持する'
$creationText = ($creationMessages | Out-String -Width 4096)
Check ($creationText.Contains($projectRoot) -and $creationText.Contains('このフォルダでCodexを開き直してください')) '作成先を省略せず開き直しを案内する'
$project = Get-Content -LiteralPath (Join-Path $projectRoot 'project.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Check ($project.name -ceq $japaneseName) 'Japanese project name survives JSON round trip'
Check ((Split-Path $projectRoot -Parent) -eq $testRoot) 'Project is a direct child of the selected parent'
Check (@(Get-ChildItem -LiteralPath (Join-Path $projectRoot '.agents\skills') -Directory).Count -eq 8) '監修を含む8つのスキルが同梱される'
Check ((Test-Path -LiteralPath (Join-Path $projectRoot '.agents\skills\manga-supervision\SKILL.md')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\reviews\SUPERVISION.md'))) '監修スキルと場面単位の相談・レビュー記入欄を使える'
$knowledgeManifest = Get-Content -LiteralPath (Join-Path $root 'docs\knowledge\supervision\distribution.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Check ((Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\manga\03-beat-pacing-timing.md')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\supervision\distribution.json'))) '制作知識はdocs/knowledge配下に配布される'
Check (@($knowledgeManifest.files | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf)
}).Count -eq 0) '同梱のギャグ監修文書が作品だけで参照できる'
Check ((Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs/knowledge/supervision') -Recurse -File).Count -eq ($knowledgeManifest.files.Count + 1)) '配布される監修ファイルはマニフェスト掲載分と一致する'
Check ((@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'docs/knowledge/supervision') -Directory).Name -join ',') -eq 'gag') '配布する専用監修はギャグのみ'
Check ((Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\story-structure.md')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\japanese-manga-readability.md'))) 'Knowledge is included'
Check ((Test-Path -LiteralPath (Join-Path $projectRoot 'templates\panel-templates\catalog.json')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'config\panel-layout-policy.json')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'scripts\validate_panel_plan.py')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\panel-layout-policy.md')) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'templates\panel-templates\index.html'))) 'コマ割り一覧・設定・検証スクリプトが同梱される'
$panelCatalog = Get-Content -Encoding UTF8 -Raw -LiteralPath (Join-Path $projectRoot 'templates\panel-templates\catalog.json') | ConvertFrom-Json
$missingPanelAssets = @($panelCatalog.templates | ForEach-Object {
    $_.assets.PSObject.Properties | ForEach-Object {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ('templates\panel-templates\' + $_.Value)) -PathType Leaf)) { $_.Value }
    }
})
Check ($panelCatalog.templateCount -eq 79 -and $missingPanelAssets.Count -eq 0) '全79種類のSVG・PNG・個別JSONが配布先で実在する'
Check ((Get-FileHash -LiteralPath (Join-Path $projectRoot 'docs\toolkit-license.txt')).Hash -eq
       (Get-FileHash -LiteralPath (Join-Path $root 'LICENSE')).Hash) '同梱キットのライセンスが原本と一致する'
Check ((Test-Path -LiteralPath (Join-Path $projectRoot 'OPTION.md') -PathType Leaf) -and
       (Test-Path -LiteralPath (Join-Path $projectRoot 'docs\knowledge\project-options.md') -PathType Leaf)) '制作オプションと欠落時にも参照できる適用手順が同梱される'
Check ($project.distributionVersion -eq (Get-Content -LiteralPath (Join-Path $root 'distribution-version.txt') -Raw).Trim()) '作品の配布版が原本の版と一致する'
Check (@(Get-ChildItem -LiteralPath (Join-Path $projectRoot '.secrets') -Force).Count -eq 0) 'Secret directory starts empty'
$snapshot = Get-Content -LiteralPath (Join-Path $projectRoot 'docs\distribution-snapshot.json') -Raw -Encoding UTF8 | ConvertFrom-Json
Check (@($project.PSObject.Properties.Name | Where-Object { $_ -match 'Path' }).Count -eq 0 -and
       @($snapshot.files | Where-Object { [IO.Path]::IsPathRooted($_.path) }).Count -eq 0) '作成結果の絶対パスを作品設定や配布記録に保存しない'
$hashesValid = $true
foreach ($entry in $snapshot.files) {
    if ((Get-FileHash -LiteralPath (Join-Path $projectRoot $entry.path)).Hash -ne $entry.sha256) { $hashesValid = $false }
}
Check $hashesValid 'Every distributed file matches its recorded SHA-256'
$originalHash = (Get-FileHash -LiteralPath (Join-Path $projectRoot 'project.json')).Hash
Must-Fail { & $maker -ProjectName $japaneseName -DestinationParent $testRoot } 'Existing project is rejected'
Check ((Get-FileHash -LiteralPath (Join-Path $projectRoot 'project.json')).Hash -eq $originalHash) 'Existing project remains unchanged'
$previewResult = & $maker -ProjectName 'PreviewOnly' -DestinationParent $testRoot -WhatIf -InformationVariable previewMessages
Check (-not (Test-Path -LiteralPath (Join-Path $testRoot 'PreviewOnly'))) 'WhatIf does not create files'
Check ($null -eq $previewResult -and -not (($previewMessages | Out-String).Contains('このフォルダでCodexを開き直してください'))) 'WhatIfで作成完了や開き直しを案内しない'
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
foreach ($relative in @('docs/knowledge/supervision/unlisted.md',
                         'docs/knowledge/supervision/gag/unlisted.md')) {
    $destination = Join-Path $fixture $relative
    $null = [IO.Directory]::CreateDirectory((Split-Path $destination -Parent))
    [IO.File]::WriteAllText($destination, 'マニフェスト未掲載ファイル')
}
$fixtureResult = & (Join-Path $fixture 'scripts\New-MangaProject.ps1') -ProjectName 'WithUnlistedFiles' -DestinationParent $testRoot
$fixtureProject = (Resolve-Path -LiteralPath $fixtureResult.Path).ProviderPath
Check (@(Get-ChildItem -LiteralPath (Join-Path $fixtureProject 'docs/knowledge/supervision') -Recurse -File | Where-Object {
    $_.Name -eq 'unlisted.md'
}).Count -eq 0) 'マニフェスト未掲載ファイルは作品へ配布されない'
# 未許可パスは、マニフェストに追加しても作成前に拒否する。
$fixtureManifest = Join-Path $fixture 'docs\knowledge\supervision\distribution.json'
foreach ($unlistedPath in @('docs/knowledge/supervision/unlisted.md',
                           'docs/knowledge/supervision/gag/unlisted.md')) {
    $badKnowledge = [ordered]@{ schemaVersion = 1; files = @($knowledgeManifest.files) + @($unlistedPath) }
    Write-Json $badKnowledge $fixtureManifest
    Must-Fail { & (Join-Path $fixture 'scripts\New-MangaProject.ps1') -ProjectName 'RejectedEntries' -DestinationParent $testRoot } "未許可パスのマニフェスト追加を拒否する: $unlistedPath"
}
Check (-not (Test-Path -LiteralPath (Join-Path $testRoot 'RejectedEntries'))) '不正な知識配布では作品フォルダを作らない'
Write-Json $knowledgeManifest $fixtureManifest
[IO.File]::WriteAllText((Join-Path $fixture 'templates\manga-project\.env'), '# Empty accidental private config')
Must-Fail { & (Join-Path $fixture 'scripts\New-MangaProject.ps1') -ProjectName 'RejectedSecrets' -DestinationParent $testRoot } 'Accidental private configuration in template is rejected'
Check (-not (Test-Path -LiteralPath (Join-Path $testRoot 'RejectedSecrets'))) 'Invalid package leaves no target directory'
$report = [ordered]@{ passed = $checks.Count; checks = @($checks); pathBase = '.'; output = $japaneseName; testedAt = [DateTimeOffset]::Now.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString() }
Write-Json $report (Join-Path $testRoot 'result.json')
$report | ConvertTo-Json -Depth 10
