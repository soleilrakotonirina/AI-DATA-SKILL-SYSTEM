#!/usr/bin/env bash
# =============================================================================
# setup_directus.sh — Setup complet Directus 11 (schema + permissions)
# Compatible Directus 11+ qui utilise /policies au lieu de /permissions+role
# Usage : bash setup_directus.sh
# =============================================================================

set -e

DIRECTUS_URL="${DIRECTUS_URL:-http://localhost:8055}"
SCHEMA_FILE="${SCHEMA_FILE:-./snapshots/schema.json}"
COLLECTIONS=("sessions" "reports_mdx" "charts" "pipeline_logs" "user_profiles")

# ── Charger le token ──────────────────────────────────────────────────────────
for env_file in "../backend/.env" "./backend/.env" "./.env"; do
  [ -f "$env_file" ] && export $(grep -v '^#' "$env_file" | grep 'DIRECTUS_TOKEN' | xargs) 2>/dev/null || true
done
TOKEN="${DIRECTUS_TOKEN:-}"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AI DATA SKILL SYSTEM — Setup Directus 11          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "  URL    : $DIRECTUS_URL"
echo "  Schema : $SCHEMA_FILE"
echo ""

if [ -z "$TOKEN" ]; then
  echo "❌  DIRECTUS_TOKEN introuvable. Exportez-le :"
  echo "    export DIRECTUS_TOKEN=votre_token"
  exit 1
fi

# ── Attendre Directus ─────────────────────────────────────────────────────────
echo "⏳  Attente de Directus..."
for i in $(seq 1 30); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$DIRECTUS_URL/server/health" 2>/dev/null || echo "000")
  [ "$STATUS" = "200" ] && echo "✅  Directus prêt." && break
  [ "$i" = "30" ] && echo "❌  Timeout." && exit 1
  sleep 1
done

# ── Vérifier le token ─────────────────────────────────────────────────────────
echo ""
echo "🔑  Vérification du token..."
HTTP_ME=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$DIRECTUS_URL/users/me")
[ "$HTTP_ME" != "200" ] && echo "❌  Token invalide (HTTP $HTTP_ME)" && exit 1
echo "✅  Token valide."

# ── Appliquer le schéma ───────────────────────────────────────────────────────
echo ""
echo "📦  Application du schéma..."
[ ! -f "$SCHEMA_FILE" ] && echo "❌  Schéma introuvable : $SCHEMA_FILE" && exit 1

npx directus schema apply "$SCHEMA_FILE" --yes
echo "✅  Schéma appliqué."
echo "⏳  Pause 2s..."
sleep 2

# ── Trouver la policy Admin (Directus 11) ─────────────────────────────────────
# Directus 11 : les permissions sont liées à des "policies", pas directement aux rôles.
# La policy "Administrator" est celle avec admin_access = true.
echo ""
echo "🔍  Recherche de la policy Administrator (Directus 11)..."

POLICIES_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$DIRECTUS_URL/policies?limit=100")

ADMIN_POLICY=$(echo "$POLICIES_RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for p in d.get('data', []):
        if p.get('admin_access') == True:
            print(p['id']); break
except: pass
" 2>/dev/null)

# Fallback : chercher par nom
if [ -z "$ADMIN_POLICY" ]; then
  ADMIN_POLICY=$(echo "$POLICIES_RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for p in d.get('data', []):
        if 'admin' in p.get('name','').lower():
            print(p['id']); break
except: pass
" 2>/dev/null)
fi

if [ -z "$ADMIN_POLICY" ]; then
  echo "⚠️   Policy Administrator introuvable."
  echo "    Affichage des policies disponibles :"
  echo "$POLICIES_RESP" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for p in d.get('data',[]):
        print(f\"    id={p.get('id')} name={p.get('name')} admin={p.get('admin_access')}\")
except: pass
"
  echo ""
  echo "    Entrez manuellement l'ID de la policy Admin :"
  read -r ADMIN_POLICY
fi

echo "✅  Policy : $ADMIN_POLICY"

# ── Permissions via /permissions avec policy (Directus 11) ────────────────────
echo ""
echo "🔐  Configuration des permissions (Directus 11)..."

for COL in "${COLLECTIONS[@]}"; do
  for ACTION in create read update delete; do

    # Vérifier si la permission existe déjà
    EXISTING=$(curl -s \
      -H "Authorization: Bearer $TOKEN" \
      "$DIRECTUS_URL/permissions?filter[collection][_eq]=$COL&filter[action][_eq]=$ACTION&filter[policy][_eq]=$ADMIN_POLICY&limit=1" \
      | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(len(d.get('data',[])))
except: print(0)
" 2>/dev/null)

    if [ "$EXISTING" = "0" ] || [ -z "$EXISTING" ]; then
      # Directus 11 : champ "policy" obligatoire (remplace "role")
      RESP=$(curl -s -X POST "$DIRECTUS_URL/permissions" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "{
          \"policy\": \"$ADMIN_POLICY\",
          \"collection\": \"$COL\",
          \"action\": \"$ACTION\",
          \"fields\": \"*\",
          \"permissions\": {},
          \"validation\": {}
        }")
      OK=$(echo "$RESP" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print('ok' if 'data' in d else 'err')
except: print('err')
" 2>/dev/null)
      [ "$OK" = "ok" ] && echo "    ✔  $COL.$ACTION" || echo "    ❌  $COL.$ACTION — $RESP"
    else
      echo "    –  $COL.$ACTION (déjà présente)"
    fi
  done
done
echo "✅  Permissions configurées."

# ── Vérification finale ───────────────────────────────────────────────────────
echo ""
echo "🧪  Vérification finale..."
ALL_OK=true

for COL in "${COLLECTIONS[@]}"; do
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "$DIRECTUS_URL/items/$COL?limit=1")

  FIELDS=$(curl -s \
    -H "Authorization: Bearer $TOKEN" \
    "$DIRECTUS_URL/fields/$COL" \
    | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    fields=[f['field'] for f in d.get('data',[])]
    print(str(len(fields))+' champs: '+', '.join(fields))
except: print('?')
" 2>/dev/null)

  if [ "$HTTP" = "200" ]; then
    echo "    ✅  $COL — $FIELDS"
  else
    echo "    ❌  $COL — HTTP $HTTP"
    ALL_OK=false
  fi
done

echo ""
if [ "$ALL_OK" = "true" ]; then
  echo "🎉  Setup terminé avec succès !"
  echo ""
  echo "    ✅  5 collections créées avec tous leurs champs"
  echo "    ✅  Permissions configurées (Directus 11 policy)"
  echo ""
  echo "    Prochaine étape :"
  echo "    cd ../backend && uvicorn api.main:app --reload --port 8000"
else
  echo "⚠️   Certaines collections sont inaccessibles."
  echo "    Relancez : bash setup_directus.sh"
fi
echo ""