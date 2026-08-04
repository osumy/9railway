#!/usr/bin/env bash
#
# deploy_9router.sh — دیپلوی خودکار 9Router روی Railway + تنظیم کامل
# =====================================================================
# این کاریه که الان دستی انجام می‌دی = خودکار می‌کنه:
#   1) پروژهٔ جدید می‌سازه (یا به پروژهٔ موجود وصل می‌شه)
#   2) تمپلیت 9router رو دیپلوی می‌کنه (با INITIAL_PASSWORD + DATA_DIR)
#   3) صبر می‌کنه تا سرویس آنلاین بشه
#   4) لاگین می‌کنه
#   5) مدل oc/deepseek-v4-flash-free رو اضافه می‌کنه
#   6) combo به اسم claude-opus-5 می‌سازه (شامل اون مدل)
#   7) API key می‌سازه
#   8) خروجی نهایی: base URL + API key (آماده برای استفاده)
#
# نیازمندی:
#   · Railway CLI نصب -> https://docs.railway.com/reference/cli
#   · توکن اکانت -> Railway Dashboard > Account > Token
#     یا در فایل .railway-token (git-ignored) یا export RAILWAY_API_TOKEN
#   · python3 (برای پارس JSON بدون jq) + curl
#
# استفاده:
#   bash deploy_9router.sh                         # پروژهٔ جدید
#   RAILWAY_UP_PROJECT=<id> bash deploy_9router.sh  # روی پروژهٔ موجود
#
# متغیرهای قابل تنظیم:
#   INITIAL_PASSWORD  رمز داشبورد (پیش‌فرض MyDeepSeekPass123)
#   COMBO_NAME        اسم combo (پیش‌فرض claude-opus-5)
#   MODEL_ID          مدل (پیش‌فرض oc/deepseek-v4-flash-free)
#   API_KEY_NAME      اسم API key (پیش‌فرض 9router-auto)
set -euo pipefail

# ---------------------------------------------------------------------------
# 0) توکن — از env یا فایل .railway-token
# ---------------------------------------------------------------------------
if [[ -z "${RAILWAY_API_TOKEN:-}" && -f .railway-token ]]; then
  RAILWAY_API_TOKEN="$(tr -d '[:space:]' < .railway-token)"
fi
if [[ -z "${RAILWAY_API_TOKEN:-}" ]]; then
  echo "❌ RAILWAY_API_TOKEN پیدا نشد."
  echo "   یا  export RAILWAY_API_TOKEN=...   یا   توکن رو توی .railway-token بذار."
  exit 1
fi
export RAILWAY_API_TOKEN

# ---------------------------------------------------------------------------
# 1) تنظیمات
# ---------------------------------------------------------------------------
TEMPLATE_REPO="9router"
INITIAL_PASSWORD="${INITIAL_PASSWORD:-MyDeepSeekPass123}"
COMBO_NAME="${COMBO_NAME:-claude-opus-5}"
MODEL_ID="${MODEL_ID:-oc/deepseek-v4-flash-free}"
API_KEY_NAME="${API_KEY_NAME:-9router-auto}"
SLEEP_AFTER_DEPLOY="${SLEEP_AFTER_DEPLOY:-25}"

# helper: پارس JSON با python (چون jq روی ویندوز نیست)
pyget() {  # pyget <json> <key-path>  → خروجی plain value
  python -c "
import json,sys
d = json.loads(sys.argv[1])
for k in sys.argv[2].split('.'):
    d = d[k]
print(d if isinstance(d, (str,int,float)) else json.dumps(d))
" "$1" "$2" 2>/dev/null || true
}

echo "═══════════════════════════════════════════════════════════"
echo "  🚀 دیپلوی خودکار 9Router روی Railway"
echo "═══════════════════════════════════════════════════════════"

# ---------------------------------------------------------------------------
# 2) پروژه — ساخت جدید یا استفاده از موجود (RAILWAY_UP_PROJECT)
# ---------------------------------------------------------------------------
echo ""
echo "⟶ [1/6] آماده‌سازی پروژه..."
if [[ -n "${RAILWAY_UP_PROJECT:-}" ]]; then
  PROJECT_ID="$RAILWAY_UP_PROJECT"
  echo "   استفاده از پروژهٔ موجود: $PROJECT_ID"
  railway link --project "$PROJECT_ID" >/dev/null 2>&1 || true
else
  PROJ_NAME="9router-$(date +%Y%m%d-%H%M%S)"
  echo "   ساخت پروژهٔ جدید: $PROJ_NAME"

  # workspace id (برای non-interactive)
  WORKSPACE_ID="${RAILWAY_WORKSPACE_ID:-}"
  if [[ -z "$WORKSPACE_ID" ]]; then
    WS_JSON="$(railway project list --json 2>/dev/null || true)"
    WORKSPACE_ID="$(printf '%s' "$WS_JSON" | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d[0]['workspace']['id'] if isinstance(d,list) and d else '')
except: pass
" 2>/dev/null || true)"
  fi

  INIT_OUT="$(railway init --name "$PROJ_NAME" --workspace "$WORKSPACE_ID" --json 2>&1 || true)"
  PROJECT_ID="$(printf '%s' "$INIT_OUT" | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d.get('id',''))
except: pass
" 2>/dev/null || true)"

  if [[ -z "${PROJECT_ID:-}" ]]; then
    PROJECT_ID="$(printf '%s' "$INIT_OUT" | grep -oE '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}' | head -n1 || true)"
  fi
  if [[ -z "${PROJECT_ID:-}" ]]; then
    echo "⚠️  نتونستیم PROJECT_ID بگیریم. خروجی init:"
    printf '%s\n' "$INIT_OUT"
    railway link
  else
    echo "   ✅ پروژه ساخته شد: $PROJECT_ID"
    railway link --project "$PROJECT_ID" >/dev/null 2>&1 || true
  fi
fi

# ---------------------------------------------------------------------------
# 3) دیپلوی 9router — فقط اگه سرویس از قبل نیست (تا ولوم اضافه نسازه!)
# ---------------------------------------------------------------------------
echo ""
echo "⟶ [2/6] بررسی سرویس 9router در پروژه..."

EXISTING_SVC="$(railway service list --project "$PROJECT_ID" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for s in d:
        if '9router' in str(s.get('name','')).lower():
            print(s['name']); break
except: pass
" 2>/dev/null || true)"

if [[ -n "${EXISTING_SVC:-}" ]]; then
  echo "   ✅ سرویس 9router از قبل هست: $EXISTING_SVC (دیپلوی دوباره نمی‌زنیم)"
  SVC_NAME="$EXISTING_SVC"
else
  echo "   دیپلوی تمپلیت 9router..."
  railway deploy --template "$TEMPLATE_REPO" \
    -v "INITIAL_PASSWORD=${INITIAL_PASSWORD}" \
    -v "DATA_DIR=/app/data"
  sleep 5
  SVC_NAME="$(railway service list --project "$PROJECT_ID" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for s in d:
        if '9router' in str(s.get('name','')).lower():
            print(s['name']); break
except: pass
" 2>/dev/null || true)"
  SVC_NAME="${SVC_NAME:-9router}"
fi

# ---------------------------------------------------------------------------
# 4) صبر تا آنلاین شدن + پیدا کردن دامنه
# ---------------------------------------------------------------------------
echo ""
echo "⟶ [3/6] پیدا کردن آدرس عمومی..."

DOMAIN="$(railway domain list --project "$PROJECT_ID" --service "$SVC_NAME" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d['domains'][0]['domain'] if d.get('domains') else '')
except: pass
" 2>/dev/null || true)"
if [[ -z "${DOMAIN:-}" ]]; then
  # فالبک: خروجی متنی ساده
  DOMAIN="$(railway domain list --project "$PROJECT_ID" --service "$SVC_NAME" --environment production 2>/dev/null | grep -oE 'https://[^ ]+|[a-z0-9-]+\.up\.railway\.app' | head -n1 || true)"
fi
if [[ -z "${DOMAIN:-}" ]]; then
  DOMAIN="$(railway status 2>/dev/null | grep -oE 'https://[^ ]+\.railway\.app' | head -n1 || true)"
fi
if [[ -z "${DOMAIN:-}" ]]; then
  echo "❌ آدرس عمومی پیدا نشد. بعداً دستی:  railway domain"
  echo "   یا از داشبورد Railway. اسکریپت ادامه نمی‌ده."
  exit 1
fi
# نرمال‌سازی: بدون https:// به جز پروتکل
DOMAIN="$(printf '%s' "$DOMAIN" | sed 's#/$##')"
echo "   ✅ آدرس: $DOMAIN"

# صبر تا آنلاین شدن (چک health حداکثر ~2 دقیقه)
echo ""
echo "   صبر تا آنلاین شدن سرویس..."
WAITED=0
while [[ $WAITED -lt 12 ]]; do
  if curl -s -m 10 "https://$DOMAIN/api/health" 2>/dev/null | grep -q '"ok":true'; then
    echo "   ✅ سرویس آنلاینه"
    break
  fi
  sleep 10
  WAITED=$((WAITED+1))
  echo "   ... $((WAITED*10)) ثانیه گذشته"
done
if ! curl -s -m 10 "https://$DOMAIN/api/health" 2>/dev/null | grep -q '"ok":true'; then
  echo "⚠️  سرویس هنوز آنلاین نشده — ادامه با ریسک. اگه لاگین شکست خورد، صبر کن و دوباره اجرا کن."
fi

# ---------------------------------------------------------------------------
# 5) لاگین به داشبورد 9router (کوکی)
# ---------------------------------------------------------------------------
echo ""
echo "⟶ [4/6] لاگین به داشبورد 9router..."
COOKIE_JAR="$(mktemp)"
LOGIN_RESP="$(curl -s -m 25 -c "$COOKIE_JAR" -H "Content-Type: application/json" \
    -d "$(printf '{"password":"%s"}' "$INITIAL_PASSWORD")" \
    "${DOMAIN}/api/auth/login" || true)"
if ! printf '%s' "$LOGIN_RESP" | python -c "import json,sys; exit(0 if json.load(sys.stdin).get('success') else 1)" 2>/dev/null; then
  echo "⚠️  لاگین موفق نشد — پاسخ:"
  printf '%s\n' "$LOGIN_RESP"
  exit 1
fi
echo "   ✅ لاگین موفق شد"

# ---------------------------------------------------------------------------
# 6) جریان کامل: مدل → combo → API key
# ---------------------------------------------------------------------------
echo ""
echo "⟶ [5/6] تنظیم مدل، combo و API key..."

# 6a) اضافه کردن مدل به providerAlias 'oc'
MODEL_RESP="$(curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
    -d "$(printf '{"providerAlias":"%s","id":"%s","type":"llm"}' "${MODEL_ID%%/*}" "${MODEL_ID#*/}")" \
    "${DOMAIN}/api/models/custom" || true)"
if printf '%s' "$MODEL_RESP" | python -c "import json,sys; exit(0 if json.load(sys.stdin).get('success') else 1)" 2>/dev/null; then
  echo "   ✅ مدل اضافه شد: $MODEL_ID"
else
  echo "   ⚠️  افزودن مدل ممکنه از قبل انجام شده باشه یا خطا خورده: $MODEL_RESP"
fi

# 6b) ساخت combo (اگه از قبل هست، خطا میده — نادیده می‌گیریم)
COMBO_RESP="$(curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
    -d "$(printf '{"name":"%s","models":["%s"]}' "$COMBO_NAME" "$MODEL_ID")" \
    "${DOMAIN}/api/combos" || true)"
if printf '%s' "$COMBO_RESP" | python -c "import json,sys; d=json.load(sys.stdin); exit(0 if d.get('id') else 1)" 2>/dev/null; then
  echo "   ✅ combo ساخته شد: $COMBO_NAME → $MODEL_ID"
else
  echo "   ⚠️  ساخت combo نتیجه نداد (شاید از قبل موجوده): $COMBO_RESP"
fi

# 6c) ساخت API key
KEY_RESP="$(curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
    -d "$(printf '{"name":"%s"}' "$API_KEY_NAME")" \
    "${DOMAIN}/api/keys" || true)"
API_KEY="$(printf '%s' "$KEY_RESP" | python -c "
import json,sys
try: print(json.load(sys.stdin).get('key',''))
except: pass
" 2>/dev/null || true)"

rm -f "$COOKIE_JAR"

# ---------------------------------------------------------------------------
# 7) خروجی نهایی
# ---------------------------------------------------------------------------
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  ✅ تنظیم کامل شد! اطلاعات استفاده:"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "  📍 Base URL  : $DOMAIN/v1"
if [[ -n "${API_KEY:-}" ]]; then
  echo "  🔑 API Key   : $API_KEY"
else
  echo "  🔑 API Key   : (ساخت نشد — از داشبورد بساز: Endpoint → Create Key)"
  printf '    پاسخ: %s\n' "$KEY_RESP"
fi
echo "  🧩 Model     : $COMBO_NAME"
echo ""
echo "  🖥  داشبورد  : $DOMAIN/dashboard   (رمز: $INITIAL_PASSWORD)"
echo ""
echo "  نمونه درخواست:"
echo "    curl -X POST \"$DOMAIN/v1/chat/completions\" \\"
echo "      -H \"Content-Type: application/json\" \\"
echo "      -H \"Authorization: Bearer ${API_KEY:-<key>}\" \\"
echo "      -d '{\"model\":\"$COMBO_NAME\",\"messages\":[{\"role\":\"user\",\"content\":\"سلام\"}],\"max_tokens\":300}'"
echo ""
echo "  💡 نکته: مدل reasoning هست — max_tokens رو 300+ بذار که جواب ناقص نشه."
echo "═══════════════════════════════════════════════════════════"
