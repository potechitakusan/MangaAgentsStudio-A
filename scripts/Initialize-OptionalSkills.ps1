#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ProjectRoot = '',
    [ValidateSet('', 'none', 'humanizer-jp', 'japanese-natural-writing')][string]$Provider = '',
    [ValidateSet('Unspecified', 'Granted', 'Denied')][string]$GeminiConsent = 'Unspecified',
    [string]$ConsentNote = ''
)

function Assert-OptionalPath([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative) -or $Relative -match '(^|[\\/])\.\.([\\/]|$)') { throw '作品外のパスは使用できません。' }
    $path = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    $rootPrefix = $Root.TrimEnd([IO.Path]::DirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    if (-not $path.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw '作品内のパスを指定してください。' }
    $current = $path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'リンクを経由する導入先は使用できません。' }
        }
        $current = Split-Path $current -Parent
    }
    return $path
}

function Write-OptionalJson($Value, [string]$Path) {
    $null = [IO.Directory]::CreateDirectory((Split-Path $Path -Parent))
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 20), [Text.UTF8Encoding]::new($false))
}

function Get-OptionalSelection([string]$Root) {
    $path = Assert-OptionalPath $Root 'OPTION.md'
    if (-not (Test-Path -LiteralPath $path)) { return 'none' }
    $body = [string](Get-Content -LiteralPath $path -Raw -Encoding UTF8)
    $rows = [regex]::Matches($body, '(?m)^\|\s*日本語推敲スキル\s*\|\s*([^|]*)\|')
    if ($rows.Count -eq 0) { return 'none' }
    if ($rows.Count -gt 1) { throw '日本語推敲スキルの設定行が重複しています。' }
    $value = $rows[0].Groups[1].Value.Trim()
    switch -Regex ($value) {
        '^(|使用しない|無効|none)$' { return 'none' }
        '^(使用する|有効|humanizer-jp)$' { return 'humanizer-jp' }
        '^japanese-natural-writing(?:[（(]Gemini[）)])?$' { return 'japanese-natural-writing' }
        default { throw '日本語推敲スキルには使用しない・humanizer-jp・japanese-natural-writingを指定してください。' }
    }
}

function Find-OptionalGit {
    $command = Get-Command git -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}

function Invoke-OptionalGit([string]$Git, [string[]]$Arguments) {
    $priorPreference = $ErrorActionPreference
    $priorPrompt = [Environment]::GetEnvironmentVariable('GIT_TERMINAL_PROMPT', 'Process')
    try {
        $ErrorActionPreference = 'Continue'
        $env:GIT_TERMINAL_PROMPT = '0'
        $output = @(& $Git @Arguments 2>&1 | ForEach-Object { "$_" })
        if ($LASTEXITCODE -ne 0) { throw ('Git処理に失敗しました: ' + ($output -join "`n")) }
        return ($output -join "`n")
    } finally {
        $ErrorActionPreference = $priorPreference
        [Environment]::SetEnvironmentVariable('GIT_TERMINAL_PROMPT', $priorPrompt, 'Process')
    }
}

function Get-OptionalArchive($Source, [string]$Work, [string]$Git) {
    $zip = Join-Path $Work 'source.zip'
    if ($Source.method -eq 'git') {
        if ($Source.repository -notmatch '^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git$' -or $Source.revision -notmatch '^[a-f0-9]{40}$') { throw 'Gitの取得先または固定版が不正です。' }
        $repo = Join-Path $Work 'repo'
        $hooks = Join-Path $Work 'empty-hooks'
        $null = [IO.Directory]::CreateDirectory($hooks)
        $null = Invoke-OptionalGit $Git @('-c', "core.hooksPath=$hooks", 'init', '--quiet', $repo)
        $null = Invoke-OptionalGit $Git @('-C', $repo, '-c', "core.hooksPath=$hooks", '-c', 'credential.helper=', 'fetch', '--quiet', '--depth=1', $Source.repository, $Source.revision)
        $head = Invoke-OptionalGit $Git @('-C', $repo, 'rev-parse', 'FETCH_HEAD')
        if ($head.Trim() -cne $Source.revision) { throw '取得したGitの版が一致しません。' }
        $names = @($Source.files.PSObject.Properties.Name)
        $tree = Invoke-OptionalGit $Git (@('-C', $repo, 'ls-tree', '-r', $head, '--') + $names)
        if ($tree -match '(?m)^(120000|160000) ') { throw 'スキル内のリンクやサブモジュールは導入しません。' }
        $null = Invoke-OptionalGit $Git (@('-C', $repo, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'archive', '--format=zip', "--output=$zip", $head, '--') + $names)
    } elseif ($Source.method -eq 'zip') {
        if ($Source.url -notmatch '^https://note\.com/api/v2/attachments/download/[a-f0-9]+$' -or $Source.revision -notmatch '^[a-f0-9]{64}$') { throw 'ZIPの取得先または固定版が不正です。' }
        $priorProtocol = [Net.ServicePointManager]::SecurityProtocol
        try {
            [Net.ServicePointManager]::SecurityProtocol = $priorProtocol -bor [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $Source.url -OutFile $zip -TimeoutSec 60
        } finally { [Net.ServicePointManager]::SecurityProtocol = $priorProtocol }
        if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Source.revision) { throw 'ZIPの内容が確認済みの版から変わっています。' }
    } else { throw '未対応の取得方法です。' }
    return $zip
}

function Expand-OptionalArchive([string]$Zip, $Source, [string]$Stage) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Zip)
    try {
        $expected = @{}
        foreach ($file in $Source.files.PSObject.Properties) {
            if ($file.Name -notmatch '^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$' -or $file.Name.Split('/') -contains '..' -or $file.Value -notmatch '^[a-f0-9]{64}$') { throw '取得対象のファイル指定が不正です。' }
            $expected[$Source.prefix + $file.Name] = $file
        }
        $seen = @{}
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName.EndsWith('/')) { continue }
            if (-not $expected.ContainsKey($entry.FullName) -or $seen.ContainsKey($entry.FullName)) { throw 'ZIPに想定外または重複するファイルがあります。' }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'ZIP内のリンクは導入しません。' }
            $file = $expected[$entry.FullName]
            $path = Assert-OptionalPath $Stage $file.Name
            $null = [IO.Directory]::CreateDirectory((Split-Path $path -Parent))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $false)
            if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value) { throw 'スキルのファイル内容が確認済みの版と一致しません。' }
            $seen[$entry.FullName] = $true
        }
        if ($seen.Count -ne $expected.Count) { throw 'スキルの必要ファイルが不足しています。' }
    } finally { $archive.Dispose() }
}

function Initialize-OptionalSkills {
    [CmdletBinding()]
    param([string]$ProjectRoot, [string]$Provider = '', [string]$GeminiConsent = 'Unspecified', [string]$ConsentNote = '')
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'
    $root = [IO.Path]::GetFullPath($ProjectRoot)
    if (-not (Test-Path -LiteralPath (Join-Path $root 'project.json') -PathType Leaf)) { throw '配布先の作品プロジェクトで実行してください。' }
    if (-not $Provider) { $Provider = Get-OptionalSelection $root }
    if ($Provider -eq 'none') { return [pscustomobject]@{ status = 'disabled'; provider = 'none'; message = '推敲スキルは無効です。外部取得・Git確認・Gemini呼び出しは行いません。' } }
    if ($Provider -notin @('humanizer-jp', 'japanese-natural-writing')) { throw '未対応の推敲スキルです。' }
    $manifestPath = Assert-OptionalPath $root 'config/optional-skills.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1) { throw '推敲スキルの配布設定が不正です。' }
    $source = $manifest.providers.$Provider
    $targetRelative = '.agents/skills/' + $Provider
    $target = Assert-OptionalPath $root $targetRelative
    $stateRelative = '.work/optional-skills/' + $Provider
    $receiptPath = Assert-OptionalPath $root ($stateRelative + '-installed.json')
    $consentPath = Assert-OptionalPath $root ($stateRelative + '-consent.json')
    # Geminiの環境検出・有効化設定を、利用枠の消費許可に置き換えない。
    $requiresConsent = $Provider -eq 'japanese-natural-writing' -or $source.requiresGeminiConsent
    if ($requiresConsent) {
        if ($GeminiConsent -notin @('Unspecified', 'Granted', 'Denied')) { throw 'Geminiの回答状態が不正です。' }
        if ($GeminiConsent -ne 'Unspecified') {
            if ([string]::IsNullOrWhiteSpace($ConsentNote)) { throw 'ユーザーの明示回答と許可範囲の記録が必要です。' }
            Write-OptionalJson ([ordered]@{ provider = $Provider; revision = $source.revision; decision = $GeminiConsent; note = $ConsentNote; recordedAt = [DateTimeOffset]::Now.ToString('o') }) $consentPath
        }
        $consent = if (Test-Path -LiteralPath $consentPath) { Get-Content -LiteralPath $consentPath -Raw -Encoding UTF8 | ConvertFrom-Json } else { $null }
        if (-not $consent -or $consent.provider -cne $Provider -or $consent.revision -cne $source.revision -or [string]::IsNullOrWhiteSpace($consent.note)) {
            return [pscustomobject]@{ status = 'needs_gemini_consent'; provider = $Provider; message = 'この作品の選択した文章をGeminiへ送り、利用枠を消費して推敲してよいか、導入前にユーザーへ確認してください。' }
        }
        if ($consent.decision -cne 'Granted') { return [pscustomobject]@{ status = 'gemini_declined'; provider = $Provider; message = 'Geminiの許可がありません。取得・導入・呼び出しを行わず、通常の制作を続けてください。' } }
    }
    if (Test-Path -LiteralPath $target) {
        if (-not (Test-Path -LiteralPath $receiptPath)) { throw '同名の既存スキルを上書きしません。導入記録との照合が必要です。' }
        $receipt = Get-Content -LiteralPath $receiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($receipt.provider -cne $Provider -or $receipt.path -cne $targetRelative -or $receipt.revision -cne $source.revision) { throw '導入済み版・配置先が異なります。更新は別途扱ってください。' }
        $expectedNames = @(@($source.files.PSObject.Properties.Name) + @('agents/openai.yaml') | Sort-Object -Unique)
        if (@(Compare-Object $expectedNames @($receipt.files.PSObject.Properties.Name)).Count -ne 0) { throw '導入記録のファイル一覧が一致しません。' }
        foreach ($file in $receipt.files.PSObject.Properties) {
            $path = Assert-OptionalPath $target $file.Name
            if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $file.Value) { throw '導入済みのスキルに変更・欠落があります。自動で上書きしません。' }
        }
        return [pscustomobject]@{ status = 'ready'; provider = $Provider; path = $targetRelative; message = '導入済みです。外部から再取得しません。' }
    }
    $git = if ($source.method -eq 'git') { Find-OptionalGit } else { $null }
    if ($source.method -eq 'git' -and -not $git) {
        return [pscustomobject]@{ status = 'needs_git_consent'; provider = $Provider; message = 'Gitがありません。Gitをインストールしてよいかユーザーへ確認し、許可を得てから導入してください。' }
    }
    $work = Assert-OptionalPath $root ('.work/optional-skills/download-' + [Guid]::NewGuid().ToString('N'))
    $stage = Join-Path $work 'skill'
    $null = [IO.Directory]::CreateDirectory($stage)
    $zip = Get-OptionalArchive $source $work $git
    Expand-OptionalArchive $zip $source $stage
    if (-not (Test-Path -LiteralPath (Join-Path $stage 'SKILL.md') -PathType Leaf)) { throw 'SKILL.mdがありません。' }
    # 明示的に選択した対象だけへ適用する。元の定義・ライセンスは保持する。
    $policyPath = Join-Path $stage 'agents/openai.yaml'
    $policy = if (Test-Path -LiteralPath $policyPath) { Get-Content -LiteralPath $policyPath -Raw -Encoding UTF8 } else { '' }
    if ($policy -match '(?m)^policy\s*:') { throw '呼び出し方針が変わっています。確認してから導入してください。' }
    $null = [IO.Directory]::CreateDirectory((Split-Path $policyPath -Parent))
    [IO.File]::WriteAllText($policyPath, ($policy.TrimEnd() + "`npolicy:`n  allow_implicit_invocation: false`n"), [Text.UTF8Encoding]::new($false))
    $files = [ordered]@{}
    foreach ($name in @($source.files.PSObject.Properties.Name) + @('agents/openai.yaml') | Select-Object -Unique) {
        $files[$name] = (Get-FileHash -LiteralPath (Join-Path $stage $name) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $receipt = [ordered]@{ provider = $Provider; revision = $source.revision; path = $targetRelative; installedAt = [DateTimeOffset]::Now.ToString('o'); files = $files; adjustment = '暗黙の呼び出しを無効化。選択した対象だけへ明示適用。' }
    $null = [IO.Directory]::CreateDirectory((Split-Path $target -Parent))
    # ステージと配置先が作品内の通常パスであることを、移動の直前にも確認する。
    $null = Assert-OptionalPath $root ($stage.Substring($root.Length).TrimStart('\', '/'))
    $null = Assert-OptionalPath $root $targetRelative
    if (Test-Path -LiteralPath $target) { throw '導入先が作成されたため、上書きせず停止します。' }
    Move-Item -LiteralPath $stage -Destination $target
    Write-OptionalJson $receipt $receiptPath
    return [pscustomobject]@{ status = 'installed'; provider = $Provider; path = $targetRelative; message = '作品内へ導入しました。認識されない場合だけCodexを開き直してください。' }
}

if ($MyInvocation.InvocationName -ne '.') {
    if (-not $ProjectRoot) { $ProjectRoot = Split-Path $PSScriptRoot -Parent }
    Initialize-OptionalSkills -ProjectRoot $ProjectRoot -Provider $Provider -GeminiConsent $GeminiConsent -ConsentNote $ConsentNote
}
