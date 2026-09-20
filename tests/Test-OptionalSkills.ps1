#requires -Version 5.1
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
. (Join-Path $root 'scripts/Initialize-OptionalSkills.ps1')
$realGit = Find-OptionalGit
$getRealArchive = ${function:Get-OptionalArchive}
$runRealGit = ${function:Invoke-OptionalGit}
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$testRoot = Join-Path $root ('.work/optional-skills-test-' + [Guid]::NewGuid().ToString('N'))
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
function Write-Text([string]$Path, [string]$Body) {
    $null = [IO.Directory]::CreateDirectory((Split-Path $Path -Parent))
    [IO.File]::WriteAllText($Path, $Body, [Text.UTF8Encoding]::new($false))
}
function New-TestArchive([string]$Name, $Contents) {
    $path = Join-Path $testRoot ($Name + '.zip')
    $zip = [IO.Compression.ZipFile]::Open($path, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($entryName in $Contents.Keys) {
            $stream = $zip.CreateEntry($entryName).Open()
            try {
                $bytes = [Text.Encoding]::UTF8.GetBytes($Contents[$entryName])
                $stream.Write($bytes, 0, $bytes.Length)
            } finally { $stream.Dispose() }
        }
    } finally { $zip.Dispose() }
    return $path
}
function Text-Hash([string]$Value) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-', '').ToLowerInvariant() }
    finally { $hash.Dispose() }
}

# 取得境界だけを差し替え、第三者の本文やGeminiを使わず実際の配置・照合を検証する。
$script:fetches = 0
$script:gitChecks = 0
$script:gitAvailable = $true
function Find-OptionalGit {
    $script:gitChecks++
    if ($script:gitAvailable) { return 'dummy-git' }
    return $null
}
function Get-OptionalArchive($Source, [string]$Work, [string]$Git) {
    $script:fetches++
    return $script:archive
}
$contents = [ordered]@{
    'SKILL.md' = "---`nname: test-only`ndescription: 導入処理の検証用。実行しない。`n---`n# 検証用の独自文章`n"
    'LICENSE' = '検証用の許諾記録'
    'NOTICE' = '検証用の権利表示'
}
$script:archive = New-TestArchive 'valid' $contents
$validArchive = $script:archive
$fileHashes = [ordered]@{}
foreach ($name in $contents.Keys) { $fileHashes[$name] = Text-Hash $contents[$name] }
$registry = [ordered]@{
    schemaVersion = 1
    providers = [ordered]@{
        'humanizer-jp' = [ordered]@{ method = 'git'; revision = ('a' * 40); requiresGeminiConsent = $false; prefix = ''; files = $fileHashes }
        'japanese-natural-writing' = [ordered]@{ method = 'zip'; revision = ('b' * 64); requiresGeminiConsent = $true; prefix = ''; files = $fileHashes }
    }
}
function New-TestProject([string]$Name, [string]$Selection = '使用しない') {
    $path = Join-Path $testRoot $Name
    Write-Text (Join-Path $path 'project.json') '{"name":"検証用"}'
    Write-Text (Join-Path $path 'OPTION.md') "| 日本語推敲スキル | $Selection | 検証 |`n"
    Write-OptionalJson $registry (Join-Path $path 'config/optional-skills.json')
    return $path
}

$off = New-TestProject 'default'
$state = Initialize-OptionalSkills $off
Check ($state.status -eq 'disabled' -and $script:fetches -eq 0 -and $script:gitChecks -eq 0) '既定ではGit確認・取得を行わない'
Check (-not (Test-Path -LiteralPath (Join-Path $off '.work')) -and -not (Test-Path -LiteralPath (Join-Path $off '.agents'))) '無効時には作業記録・導入先を作らない'
$missing = Join-Path $testRoot 'missing-option'
Write-Text (Join-Path $missing 'project.json') '{}'
Check ((Initialize-OptionalSkills $missing).status -eq 'disabled') 'OPTIONや取得設定がない作品も既定は無効'
Write-Text (Join-Path $missing 'OPTION.md') ''
Check ((Initialize-OptionalSkills $missing).status -eq 'disabled') '空のOPTIONも既定は無効'
foreach ($selection in @('', '無効', '使用しない', 'none')) {
    Write-Text (Join-Path $off 'OPTION.md') "| 日本語推敲スキル | $selection | 検証 |"
    Check ((Get-OptionalSelection $off) -eq 'none') "無効な選択を解決する: $selection"
}
Write-Text (Join-Path $off 'OPTION.md') '| 別の項目 | humanizer-jp | 日本語推敲スキルは例示のみ |'
Check ((Get-OptionalSelection $off) -eq 'none') '説明や別の項目を有効化指定とみなさない'
Write-Text (Join-Path $off 'OPTION.md') '| 日本語推敲スキル | 使用する | 検証 |'
Check ((Get-OptionalSelection $off) -eq 'humanizer-jp') '有効化だけの指定はGeminiを使わない版を選ぶ'
Write-Text (Join-Path $off 'OPTION.md') '| 日本語推敲スキル | japanese-natural-writing（Gemini） | 検証 |'
Check ((Get-OptionalSelection $off) -eq 'japanese-natural-writing') 'Gemini版の選択を解決する'
Write-Text (Join-Path $off 'OPTION.md') '| 日本語推敲スキル | unknown | 検証 |'
Must-Fail { Get-OptionalSelection $off } '不明なスキルを黙って導入しない'
Write-Text (Join-Path $off 'OPTION.md') "| 日本語推敲スキル | 使用しない |`n| 日本語推敲スキル | humanizer-jp |"
Must-Fail { Get-OptionalSelection $off } '重複する設定を拒否する'
Must-Fail { Initialize-OptionalSkills $testRoot -Provider humanizer-jp } '作品ではないフォルダへ導入しない'

$standard = New-TestProject 'standard' 'humanizer-jp'
$script:gitAvailable = $false
Check ((Initialize-OptionalSkills $standard).status -eq 'needs_git_consent' -and $script:fetches -eq 0) 'Gitがなければ許可確認を要求し取得しない'
Check (-not (Test-Path -LiteralPath (Join-Path $standard '.agents'))) 'Gitの回答前に導入先を作らない'
$script:gitAvailable = $true
$state = Initialize-OptionalSkills $standard
Check ($state.status -eq 'installed' -and $script:fetches -eq 1) '有効な通常版を初回に自動導入する'
$installed = Join-Path $standard '.agents/skills/humanizer-jp'
foreach ($name in $contents.Keys) {
    Check ((Get-FileHash -LiteralPath (Join-Path $installed $name)).Hash.ToLowerInvariant() -ceq $fileHashes[$name]) "本文と権利表示を改変しない: $name"
}
Check ((Get-Content -LiteralPath (Join-Path $installed 'agents/openai.yaml') -Raw -Encoding UTF8) -match 'allow_implicit_invocation: false') '導入済みでも暗黙に呼び出さない'
$priorGitChecks = $script:gitChecks
$script:gitAvailable = $false
Check ((Initialize-OptionalSkills $standard).status -eq 'ready' -and $script:fetches -eq 1 -and $script:gitChecks -eq $priorGitChecks) '再開時はGitがなくても再取得せず導入済みを確認する'
$receiptPath = Join-Path $standard '.work/optional-skills/humanizer-jp-installed.json'
$receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
Check ($receipt.path -ceq '.agents/skills/humanizer-jp' -and -not (Get-Content -LiteralPath $receiptPath -Raw).Contains($testRoot)) '導入記録に実機の絶対パスを残さない'
Write-Text (Join-Path $standard 'OPTION.md') '| 日本語推敲スキル | 使用しない |'
Check ((Initialize-OptionalSkills $standard).status -eq 'disabled' -and (Test-Path -LiteralPath $installed) -and $script:fetches -eq 1) '無効化後は導入済みを保持して無効を返す'
Check ((Initialize-OptionalSkills $standard -Provider humanizer-jp).status -eq 'ready') '会話で採用した実効設定を指定できる'
Write-Text (Join-Path $installed 'SKILL.md') '利用者による変更'
Must-Fail { Initialize-OptionalSkills $standard -Provider humanizer-jp } '改変済みのスキルを上書きしない'
Check ((Get-Content -LiteralPath (Join-Path $installed 'SKILL.md') -Raw -Encoding UTF8) -ceq '利用者による変更') '改変されたファイルを保つ'
$existing = New-TestProject 'existing' 'humanizer-jp'
Write-Text (Join-Path $existing '.agents/skills/humanizer-jp/SKILL.md') '別の既存スキル'
Must-Fail { Initialize-OptionalSkills $existing } '記録のない同名スキルを上書きしない'

$gemini = New-TestProject 'gemini' 'japanese-natural-writing'
$script:gitAvailable = $true
$beforeFetch = $script:fetches
$beforeGit = $script:gitChecks
Check ((Initialize-OptionalSkills $gemini).status -eq 'needs_gemini_consent') 'Gemini版の有効化は利用枠の承諾にならない'
Check ($script:fetches -eq $beforeFetch -and $script:gitChecks -eq $beforeGit -and -not (Test-Path -LiteralPath (Join-Path $gemini '.agents'))) 'Geminiの回答前には取得・導入・環境確認を行わない'
Must-Fail { Initialize-OptionalSkills $gemini -GeminiConsent Granted } '回答と対象範囲の記録なしで承諾を作らない'
Check ((Initialize-OptionalSkills $gemini -GeminiConsent Denied -ConsentNote '検証用の拒否回答').status -eq 'gemini_declined') '拒否回答を保存する'
Check ((Initialize-OptionalSkills $gemini).status -eq 'gemini_declined' -and $script:fetches -eq $beforeFetch) '再開しても拒否後に取得や許可確認を繰り返さない'
# 以下のGrantedは独自のダミー文章の配置テスト専用。外部スキル・Geminiへは接続しない。
Check ((Initialize-OptionalSkills $gemini -GeminiConsent Granted -ConsentNote 'ダミー配置テストへの模擬回答。実サービスの利用許可ではない').status -eq 'installed') '模擬承諾後に初めてダミー版を配置する'
Check ($script:fetches -eq ($beforeFetch + 1) -and $script:gitChecks -eq $beforeGit) 'ZIP方式ではGitを要求しない'
Check ((Initialize-OptionalSkills $gemini).status -eq 'ready' -and $script:fetches -eq ($beforeFetch + 1)) '同じ作品・固定版の回答を再利用する'
Check ((Initialize-OptionalSkills $gemini -GeminiConsent Denied -ConsentNote '検証用の撤回回答').status -eq 'gemini_declined') '導入済みでも許可撤回を反映する'
$configPath = Join-Path $gemini 'config/optional-skills.json'
$changed = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$changed.providers.'japanese-natural-writing'.revision = 'c' * 64
Write-OptionalJson $changed $configPath
Check ((Initialize-OptionalSkills $gemini).status -eq 'needs_gemini_consent') '版変更後は以前の回答を流用しない'
$otherGemini = New-TestProject 'other-gemini' 'japanese-natural-writing'
Check ((Initialize-OptionalSkills $otherGemini).status -eq 'needs_gemini_consent') '別作品には利用許可を流用しない'
$changed.providers.'japanese-natural-writing'.requiresGeminiConsent = $false
Write-OptionalJson $changed (Join-Path $otherGemini 'config/optional-skills.json')
Check ((Initialize-OptionalSkills $otherGemini).status -eq 'needs_gemini_consent') 'Gemini版では設定の誤変更によって許可確認を省略しない'

$badContents = [ordered]@{}
foreach ($name in $contents.Keys) { $badContents[$name] = $contents[$name] }
$badContents['SKILL.md'] = '変更された取得物'
$script:archive = New-TestArchive 'bad-hash' $badContents
$bad = New-TestProject 'bad-hash' 'humanizer-jp'
Must-Fail { Initialize-OptionalSkills $bad } '取得物のハッシュ不一致を拒否する'
Check (-not (Test-Path -LiteralPath (Join-Path $bad '.agents/skills/humanizer-jp'))) '取得失敗を導入済みにしない'
$script:archive = New-TestArchive 'missing-file' ([ordered]@{'SKILL.md' = $contents['SKILL.md']})
$bad = New-TestProject 'missing-file' 'humanizer-jp'
Must-Fail { Initialize-OptionalSkills $bad } '許諾文等の必要ファイルが欠けた取得物を拒否する'
$badContents['SKILL.md'] = $contents['SKILL.md']
$badContents['../outside.txt'] = '導入対象外'
$script:archive = New-TestArchive 'unexpected-file' $badContents
$bad = New-TestProject 'unexpected-file' 'humanizer-jp'
Must-Fail { Initialize-OptionalSkills $bad } '想定外のファイルと作品外へ向かうZIPエントリーを拒否する'
Check (-not (Test-Path -LiteralPath (Join-Path $bad '.agents/skills/humanizer-jp'))) '不正なZIPを有効なスキルとして配置しない'
Must-Fail { Assert-OptionalPath $bad '../escape' } '直接指定した作品外のパスも拒否する'

# 配布元にインターフェース定義がある場合も保持してポリシーだけ追加する。
$withPolicy = [ordered]@{'SKILL.md' = $contents['SKILL.md']; 'agents/openai.yaml' = "interface:`n  display_name: test-only`n"}
$policyHashes = [ordered]@{}
foreach ($name in $withPolicy.Keys) { $policyHashes[$name] = Text-Hash $withPolicy[$name] }
$policyProject = New-TestProject 'interface' 'humanizer-jp'
$policyConfig = Get-Content -LiteralPath (Join-Path $policyProject 'config/optional-skills.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$policyConfig.providers.'humanizer-jp'.files = [pscustomobject]$policyHashes
Write-OptionalJson $policyConfig (Join-Path $policyProject 'config/optional-skills.json')
$script:archive = New-TestArchive 'interface' $withPolicy
$null = Initialize-OptionalSkills $policyProject
$policyText = Get-Content -LiteralPath (Join-Path $policyProject '.agents/skills/humanizer-jp/agents/openai.yaml') -Raw -Encoding UTF8
Check ($policyText.Contains('display_name: test-only') -and $policyText.Contains('allow_implicit_invocation: false')) '既存のインターフェースを保って暗黙の実行を無効化する'
Check ((Initialize-OptionalSkills $policyProject).status -eq 'ready') 'ポリシー追記後のハッシュで再開時に照合する'

# ZIP取得も通信境界だけを差し替え、全体ハッシュと配布物のサブフォルダを検証する。
$prefixedContents = [ordered]@{}
foreach ($name in $contents.Keys) { $prefixedContents['japanese-natural-writing/' + $name] = $contents[$name] }
$zipFixture = New-TestArchive 'prefixed' $prefixedContents
$zipSource = [pscustomobject]@{ method = 'zip'; url = 'https://note.com/api/v2/attachments/download/123abc'; revision = (Get-FileHash -LiteralPath $zipFixture).Hash.ToLowerInvariant(); prefix = 'japanese-natural-writing/'; files = [pscustomobject]$fileHashes }
function Invoke-WebRequest([switch]$UseBasicParsing, [string]$Uri, [string]$OutFile, [int]$TimeoutSec) {
    Copy-Item -LiteralPath $zipFixture -Destination $OutFile
}
$zipWork = Join-Path $testRoot 'zip-download'
$null = [IO.Directory]::CreateDirectory($zipWork)
$zipDownloaded = & $getRealArchive $zipSource $zipWork ''
Check ((Get-FileHash -LiteralPath $zipDownloaded).Hash.ToLowerInvariant() -ceq $zipSource.revision) 'ZIP全体の固定ハッシュを取得時に照合する'
$zipStage = Join-Path $zipWork 'expanded'
$null = [IO.Directory]::CreateDirectory($zipStage)
Expand-OptionalArchive $zipDownloaded $zipSource $zipStage
Check ((Get-FileHash -LiteralPath (Join-Path $zipStage 'SKILL.md')).Hash.ToLowerInvariant() -ceq $fileHashes['SKILL.md']) 'ZIPの配布フォルダを除いてスキル本体を配置する'
$zipSource.revision = '0' * 64
Must-Fail { & $getRealArchive $zipSource $zipWork '' } 'ZIPが差し替わっていたら採用しない'

# 通信なしで実際のGit取得経路を検証。fetchの相手だけローカルの検証用リポジトリへ置き換える。
if (-not $realGit) { throw 'Git取得経路の検証にはインストール済みのGitが必要です。' }
$localRepo = Join-Path $testRoot 'local-repository'
$emptyHooks = Join-Path $testRoot 'empty-hooks'
$null = [IO.Directory]::CreateDirectory($emptyHooks)
$null = & $runRealGit $realGit @('-c', "core.hooksPath=$emptyHooks", 'init', '--quiet', $localRepo)
Write-Text (Join-Path $localRepo 'SKILL.md') $contents['SKILL.md']
$null = & $runRealGit $realGit @('-C', $localRepo, '-c', 'core.autocrlf=false', 'add', 'SKILL.md')
$null = & $runRealGit $realGit @('-C', $localRepo, '-c', "core.hooksPath=$emptyHooks", '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--quiet', '-m', 'Test fixture')
$localRevision = & $runRealGit $realGit @('-C', $localRepo, 'rev-parse', 'HEAD')
$localSource = [pscustomobject]@{ method = 'git'; repository = 'https://github.com/test/fixture.git'; revision = $localRevision.Trim(); prefix = ''; files = [pscustomobject]@{'SKILL.md' = $fileHashes['SKILL.md']} }
function Invoke-OptionalGit([string]$Git, [string[]]$Arguments) {
    if ($Arguments -contains 'fetch') {
        $Arguments = @($Arguments | ForEach-Object { if ($_ -eq 'https://github.com/test/fixture.git') { $localRepo } else { $_ } })
    }
    return (& $runRealGit $Git $Arguments)
}
$gitWork = Join-Path $testRoot 'git-archive'
$null = [IO.Directory]::CreateDirectory($gitWork)
$savedEnvironment = @{}
foreach ($key in @('GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0', 'GIT_CONFIG_VALUE_0')) { $savedEnvironment[$key] = [Environment]::GetEnvironmentVariable($key, 'Process') }
try {
    $env:GIT_CONFIG_COUNT = '1'
    $env:GIT_CONFIG_KEY_0 = 'core.autocrlf'
    $env:GIT_CONFIG_VALUE_0 = 'true'
    $gitArchive = & $getRealArchive $localSource $gitWork $realGit
    $gitStage = Join-Path $gitWork 'expanded'
    $null = [IO.Directory]::CreateDirectory($gitStage)
    Expand-OptionalArchive $gitArchive $localSource $gitStage
    Check ((Get-FileHash -LiteralPath (Join-Path $gitStage 'SKILL.md')).Hash.ToLowerInvariant() -ceq $fileHashes['SKILL.md']) 'Gitの自動CRLF設定にかかわらず固定版の原文・ハッシュを保持する'
} finally {
    foreach ($key in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($key, $savedEnvironment[$key], 'Process') }
}

$report = [ordered]@{ passed = $checks.Count; checks = @($checks); network = $false; externalSkills = $false; geminiCalls = 0; testedAt = [DateTimeOffset]::Now.ToString('o'); powershell = $PSVersionTable.PSVersion.ToString() }
Write-OptionalJson $report (Join-Path $testRoot 'result.json')
$report | ConvertTo-Json -Depth 10
