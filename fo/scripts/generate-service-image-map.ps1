
$ErrorActionPreference = "Stop"

$projectRoot = (Get-Location).Path
$assetRoot = Join-Path $projectRoot "assets\services"
$outputFile = Join-Path $projectRoot "src\super-admin\utils\serviceAssetMap.ts"

if (-not (Test-Path $assetRoot)) {
    throw "Image folder not found: $assetRoot"
}

$files = Get-ChildItem -Path $assetRoot -Recurse -File |
    Where-Object { $_.Extension -match '^\.(png|jpe?g|webp)$' } |
    Sort-Object FullName

if ($files.Count -eq 0) {
    throw "No supported images found in $assetRoot"
}

$entries = foreach ($file in $files) {
    $relative = $file.FullName.Substring($assetRoot.TrimEnd('\').Length + 1)
    $relative = $relative.Replace('\', '/')

    $key = "/services/$relative"
    $requirePath = "../../../assets/services/$relative"

    $keyJson = ConvertTo-Json -InputObject $key -Compress
    $requireJson = ConvertTo-Json -InputObject $requirePath -Compress

    "  ${keyJson}: require(${requireJson}),"
}

$content = @"
import type { ImageSourcePropType } from 'react-native';

// Generated from assets/services. Do not edit manually.
export const SERVICE_IMAGE_MAP: Record<string, ImageSourcePropType> = {
$($entries -join "`r`n")
};

const LOWERCASE_SERVICE_IMAGE_MAP: Record<string, ImageSourcePropType> = {};

for (const [path, source] of Object.entries(SERVICE_IMAGE_MAP)) {
  LOWERCASE_SERVICE_IMAGE_MAP[path.toLowerCase()] = source;
}

export function getLocalServiceImage(
  assetPath: string | null | undefined
): ImageSourcePropType | undefined {
  if (!assetPath || typeof assetPath !== 'string') return undefined;

  let normalized = assetPath.trim().replace(/\\/g, '/');

  // If a legacy web URL contains a local /services path, resolve that path
  // against the bundled registry instead of downloading the URL.
  if (/^https?:\/\//i.test(normalized)) {
    const match = normalized.match(/^https?:\/\/[^/]+(\/[^?#]*)?/i);
    normalized = match?.[1] || '';
  }

  normalized = normalized.split(/[?#]/)[0];

  try {
    normalized = decodeURIComponent(normalized);
  } catch {
    // Keep the original path if it contains invalid URL encoding.
  }

  if (!normalized.startsWith('/')) {
    normalized = '/' + normalized;
  }

  if (!normalized.toLowerCase().startsWith('/services/')) {
    return undefined;
  }

  return (
    SERVICE_IMAGE_MAP[normalized] ??
    LOWERCASE_SERVICE_IMAGE_MAP[normalized.toLowerCase()]
  );
}
"@

$outputDirectory = Split-Path $outputFile -Parent
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
Set-Content -Path $outputFile -Value $content -Encoding UTF8

Write-Host "Generated $outputFile"
Write-Host "Images registered: $($files.Count)"
