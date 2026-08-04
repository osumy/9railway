#!/usr/bin/env bash
#
# 9router-cli.sh — مدیریت کامل سرویس‌های 9Router روی Railway
# ============================================================
# یک ابزار CLI که همه‌چیز رو خودکار می‌کنه:
#   · پروژه‌ای به اسم '9router' می‌سازه (اگه نباشه)
#   · چند سرویس 9router همزمان بالا میاره
#   · هر سرویس رو خودکار تنظیم می‌کنه (لاگین → مدل → combo → API key)
#   · همه‌چیز (URL + API key + combo) رو توی state.json ذخیره می‌کنه
#   · قابلیت مدیریت: list, keys, down, status
#
# استفاده:
#   bash 9router-cli.sh up [تعداد]         # N تا سرویس جدید بالا بیار (پیش‌فرض 1)
#   bash 9router-cli.sh list               # لیست سرویس‌های ذخیره‌شده
#   bash 9router-cli.sh keys               # نمایش API key ها
#   bash 9router-cli.sh status             # وضعیت زندهٔ Railway
#   bash 9router-cli.sh down [name|all]    # حذف یکی یا همهٔ سرویس‌ها
#   bash 9router-cli.sh setpass <new>      # تغییر پسورد پیش‌فرض (settings.json)
#   bash 9router-cli.sh reset             # ریست state.json (سرویس‌ها دست نمی‌خورن)
#
# تنظیمات: settings.json (پسورد پیش‌فرض MyPassword123456)
# وضعیت:   state.json (خروجی‌های هر سرویس)
set -euo pipefail

# ---------------------------------------------------------------------------
# مسیرها
# ---------------------------------------------------------------------------
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETTINGS_FILE="$DIR/settings.json"
STATE_FILE="$DIR/state.json"

# ---------------------------------------------------------------------------
# توکن Railway
# ---------------------------------------------------------------------------
if [[ -z "${RAILWAY_API_TOKEN:-}" && -f "$DIR/.railway-token" ]]; then
  RAILWAY_API_TOKEN="$(tr -d '[:space:]' < "$DIR/.railway-token")"
fi
if [[ -z "${RAILWAY_API_TOKEN:-}" ]]; then
  echo "❌ RAILWAY_API_TOKEN پیدا نشد. توی .railway-token بذار یا export کن."
  exit 1
fi
export RAILWAY_API_TOKEN

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
pyget() {  # pyget <json> <dot.path>
  python -c "
import json,sys
try:
    d = json.loads(sys.argv[1])
    for k in sys.argv[2].split('.'):
        if isinstance(d, list): d = d[int(k)]
        else: d = d[k]
    print(d if isinstance(d,(str,int,float,bool)) else json.dumps(d, ensure_ascii=False))
except Exception:
    pass
" "$1" "$2" 2>/dev/null || true
}

ensure_settings() {
  if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo '{
  "default_password": "MyPassword123456",
  "combo_name": "claude-opus-5",
  "model_id": "oc/deepseek-v4-flash-free"
}' > "$SETTINGS_FILE"
  fi
}

ensure_state() {
  if [[ ! -f "$STATE_FILE" ]]; then
    echo '{"services": []}' > "$STATE_FILE"
  fi
}

read_setting() {  # read_setting <key>
  ensure_settings
  pyget "$(cat "$SETTINGS_FILE")" "$1"
}

read_state() {
  ensure_state
  cat "$STATE_FILE"
}

write_state() {
  python - "$@" <<'PYEOF'
import json, sys
path = sys.argv[1]
data = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else {"services": []}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
PYEOF
  echo "   ✅ state.json ذخیره شد"
}

# پیدا کردن workspace id
get_workspace_id() {
  railway project list --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d[0]['workspace']['id'] if isinstance(d,list) and d else '')
except: pass
" 2>/dev/null || true
}

# پیدا کردن PROJECT_ID پروژه‌ای به اسم '9router' (که deleted نباشه)
find_9router_project() {
  railway project list --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for p in d:
        if p.get('name') == '9router' and not p.get('deletedAt'):
            print(p['id']); break
except: pass
" 2>/dev/null || true
}

# پیدا کردن سرویس‌های فعال 9router در یک پروژه
list_services() {  # list_services <project_id>
  railway service list --project "$1" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    for s in d:
        print((s.get('id') or '').strip(), '|', (s.get('name') or '').strip())
except: pass
" 2>/dev/null | tr -d '\r' || true
}

# پیدا کردن دامنهٔ یک سرویس
get_service_domain() {  # get_service_domain <project> <service_name>
  railway domain list --project "$1" --service "$2" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(d['domains'][0]['domain'] if d.get('domains') else '')
except: pass
" 2>/dev/null || true
}

# پیدا کردن اسم سرویسِ تازه‌ساخته (آخرین سرویسی که با 9router شروع میشه)
latest_9router_service() {  # latest_9router_service <project_id>
  railway service list --project "$1" --environment production --json 2>/dev/null | python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    names = [s['name'] for s in d if '9router' in str(s.get('name','')).lower()]
    print(names[-1] if names else '')
except: pass
" 2>/dev/null || true
}

# آیا این سرویس قبلاً توی state هست؟
service_in_state() {  # service_in_state <state> <service_name>
  python -c "
import json,sys
d = json.loads(sys.argv[1])
name = sys.argv[2]
for s in d.get('services', []):
    if s.get('service') == name:
        print('yes'); break
else:
    print('no')
" "$1" "$2" 2>/dev/null || echo "no"
}

# ---------------------------------------------------------------------------
# فانکشن‌ها
# ---------------------------------------------------------------------------

# تنظیم کامل یک سرویس: لاگین → مدل → combo → key → ذخیره در state
configure_service() {  # configure_service <project_id> <service_name> <password>
  local PROJECT_ID="$1" SVC="$2" PASSWORD="$3"
  local DOMAIN SVC_STATE

  DOMAIN="$(get_service_domain "$PROJECT_ID" "$SVC")"
  if [[ -z "${DOMAIN:-}" ]]; then
    echo "   ⚠️  دامنه برای $SVC پیدا نشد"
    return 1
  fi

  echo "   → تنظیم $SVC ($DOMAIN)"

  # لاگین
  local COOKIE_JAR="$(mktemp)"
  local LOGIN
  LOGIN="$(curl -s -m 25 -c "$COOKIE_JAR" -H "Content-Type: application/json" \
      -d "$(printf '{"password":"%s"}' "$PASSWORD")" "https://$DOMAIN/api/auth/login" || true)"
  if ! printf '%s' "$LOGIN" | python -c "import json,sys; exit(0 if json.load(sys.stdin).get('success') else 1)" 2>/dev/null; then
    echo "   ⚠️  لاگین $SVC ناموفق — پاسخ: $LOGIN"
    rm -f "$COOKIE_JAR"
    return 1
  fi

  # مدل
  local MODEL_ID COMBO_NAME
  MODEL_ID="$(read_setting model_id)"; COMBO_NAME="$(read_setting combo_name)"
  curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
      -d "$(printf '{"providerAlias":"%s","id":"%s","type":"llm"}' "${MODEL_ID%%/*}" "${MODEL_ID#*/}")" \
      "https://$DOMAIN/api/models/custom" >/dev/null 2>&1 || true

  # combo
  curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
      -d "$(printf '{"name":"%s","models":["%s"]}' "$COMBO_NAME" "$MODEL_ID")" \
      "https://$DOMAIN/api/combos" >/dev/null 2>&1 || true

  # API key
  local KEY_RESP API_KEY
  KEY_RESP="$(curl -s -m 25 -b "$COOKIE_JAR" -H "Content-Type: application/json" \
      -d "$(printf '{"name":"9router-%s"}' "$SVC")" "https://$DOMAIN/api/keys" || true)"
  API_KEY="$(printf '%s' "$KEY_RESP" | python -c "
import json,sys
try: print(json.load(sys.stdin).get('key',''))
except: pass
" 2>/dev/null || true)"

  rm -f "$COOKIE_JAR"

  # ذخیره در state
  local STATE
  STATE="$(read_state)"
  SVC_STATE="$(printf '{"service":"%s","url":"https://%s","api_key":"%s","combo":"%s","model":"%s","created":"%s","project_id":"%s"}' \
      "$SVC" "$DOMAIN" "$API_KEY" "$COMBO_NAME" "$MODEL_ID" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$PROJECT_ID")"
  python - "$STATE_FILE" "$STATE" "$SVC_STATE" <<'PYEOF'
import json, sys
path, state, new_svc = sys.argv[1], json.loads(sys.argv[2]), json.loads(sys.argv[3])
# حذف ورودی قبلی با همین سرویس (اگه هست)
state["services"] = [s for s in state["services"] if s.get("service") != new_svc["service"]]
state["services"].append(new_svc)
with open(path, "w", encoding="utf-8") as f:
    json.dump(state, f, indent=2, ensure_ascii=False)
PYEOF

  echo "   ✅ $SVC آماده شد: $API_KEY"
}

# فرمان up: N سرویس جدید بالا بیار
cmd_up() {
  local N="${1:-1}"
  local PASSWORD COMBO_NAME MODEL_ID
  ensure_settings
  PASSWORD="$(read_setting default_password)"
  COMBO_NAME="$(read_setting combo_name)"
  MODEL_ID="$(read_setting model_id)"

  # پروژهٔ '9router' پیدا کن یا بساز
  local PROJECT_ID
  PROJECT_ID="$(find_9router_project)"
  if [[ -z "${PROJECT_ID:-}" ]]; then
    echo "   پروژهٔ '9router' پیدا نشد → ساختش..."
    local WS_ID
    WS_ID="$(get_workspace_id)"
    railway init --name 9router --workspace "$WS_ID" --json >/dev/null 2>&1 || \
      railway init --name 9router >/dev/null 2>&1 || true
    # بعد از init، پروژه رو دوباره از لیست پیدا کن (مطمئن‌تر)
    sleep 3
    PROJECT_ID="$(find_9router_project)"
    echo "   ✅ پروژهٔ 9router ساخته شد: $PROJECT_ID"
  else
    echo "   ✅ پروژهٔ 9router هست: $PROJECT_ID"
  fi

  echo ""
  echo "   بالا آوردن $N سرویس..."
  for ((i=1; i<=N; i++)); do
    echo ""
    echo "── سرویس $i/$N ──"
    # دیپلوی سرویس جدید (اسم خودکار + هش)
    local DEPLOY_OUT
    DEPLOY_OUT="$(railway deploy --template 9router \
        -v "INITIAL_PASSWORD=${PASSWORD}" \
        -v "DATA_DIR=/app/data" 2>&1 || true)"
    if printf '%s' "$DEPLOY_OUT" | grep -q 'limit exceeded\|3 volumes'; then
      echo "   ⚠️  محدودیت ولوم/منابع → پاک‌سازی ولوم‌های detached و تلاش دوباره..."
      clean_volumes
      sleep 30
      DEPLOY_OUT="$(railway deploy --template 9router \
          -v "INITIAL_PASSWORD=${PASSWORD}" \
          -v "DATA_DIR=/app/data" 2>&1 || true)"
    fi
    echo "$DEPLOY_OUT" | tail -3

    # پیدا کردن اسم سرویسِ تازه (آخرین) — با صبر تا ۹۰ ثانیه
    local SVC
    SVC=""
    local WAIT_SVC=0
    while [[ -z "${SVC:-}" && $WAIT_SVC -lt 9 ]]; do
      sleep 10
      SVC="$(latest_9router_service "$PROJECT_ID")"
      WAIT_SVC=$((WAIT_SVC+1))
    done
    if [[ -z "${SVC:-}" ]]; then
      echo "   ❌ نتونستیم سرویس رو پیدا کنیم. دستی چک کن."
      continue
    fi
    echo "   سرویس: $SVC"

    # صبر تا آنلاین + گرفتن دامنه
    local DOMAIN WAITED
    WAITED=0
    while [[ $WAITED -lt 12 ]]; do
      DOMAIN="$(get_service_domain "$PROJECT_ID" "$SVC")"
      if [[ -n "${DOMAIN:-}" ]] && curl -s -m 10 "https://$DOMAIN/api/health" 2>/dev/null | grep -q '"ok":true'; then
        break
      fi
      sleep 10
      WAITED=$((WAITED+1))
    done
    if [[ -z "${DOMAIN:-}" ]]; then
      echo "   ❌ دامنه برای $SVC پیدا نشد"
      continue
    fi

    # تنظیم کامل سرویس
    configure_service "$PROJECT_ID" "$SVC" "$PASSWORD"
  done

  echo ""
  echo "═══════════════════════════════════════════════"
  echo "  ✅ $N سرویس پردازش شد. برای دیدن:"
  echo "  bash 9router-cli.sh list"
  echo "═══════════════════════════════════════════════"
}

# فرمان list
cmd_list() {
  local STATE
  ensure_state
  STATE="$(read_state)"
  python - "$STATE" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
svcs = d.get("services", [])
if not svcs:
    print("   (هیچ سرویسی توی state نیست — bash 9router-cli.sh up)")
else:
    for i, s in enumerate(svcs, 1):
        print(f"  [{i}] {s.get('service')}")
        print(f"      URL    : {s.get('url')}/v1")
        print(f"      API key: {s.get('api_key')}")
        print(f"      Combo  : {s.get('combo')}  (model: {s.get('model')})")
        print(f"      Created: {s.get('created')}")
        print()
PYEOF
}

# فرمان keys
cmd_keys() {
  local STATE
  ensure_state
  STATE="$(read_state)"
  python - "$STATE" <<'PYEOF'
import json, sys
d = json.loads(sys.argv[1])
svcs = d.get("services", [])
if not svcs:
    print("   (هیچ API key ای توی state نیست)")
else:
    for s in svcs:
        print(f"  {s.get('service')}:  {s.get('api_key')}")
PYEOF
}

# فرمان status
cmd_status() {
  echo "   وضعیت Railway:"
  railway status 2>&1 | grep -iE 'Project:|Service:|url:|volume' | head -20
}

# فرمان down
cmd_down() {
  local TARGET="${1:-}"
  local STATE PROJECT_ID
  ensure_state
  STATE="$(read_state)"
  PROJECT_ID="$(find_9router_project)"

  if [[ "$TARGET" == "all" ]]; then
    echo "   حذف همهٔ سرویس‌های 9router از Railway..."
    local SVCS
    SVCS="$(list_services "$PROJECT_ID" 2>/dev/null || true)"
    if [[ -n "${SVCS:-}" ]]; then
      printf '%s\n' "$SVCS" | while IFS='|' read -r sid sname; do
        sid="$(printf '%s' "$sid" | tr -d ' ')"
        sname="$(printf '%s' "$sname" | tr -d ' ')"
        if [[ -n "$sname" ]]; then
          railway service delete --project "$PROJECT_ID" --service "$sname" --environment production --yes --json >/dev/null 2>&1 || true
          echo "   ✅ حذف شد: $sname"
        fi
      done
    fi
    # پاک کردن state
    echo '{"services": []}' > "$STATE_FILE"
    echo "   ✅ state.json خالی شد"
    # ولوم‌های detached رو هم پاک کن (محدودیت ۳ ولوم)
    clean_volumes
    return
  fi

  # حذف یکی
  if [[ -z "${TARGET:-}" ]]; then
    echo "   استفاده: down <name|all>  یا  down"
    cmd_list
    echo "   از state.json می‌تونی اسم سرویس رو ببینی."
    return
  fi

  # حذف از state (چون railway service delete با نام ممکنه کش کنه، از نام دقیق استفاده می‌کنیم)
  local SVC_NAME
  SVC_NAME="$TARGET"
  railway service delete --project "$PROJECT_ID" --service "$SVC_NAME" --environment production --yes --json >/dev/null 2>&1 \
    && echo "   ✅ حذف شد: $SVC_NAME" \
    || echo "   ⚠️  حذف $SVC_NAME ناموفق (شاید اسم درست نباشه)"
  # از state پاک کن
  python - "$STATE_FILE" "$SVC_NAME" <<'PYEOF'
import json, sys
path, name = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
d["services"] = [s for s in d.get("services", []) if s.get("service") != name]
with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
PYEOF
  echo "   ✅ از state.json پاک شد"
}

# فرمان setpass
cmd_setpass() {
  local NEW="${1:-}"
  if [[ -z "${NEW:-}" ]]; then
    echo "   استفاده: setpass <new-password>"
    return
  fi
  ensure_settings
  python - "$SETTINGS_FILE" "$NEW" <<'PYEOF'
import json, sys
path, newpass = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
d["default_password"] = newpass
with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
PYEOF
  echo "   ✅ پسورد پیش‌فرض به $NEW تغییر کرد"
  echo "   (فقط برای سرویس‌های جدید اعمال می‌شه)"
}

# حذف ولوم‌های detached (سقف ۳ ولوم در پروژه)
clean_volumes() {
  echo "   پاک‌سازی ولوم‌های detached..."
  local VOLS
  VOLS="$(railway volume list 2>/dev/null || true)"
  if [[ -z "${VOLS:-}" ]]; then
    echo "   (ولومی نیست)"
    return
  fi
  printf '%s\n' "$VOLS" | while IFS= read -r line; do
    if printf '%s' "$line" | grep -q '^Volume:'; then
      local vname
      vname="$(printf '%s' "$line" | sed 's/^Volume: //' | tr -d ' \r')"
      CUR_VOL="$vname"
    elif printf '%s' "$line" | grep -qi 'Attached to: N/A'; then
      if [[ -n "${CUR_VOL:-}" ]]; then
        echo "   → حذف ولوم detached: $CUR_VOL"
        railway volume delete -v "$CUR_VOL" -y --json >/dev/null 2>&1 || true
        CUR_VOL=""
      fi
    fi
  done
  echo "   ✅ ولوم‌های detached در صف حذف قرار گرفتن"
}

# فرمان sync: سرویس‌های موجود در پروژه را تنظیم کن (بدون ساخت جدید)
cmd_sync() {
  local PASSWORD PROJECT_ID
  ensure_settings
  PASSWORD="$(read_setting default_password)"
  PROJECT_ID="$(find_9router_project)"
  if [[ -z "${PROJECT_ID:-}" ]]; then
    echo "   ❌ پروژهٔ 9router پیدا نشد. اول:  bash 9router-cli.sh up"
    return 1
  fi
  echo "   تنظیم سرویس‌های موجود در پروژهٔ $PROJECT_ID..."
  local SVCS
  SVCS="$(list_services "$PROJECT_ID" 2>/dev/null || true)"
  if [[ -z "${SVCS:-}" ]]; then
    echo "   (هیچ سرویسی نیست)"
    return
  fi
  printf '%s\n' "$SVCS" | while IFS='|' read -r sid sname; do
    sname="$(printf '%s' "$sname" | tr -d ' \r')"
    [[ -n "$sname" ]] || continue
    configure_service "$PROJECT_ID" "$sname" "$PASSWORD" || true
  done
}

# فرمان reset
cmd_reset() {
  echo '{"services": []}' > "$STATE_FILE"
  echo "   ✅ state.json ریست شد"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
CMD="${1:-help}"
ARG="${2:-}"

case "$CMD" in
  up)        cmd_up "$ARG" ;;
  sync)      cmd_sync ;;
  list)      cmd_list ;;
  keys)      cmd_keys ;;
  status)    cmd_status ;;
  down)      cmd_down "$ARG" ;;
  clean)     clean_volumes ;;
  setpass)   cmd_setpass "$ARG" ;;
  reset)     cmd_reset ;;
  help|--help|-h)
    echo "9router-cli.sh — مدیریت سرویس‌های 9Router روی Railway"
    echo ""
    echo "  up [N]      بالا آوردن N سرویس جدید (پیش‌فرض 1)"
    echo "  sync        تنظیم سرویس‌های موجود (بدون ساخت جدید)"
    echo "  list        نمایش سرویس‌های ذخیره‌شده (URL + API key)"
    echo "  keys        نمایش فقط API key ها"
    echo "  status      وضعیت زندهٔ Railway"
    echo "  down [name|all]  حذف سرویس (یکی یا همه)"
    echo "  clean       پاک‌سازی ولوم‌های detached"
    echo "  setpass <p> تغییر پسورد پیش‌فرض"
    echo "  reset       ریست state.json"
    echo ""
    echo "  settings.json: پسورد پیش‌فرض (MyPassword123456)، combo_name، model_id"
    echo "  state.json:    خروجی‌های هر سرویس"
    ;;
  *)
    echo "دستور ناشناخته: $CMD  (برای راهنما: bash 9router-cli.sh help)"
    exit 1
    ;;
esac
