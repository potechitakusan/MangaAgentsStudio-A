#requires -Version 5.1
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateLength(1, 64)]
    [ValidatePattern('^[\p{L}\p{N}][\p{L}\p{N} _-]*$')]
    [string]$ProjectName,
    [string]$DestinationParent
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$sourceRootPath = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))

function Get-RelativePath([string]$Base, [string]$Path) {
    $baseUri = [Uri]([IO.Path]::GetFullPath($Base).TrimEnd('\') + '\')
    $pathUri = [Uri][IO.Path]::GetFullPath($Path)
    $relative = $baseUri.MakeRelativeUri($pathUri)
    if ($relative.IsAbsoluteUri) { throw '作業パスを相対パスで表せません。' }
    return [Uri]::UnescapeDataString($relative.ToString())
}
if ($ProjectName -ne $ProjectName.Trim() -or $ProjectName -match '^(CON|PRN|AUX|NUL|COM[0-9\u00b9\u00b2\u00b3]|LPT[0-9\u00b9\u00b2\u00b3])$') {
    throw 'ProjectName is a Windows reserved name or has trailing whitespace.'
}
if (-not $DestinationParent) { $DestinationParent = Split-Path $sourceRootPath -Parent }
$parent = Get-Item -LiteralPath $DestinationParent -Force
if (-not $parent.PSIsContainer) { throw 'DestinationParent must be an existing directory.' }
$parentPath = [IO.Path]::GetFullPath($parent.FullName)
$target = [IO.Path]::GetFullPath((Join-Path $parentPath $ProjectName))
if ((Split-Path $target -Parent).TrimEnd('\') -ne $parentPath.TrimEnd('\')) { throw 'Target must be a direct child of DestinationParent.' }
if (Test-Path -LiteralPath $target) { throw "Target already exists; no files were changed: $target" }

function Assert-NoLinks([string]$Path) {
    $current = Get-Item -LiteralPath $Path -Force
    while ($null -ne $current) {
        if (($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked paths are not supported for packaging: $($current.FullName)" }
        if ($current -is [IO.FileInfo]) { $current = $current.Directory } else { $current = $current.Parent }
    }
}
function Get-PackageFiles([string]$Root, [string[]]$SkipDirectories = @()) {
    # Inspect each directory before descending, so a junction is never followed.
    foreach ($item in (Get-ChildItem -LiteralPath $Root -Force)) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Linked package content: $($item.FullName)" }
        if ($item.PSIsContainer) {
            if ($item.Name -ne '__pycache__' -and $item.Name -notin $SkipDirectories) { Get-PackageFiles $item.FullName }
        } else { $item }
    }
}
Assert-NoLinks $parentPath
Assert-NoLinks $sourceRootPath
$mappings = @(
    @{ Source = 'templates\manga-project'; Target = ''; Extensions = @('.md', '.json', '.py'); Special = @('.gitignore', '.env.example', 'requirements-composition.txt') },
    @{ Source = 'docs\knowledge'; Target = 'docs\knowledge'; Extensions = @('.md'); Special = @() },
    @{ Source = 'skills'; Target = '.agents\skills'; Extensions = @('.md'); Special = @() },
    @{ Source = 'scripts\video'; Target = 'scripts\video'; Extensions = @('.py'); Special = @() }
)
$package = [Collections.Generic.List[object]]::new()
foreach ($mapping in $mappings) {
    $sourceRoot = Join-Path $sourceRootPath $mapping.Source
    if (-not (Test-Path -LiteralPath $sourceRoot -PathType Container)) { throw "Missing source directory: $sourceRoot" }
    Assert-NoLinks $sourceRoot
    # supervisionは後で明示リストから配布するため、一括コピーから除外する。
    $skipDirectories = if ($mapping.Source -eq 'docs\knowledge') { @('supervision') } else { @() }
    $files = @(Get-PackageFiles $sourceRoot -SkipDirectories $skipDirectories)
    if ($files.Count -eq 0) { throw "Empty package directory: $sourceRoot" }
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($sourceRoot.Length).TrimStart('\')
        if ($relative -match '(^|[\\/])(\.secrets|\.git)([\\/]|$)' -or
            ($file.Name -like '.env*' -and $file.Name -ne '.env.example') -or
            $file.Name -match '(?i)(secret|credential|api[-_]?key|token)') { throw "Secret-like package filename: $relative" }
        $panelAsset = $mapping.Source -eq 'templates\manga-project' -and (
            $relative -eq 'templates\panel-templates\index.html' -or
            $relative -match '^templates\\panel-templates\\(svg|guides)\\[^\\]+\.svg$' -or
            $relative -match '^templates\\panel-templates\\(png|previews)\\[^\\]+\.png$')
        $onomatopoeiaAsset = $mapping.Source -eq 'templates\manga-project' -and
            ($relative -eq 'templates\onomatopoeia\index.html' -or
             $relative -match '^templates\\onomatopoeia\\images\\[^\\]+\.webp$')
        if ($file.Extension -notin $mapping.Extensions -and $file.Name -notin $mapping.Special -and
            -not $panelAsset -and -not $onomatopoeiaAsset) { throw "Unexpected package file type: $relative" }
        $destination = if ($mapping.Target) { Join-Path $mapping.Target $relative } else { $relative }
        $package.Add([pscustomobject]@{ Source = $file.FullName; Destination = $destination })
    }
}
# 監修知識を明示リストから配布する。
$knowledgeManifestRelative = 'docs/knowledge/supervision/distribution.json'
$knowledgeManifestPath = Join-Path $sourceRootPath $knowledgeManifestRelative
Assert-NoLinks $knowledgeManifestPath
$knowledgeManifest = Get-Content -LiteralPath $knowledgeManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($knowledgeManifest.schemaVersion -isnot [int] -or $knowledgeManifest.schemaVersion -ne 1 -or
    $knowledgeManifest.files -isnot [array] -or $knowledgeManifest.files.Count -eq 0) {
    throw '知識の配布マニフェストが不正です。'
}
$knowledgePattern = '\A(?:docs/knowledge/supervision/(?:README|routing|sources)\.md|docs/knowledge/supervision/gag/(?:README|mechanisms|design-and-review|know-how)\.md|docs/knowledge/supervision/(?:tsukkomi|allure|stature|horror|conflict|grief|romance|trust|awkwardness|urgency|revelation|payoff|endearment|bargaining|reconciliation)/README\.md)\z'
$knowledgeSeen = @{}
foreach ($relative in $knowledgeManifest.files) {
    if ($relative -isnot [string] -or $relative -cnotmatch $knowledgePattern) { throw "知識の配布に許可されていないパスです: $relative" }
    if ($knowledgeSeen.ContainsKey($relative)) { throw "知識の配布パスが重複しています: $relative" }
    $knowledgeSeen[$relative] = $true
    $source = Join-Path $sourceRootPath $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "配布する知識がありません: $relative" }
    Assert-NoLinks $source
    $package.Add([pscustomobject]@{ Source = $source; Destination = $relative.Replace('/', '\') })
}
$package.Add([pscustomobject]@{ Source = $knowledgeManifestPath; Destination = $knowledgeManifestRelative.Replace('/', '\') })
$resolver = Join-Path $PSScriptRoot 'Resolve-ReviewProfile.ps1'
$null = & $resolver -ConfigPath (Join-Path $sourceRootPath 'templates\manga-project\config\review-profiles.json')
$package.Add([pscustomobject]@{ Source = $resolver; Destination = 'scripts\Resolve-ReviewProfile.ps1' })
$validator = Join-Path $PSScriptRoot 'validate_panel_plan.py'
$package.Add([pscustomobject]@{ Source = $validator; Destination = 'scripts\validate_panel_plan.py' })
$package.Add([pscustomobject]@{ Source = (Join-Path $PSScriptRoot 'prepare_page_layout.py'); Destination = 'scripts\prepare_page_layout.py' })
$package.Add([pscustomobject]@{ Source = (Join-Path $PSScriptRoot 'Initialize-OptionalSkills.ps1'); Destination = 'scripts\Initialize-OptionalSkills.ps1' })
$package.Add([pscustomobject]@{ Source = (Join-Path $sourceRootPath 'LICENSE'); Destination = 'docs\toolkit-license.txt' })
if (@($package | Group-Object Destination | Where-Object Count -gt 1).Count -gt 0) { throw 'Duplicate destination in package.' }
$version = (Get-Content -LiteralPath (Join-Path $sourceRootPath 'distribution-version.txt') -Raw -Encoding UTF8).Trim()
$snapshot = @($package | Sort-Object Destination | ForEach-Object {
    [ordered]@{ path = $_.Destination.Replace('\', '/'); sha256 = (Get-FileHash -LiteralPath $_.Source -Algorithm SHA256).Hash.ToLowerInvariant() }
})
$displayTarget = Get-RelativePath (Get-Location).ProviderPath $target
if (-not $PSCmdlet.ShouldProcess($displayTarget, "配布版 $version から漫画プロジェクトを作成（$($package.Count) ファイル）")) { return }

$created = $false
try {
    $null = New-Item -ItemType Directory -Path $target
    $created = $true
    foreach ($entry in $package) {
        $destination = Join-Path $target $entry.Destination
        $null = [IO.Directory]::CreateDirectory((Split-Path $destination -Parent))
        Copy-Item -LiteralPath $entry.Source -Destination $destination -ErrorAction Stop
    }
    foreach ($directory in @('input', 'assets\characters', 'assets\references', 'workflows', 'output', '.secrets')) {
        $null = [IO.Directory]::CreateDirectory((Join-Path $target $directory))
    }
    $createdAt = [DateTimeOffset]::Now.ToString('o')
    $utf8 = [Text.UTF8Encoding]::new($false)
    $project = [ordered]@{ schemaVersion = 1; name = $ProjectName; createdAt = $createdAt; distributionVersion = $version }
    [IO.File]::WriteAllText((Join-Path $target 'project.json'), ($project | ConvertTo-Json -Depth 10), $utf8)
    $manifest = [ordered]@{ version = $version; createdAt = $createdAt; files = $snapshot }
    [IO.File]::WriteAllText((Join-Path $target 'docs\distribution-snapshot.json'), ($manifest | ConvertTo-Json -Depth 10), $utf8)
    Write-Host "漫画プロジェクトを作成しました。作成先の絶対パス: $target"
    Write-Host 'このフォルダでCodexを開き直してください。作品フォルダで新しい会話を始めてから漫画を制作します。'
    Write-Host 'やり方がわからない場合は、ご利用の環境（Windows／Mac、アプリ／VS Code）を教えてください。必要な手順をご案内します。'
    [pscustomobject]@{ ProjectName = $ProjectName; Path = $displayTarget; AbsolutePath = $target; Version = $version; CopiedFiles = $package.Count }
} catch {
    if ($created) { Write-Warning "作成が失敗しました。確認用の途中出力を保持しています: $displayTarget" }
    throw
}
