# =============================================================================
# setup_directus.ps1 — Setup complet Directus 11 (schema + permissions)
# Compatible Windows PowerShell 5.1+ et PowerShell 7+
# Usage : .\setup_directus.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$DIRECTUS_URL = if ($env:DIRECTUS_URL) { $env:DIRECTUS_URL } else { "http://localhost:8055" }
$SCHEMA_FILE  = if ($env:SCHEMA_FILE)  { $env:SCHEMA_FILE  } else { ".\snapshots\schema.json" }
$COLLECTIONS  = @("sessions", "reports_mdx", "charts", "pipeline_logs", "user_profiles")

# ── Charger le token depuis .env ──────────────────────────────────────────────
$TOKEN = $env:DIRECTUS_TOKEN
$envFiles = @("..\backend\.env", ".\backend\.env", ".\.env")
foreach ($envFile in $envFiles) {
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match "^DIRECTUS_TOKEN=(.+)$") {
                $TOKEN = $matches[1].Trim()
            }
        }
    }
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   AI DATA SKILL SYSTEM — Setup Directus 11          ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host "  URL    : $DIRECTUS_URL"
Write-Host "  Schema : $SCHEMA_FILE"
Write-Host ""

if (-not $TOKEN) {
    Write-Host "❌  DIRECTUS_TOKEN introuvable." -ForegroundColor Red
    Write-Host "    Exportez-le : `$env:DIRECTUS_TOKEN = 'votre_token'"
    exit 1
}

# ── Fonction utilitaire : appel HTTP ─────────────────────────────────────────
function Invoke-Dir {
    param(
        [string]$Method = "GET",
        [string]$Path,
        [object]$Body = $null,
        [switch]$StatusOnly
    )
    $uri     = "$DIRECTUS_URL$Path"
    $headers = @{ "Authorization" = "Bearer $TOKEN"; "Content-Type" = "application/json" }
    try {
        if ($Body) {
            $json = $Body | ConvertTo-Json -Depth 10 -Compress
            $resp = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -Body $json
        } else {
            $resp = Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
        }
        return $resp
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        if ($StatusOnly) { return $status }
        # Retourner le corps de l'erreur pour debug
        try {
            $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
            return $reader.ReadToEnd() | ConvertFrom-Json
        } catch {
            return $null
        }
    }
}

function Get-HttpStatus {
    param([string]$Path)
    $uri     = "$DIRECTUS_URL$Path"
    $headers = @{ "Authorization" = "Bearer $TOKEN" }
    try {
        $resp = Invoke-WebRequest -Method GET -Uri $uri -Headers $headers -UseBasicParsing
        return $resp.StatusCode
    } catch {
        return $_.Exception.Response.StatusCode.value__
    }
}

# ── Attendre Directus ─────────────────────────────────────────────────────────
Write-Host "⏳  Attente de Directus..." -ForegroundColor Yellow
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $h = Invoke-WebRequest -Uri "$DIRECTUS_URL/server/health" -UseBasicParsing -ErrorAction Stop
        if ($h.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) { Write-Host "❌  Timeout — Directus ne répond pas." -ForegroundColor Red; exit 1 }
Write-Host "✅  Directus prêt." -ForegroundColor Green

# ── Vérifier le token ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "🔑  Vérification du token..." -ForegroundColor Yellow
$meStatus = Get-HttpStatus "/users/me"
if ($meStatus -ne 200) {
    Write-Host "❌  Token invalide (HTTP $meStatus)" -ForegroundColor Red; exit 1
}
Write-Host "✅  Token valide." -ForegroundColor Green

# ── Appliquer le schéma ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "📦  Application du schéma..." -ForegroundColor Yellow
if (-not (Test-Path $SCHEMA_FILE)) {
    Write-Host "❌  Schéma introuvable : $SCHEMA_FILE" -ForegroundColor Red; exit 1
}

# npx fonctionne dans PowerShell si Node.js est installé
npx directus schema apply $SCHEMA_FILE --yes
Write-Host "✅  Schéma appliqué." -ForegroundColor Green
Write-Host "⏳  Pause 2s..."
Start-Sleep -Seconds 2

# ── Trouver la policy Administrator (Directus 11) ─────────────────────────────
Write-Host ""
Write-Host "🔍  Recherche de la policy Administrator..." -ForegroundColor Yellow

$policiesResp = Invoke-Dir -Path "/policies?limit=100"
$adminPolicy  = $null

if ($policiesResp -and $policiesResp.data) {
    # Méthode 1 : admin_access = true
    foreach ($p in $policiesResp.data) {
        if ($p.admin_access -eq $true) { $adminPolicy = $p.id; break }
    }
    # Méthode 2 : nom contient "admin"
    if (-not $adminPolicy) {
        foreach ($p in $policiesResp.data) {
            if ($p.name -match "admin") { $adminPolicy = $p.id; break }
        }
    }
}

if (-not $adminPolicy) {
    Write-Host "⚠️   Policy Administrator introuvable." -ForegroundColor Yellow
    Write-Host "    Policies disponibles :"
    if ($policiesResp -and $policiesResp.data) {
        foreach ($p in $policiesResp.data) {
            Write-Host "    id=$($p.id)  name=$($p.name)  admin=$($p.admin_access)"
        }
    }
    Write-Host ""
    $adminPolicy = Read-Host "    Entrez manuellement l'ID de la policy Admin"
}

Write-Host "✅  Policy : $adminPolicy" -ForegroundColor Green

# ── Créer les permissions ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "🔐  Configuration des permissions..." -ForegroundColor Yellow

foreach ($col in $COLLECTIONS) {
    foreach ($action in @("create", "read", "update", "delete")) {

        # Vérifier si la permission existe déjà
        $checkResp = Invoke-Dir -Path "/permissions?filter[collection][_eq]=$col&filter[action][_eq]=$action&filter[policy][_eq]=$adminPolicy&limit=1"
        $exists = $checkResp -and $checkResp.data -and $checkResp.data.Count -gt 0

        if ($exists) {
            Write-Host "    –  $col.$action (déjà présente)" -ForegroundColor DarkGray
        } else {
            $body = @{
                policy     = $adminPolicy
                collection = $col
                action     = $action
                fields     = "*"
                permissions = @{}
                validation  = @{}
            }
            $resp = Invoke-Dir -Method POST -Path "/permissions" -Body $body
            if ($resp -and $resp.data) {
                Write-Host "    ✔  $col.$action" -ForegroundColor Green
            } else {
                Write-Host "    ❌  $col.$action — $($resp | ConvertTo-Json -Compress)" -ForegroundColor Red
            }
        }
    }
}
Write-Host "✅  Permissions configurées." -ForegroundColor Green

# ── Vérification finale ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "🧪  Vérification finale..." -ForegroundColor Yellow
$allOk = $true

foreach ($col in $COLLECTIONS) {
    $status = Get-HttpStatus "/items/$col`?limit=1"

    $fieldsResp = Invoke-Dir -Path "/fields/$col"
    $fieldNames = if ($fieldsResp -and $fieldsResp.data) {
        $fieldsResp.data | ForEach-Object { $_.field }
    } else { @() }
    $fieldSummary = "$($fieldNames.Count) champs: $($fieldNames -join ', ')"

    if ($status -eq 200) {
        Write-Host "    ✅  $col — $fieldSummary" -ForegroundColor Green
    } else {
        Write-Host "    ❌  $col — HTTP $status" -ForegroundColor Red
        $allOk = $false
    }
}

Write-Host ""
if ($allOk) {
    Write-Host "🎉  Setup terminé avec succès !" -ForegroundColor Green
    Write-Host ""
    Write-Host "    ✅  5 collections créées avec tous leurs champs"
    Write-Host "    ✅  Permissions configurées (Directus 11 policy)"
    Write-Host ""
    Write-Host "    Prochaine étape :"
    Write-Host "    cd ..\backend ; uvicorn api.main:app --reload --port 8000"
} else {
    Write-Host "⚠️   Certaines collections sont inaccessibles." -ForegroundColor Yellow
    Write-Host "    Relancez : .\setup_directus.ps1"
}
Write-Host ""