#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'config\review-profiles.json'),
    [string]$Preset,
    [string]$SceneId
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$keys = @('immersion', 'cinema', 'story', 'readability', 'characterConsistency', 'terminology')

function Assert-Object($Value, [string]$Label) {
    if ($null -eq $Value -or $Value -isnot [pscustomobject]) { throw "$Label must be a JSON object." }
}
function Assert-Fields($Value, [string[]]$Allowed, [string]$Label) {
    foreach ($property in $Value.PSObject.Properties) {
        if ($property.Name -cnotin $Allowed) { throw "Unknown field in ${Label}: $($property.Name)" }
    }
}
function Assert-Weights($Value, [string]$Label, [bool]$Complete) {
    Assert-Object $Value $Label
    Assert-Fields $Value $keys $Label
    foreach ($key in $keys) {
        $property = $Value.PSObject.Properties[$key]
        if ($null -eq $property) {
            if ($Complete) { throw "Missing weight in ${Label}: $key" }
            continue
        }
        $weight = $property.Value
        if (($weight -isnot [int] -and $weight -isnot [long]) -or $weight -lt 1 -or $weight -gt 5) {
            throw "Weight ${Label}.${key} must be an integer from 1 to 5."
        }
    }
}

$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
Assert-Object $config 'config'
Assert-Fields $config @('schemaVersion', 'defaults', 'presets', 'scenes') 'config'
if ($config.schemaVersion -cne 1 -or ($config.schemaVersion -isnot [int] -and $config.schemaVersion -isnot [long])) {
    throw 'Unsupported schemaVersion.'
}
Assert-Weights $config.defaults 'defaults' $true
Assert-Object $config.presets 'presets'
Assert-Object $config.scenes 'scenes'
foreach ($entry in $config.presets.PSObject.Properties) {
    if ([string]::IsNullOrWhiteSpace($entry.Name)) { throw 'Preset name must not be empty.' }
    Assert-Weights $entry.Value "presets.$($entry.Name)" $false
}
foreach ($entry in $config.scenes.PSObject.Properties) {
    $scene = $entry.Value
    if ([string]::IsNullOrWhiteSpace($entry.Name)) { throw 'Scene name must not be empty.' }
    Assert-Object $scene "scenes.$($entry.Name)"
    Assert-Fields $scene @('preset', 'weights', 'reason') "scenes.$($entry.Name)"
    if ($null -ne $scene.PSObject.Properties['preset']) {
        if ($scene.preset -isnot [string] -or $null -eq $config.presets.PSObject.Properties[$scene.preset]) {
            throw "Unknown scene preset: $($entry.Name)"
        }
    }
    if ($null -ne $scene.PSObject.Properties['reason'] -and $scene.reason -isnot [string]) {
        throw "Scene reason must be text: $($entry.Name)"
    }
    if ($null -ne $scene.PSObject.Properties['weights']) { Assert-Weights $scene.weights "scenes.$($entry.Name).weights" $false }
}
if ($Preset -and $null -eq $config.presets.PSObject.Properties[$Preset]) { throw "Unknown preset: $Preset" }
$selectedScene = $null
if ($SceneId) {
    $entry = $config.scenes.PSObject.Properties[$SceneId]
    if ($null -eq $entry) { throw "Unknown scene: $SceneId" }
    $selectedScene = $entry.Value
    if ($null -ne $selectedScene.PSObject.Properties['preset']) { $Preset = $selectedScene.preset }
}
$effective = [ordered]@{}
foreach ($key in $keys) { $effective[$key] = $config.defaults.$key }
if ($Preset) {
    foreach ($entry in $config.presets.PSObject.Properties[$Preset].Value.PSObject.Properties) { $effective[$entry.Name] = $entry.Value }
}
if ($null -ne $selectedScene -and $null -ne $selectedScene.PSObject.Properties['weights']) {
    foreach ($entry in $selectedScene.weights.PSObject.Properties) { $effective[$entry.Name] = $entry.Value }
}
[pscustomobject]@{ schemaVersion = 1; sceneId = $SceneId; preset = $Preset; weights = [pscustomobject]$effective }
