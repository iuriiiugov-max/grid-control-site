#!/usr/bin/env python3
import argparse
import base64
import calendar
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests

BASE_URL = "https://api.bitget.com"
VERSION = "0.6.1"
SCHEMA = "grid_pilot26_android_observer_v3"
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "config.json"
OUT = ROOT / "out" / "latest.json"
LOG = ROOT / "logs" / "collector.log"
LOCAL = Path(os.environ.get("GRID_PILOT26_SECRET_DIR", str(Path.home() / ".grid_pilot26"))).expanduser()
API_KEY_FILE = LOCAL / "grid_pilot26_READ_api_key"
PASSPHRASE_FILE = LOCAL / "grid_pilot26_READ_passphrase"
PRIVATE_KEY_FILE = LOCAL / "grid_pilot26_READ_private.pem"
PROXY_URL_FILE = LOCAL / "proxy_url"

# Hard fail-closed: private Bitget network calls are GET only and endpoint allowlisted.
ALLOWED_GET_PATHS = {
    "/api/v3/account/info",
    "/api/v3/account/assets",
    "/api/v3/account/settings",
    "/api/v3/trade/unfilled-orders",
    "/api/v3/trade/history-orders",
    "/api/v3/trade/fills",
    "/api/v3/position/current-position",
    "/api/v3/trade/grid/bot-detail",
    "/api/v3/trade/grid/list-details",
}

# Defence in depth: even a future accidental allowlist edit cannot arm these common mutations.
FORBIDDEN_WRITE_MARKERS = (
    "/place-order",
    "/batch-place-order",
    "/cancel",
    "/modify",
    "/close",
    "/create",
    "/add-investment",
    "/transfer",
    "/borrow",
    "/repay",
    "/withdraw",
)

GRID_DELEGATE_TYPES = {
    "strategy_grid_positive",
    "strategy_grid_reverse",
    "strategy_grid_middle",
}



def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg: str):
    line = f"{utc_now()} {msg}"
    print(line)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_secret(path: Path) -> str:
    if not path.exists():
        raise RuntimeError(f"Missing local secret file: {path.name}")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise RuntimeError(f"Unsafe permissions on {path.name}: {oct(mode)}; require 600 or stricter")
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"Empty local secret file: {path.name}")
    return value


def load_local_auth():
    api_key = read_secret(API_KEY_FILE)
    passphrase = read_secret(PASSPHRASE_FILE)
    _ = read_secret(PRIVATE_KEY_FILE)  # permissions/non-empty preflight; signing reads file directly
    proxy_url = None
    if PROXY_URL_FILE.exists():
        proxy_url = read_secret(PROXY_URL_FILE)
        parsed = urlparse(proxy_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or not parsed.port:
            raise RuntimeError("proxy_url must be a complete http(s) proxy URL with host and port")
    return {"api_key": api_key, "passphrase": passphrase, "proxy_url": proxy_url}


def shutil_which(name: str):
    from shutil import which
    return which(name)


def sign_rsa(message: str) -> str:
    if not shutil_which("openssl"):
        raise RuntimeError("openssl executable not found")
    cp = subprocess.run(
        ["openssl", "dgst", "-sha256", "-sign", str(PRIVATE_KEY_FILE)],
        input=message.encode("utf-8"), capture_output=True, check=False
    )
    if cp.returncode != 0:
        raise RuntimeError("local RSA signing failed")
    return base64.b64encode(cp.stdout).decode("ascii")


def auth_headers(auth: dict, method: str, path: str, params=None):
    method = method.upper()
    if method != "GET":
        raise RuntimeError("READ_ONLY observer rejects non-GET method")
    if any(marker in path for marker in FORBIDDEN_WRITE_MARKERS):
        raise RuntimeError(f"Mutating endpoint rejected: {path}")
    if path not in ALLOWED_GET_PATHS:
        raise RuntimeError(f"Endpoint not allowlisted: {path}")
    params = params or {}
    sorted_items = sorted((str(k), str(v)) for k, v in params.items() if v is not None and v != "")
    query = urlencode(sorted_items)
    request_path = path + (("?" + query) if query else "")
    timestamp = str(int(time.time() * 1000))
    prehash = timestamp + "GET" + request_path
    signature = sign_rsa(prehash)
    return {
        "ACCESS-KEY": auth["api_key"],
        "ACCESS-SIGN": signature,
        "ACCESS-PASSPHRASE": auth["passphrase"],
        "ACCESS-TIMESTAMP": timestamp,
        "Content-Type": "application/json",
        "locale": "en-US",
        "User-Agent": f"grid-pilot26-android-readonly/{VERSION}",
    }


def make_session(proxy_url: str | None):
    s = requests.Session()
    s.trust_env = False
    if proxy_url is not None:
        s.proxies = {"http": proxy_url, "https": proxy_url}
    return s


def get_private(session, auth: dict, path: str, params=None, timeout=20):
    canonical_params = dict(sorted((str(k), str(v)) for k, v in (params or {}).items() if v is not None and v != ""))
    headers = auth_headers(auth, "GET", path, canonical_params)
    try:
        r = session.get(BASE_URL + path, params=canonical_params, headers=headers, timeout=timeout)
        r.raise_for_status()
    except requests.HTTPError as e:
        try:
            body = e.response.json()
            code = body.get("code")
            msg = body.get("msg")
        except Exception:
            code = None
            msg = None
        raise RuntimeError(
            f"Bitget HTTP {e.response.status_code}: code={code} msg={msg}"
        ) from None
    except requests.RequestException as e:
        # Deliberately do not stringify e; proxy URLs may contain credentials.
        raise RuntimeError(f"network/proxy failure ({type(e).__name__})") from None
    try:
        body = r.json()
    except Exception:
        raise RuntimeError("Bitget returned non-JSON response") from None
    if str(body.get("code")) != "00000":
        raise RuntimeError(f"Bitget read failed: code={body.get('code')} msg={body.get('msg')}")
    return body.get("data")


def safe_call(fn):
    try:
        return {"ok": True, "data": fn()}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def sanitize_info(data):
    if not isinstance(data, dict):
        return data
    return {
        "permType": data.get("permType"),
        "permissions": data.get("permissions"),
    }


def call_coverage(call_result, enabled=True):
    if not enabled:
        return "DISABLED"
    if isinstance(call_result, dict) and call_result.get("ok") is True:
        return "COMPLETE"
    return "FAILED"


def _call_list(call_result):
    if not isinstance(call_result, dict) or call_result.get("ok") is not True:
        return []
    data = call_result.get("data")
    if isinstance(data, dict):
        rows = data.get("list")
        return rows if isinstance(rows, list) else []
    return data if isinstance(data, list) else []


def detect_grid_order_activity(open_orders, recent_orders):
    evidence = []
    seen = set()
    for source_name, call_result in (("openSpotOrders", open_orders), ("recentSpotOrders", recent_orders)):
        for row in _call_list(call_result):
            if not isinstance(row, dict):
                continue
            delegate_type = str(row.get("delegateType") or "").strip()
            if delegate_type not in GRID_DELEGATE_TYPES:
                continue
            order_id = str(row.get("orderId") or "").strip()
            key = (source_name, order_id or str(row.get("clientOid") or ""))
            if key in seen:
                continue
            seen.add(key)
            evidence.append({
                "source": source_name,
                "symbol": row.get("symbol"),
                "delegateType": delegate_type,
                "orderId": order_id or None,
                "orderStatus": row.get("orderStatus"),
                "createdTime": row.get("createdTime"),
                "updatedTime": row.get("updatedTime"),
            })
    symbols = sorted({str(x.get("symbol")) for x in evidence if x.get("symbol")})
    return {
        "status": "DETECTED" if evidence else "NO_SIGNAL",
        "evidenceCount": len(evidence),
        "symbols": symbols,
        "evidence": evidence,
        "botIdAvailable": False,
        "semantic": "GRID_ORDER_ACTIVITY_ONLY_NO_BOTID",
    }


def parse_utc_epoch(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return int(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return None


def confirmation_fresh(value, ttl_sec, now_epoch):
    ts = parse_utc_epoch(value)
    if ts is None:
        return False, None
    age = max(0, int(now_epoch - ts))
    return age <= ttl_sec, age


def write_snapshot(snapshot: dict):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, OUT)
    os.chmod(OUT, 0o600)


def self_test():
    dummy = {"api_key": "x", "passphrase": "y"}
    if "/api/v3/position/current-position" not in ALLOWED_GET_PATHS:
        raise RuntimeError("positions endpoint missing from allowlist")
    try:
        auth_headers(dummy, "POST", "/api/v3/account/assets")
        raise RuntimeError("POST guard failed")
    except RuntimeError as e:
        if "non-GET" not in str(e):
            raise
    try:
        auth_headers(dummy, "GET", "/api/v3/trade/place-order")
        raise RuntimeError("write endpoint guard failed")
    except RuntimeError as e:
        if not ("Mutating endpoint rejected" in str(e) or "not allowlisted" in str(e)):
            raise
    forbidden_in_allowlist = [p for p in ALLOWED_GET_PATHS if any(m in p for m in FORBIDDEN_WRITE_MARKERS)]
    if forbidden_in_allowlist:
        raise RuntimeError(f"forbidden endpoint present in allowlist: {forbidden_in_allowlist}")
    synthetic = {"ok": True, "data": {"list": [
        {"orderId": "1", "symbol": "BGBUSDT", "delegateType": "strategy_grid_positive", "orderStatus": "live"},
        {"orderId": "2", "symbol": "ADAUSDT", "delegateType": "market", "orderStatus": "filled"},
    ]}}
    discovery = detect_grid_order_activity(synthetic, {"ok": True, "data": {"list": []}})
    if discovery.get("status") != "DETECTED" or discovery.get("symbols") != ["BGBUSDT"]:
        raise RuntimeError("grid discovery classifier self-test failed")
    if parse_utc_epoch("1970-01-01T00:00:00Z") != 0:
        raise RuntimeError("UTC parser self-test failed")
    qp = {"limit":"100","category":"SPOT","cursor":"abc+/="}
    cp = dict(sorted((str(k), str(v)) for k, v in qp.items() if v is not None and v != ""))
    tq = requests.Request("GET", BASE_URL + "/api/v3/trade/history-orders", params=cp).prepare().url.split("?",1)[1]
    if tq != urlencode(sorted(cp.items())):
        raise RuntimeError("query-order prepared/transmitted mismatch")
    print("PASS_QUERY_ORDER_CANONICAL_V0_4")
    print("PASS_GET_ONLY_GUARD_V0_4")
    print("PASS_GRID_ORDER_DISCOVERY_CLASSIFIER_V0_4")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    interval_sec = int(cfg.get("observerIntervalSec", 60))
    ttl_sec = int(cfg.get("privateStateTtlSec", 120))
    if interval_sec <= 0 or ttl_sec <= 0 or interval_sec >= ttl_sec:
        raise RuntimeError(f"Unsafe cadence: observerIntervalSec={interval_sec} must be < privateStateTtlSec={ttl_sec}")

    auth = load_local_auth()
    session = make_session(auth["proxy_url"])
    now_ms = int(time.time() * 1000)
    snapshot_id = f"gp26-{now_ms}"

    snapshot = {
        "schema": SCHEMA,
        "observerVersion": VERSION,
        "snapshotId": snapshot_id,
        "cycleId": snapshot_id,
        "accountTag": cfg.get("accountTag", "grid_pilot26"),
        "capturedAtEpochMs": now_ms,
        "capturedAtUtc": utc_now(),
        "mode": "READ_ONLY_GET_ONLY_PROXY_OPTIONAL",
        "source": "ANDROID_LOCAL_COLLECTOR",
        "timing": {
            "observerIntervalSec": interval_sec,
            "privateStateTtlSec": ttl_sec,
            "cadenceGate": "PASS",
        },
        "authHealth": {},
        "account": {},
        "trade": {},
        "positions": {},
        "gridBots": [],
        "gridDiscovery": {},
        "coverage": {},
        "health": {},
    }

    info = safe_call(lambda: sanitize_info(get_private(session, auth, "/api/v3/account/info")))
    snapshot["authHealth"] = info
    if info.get("ok"):
        d = info.get("data") or {}
        if str(d.get("permType", "")).lower() != "readonly":
            snapshot["authHealth"] = {"ok": False, "error": "API key is not readonly"}

    # Fail closed: if auth/proxy health fails, do not continue to account reads.
    if not snapshot["authHealth"].get("ok", False):
        snapshot["coverage"] = {
            "auth": "FAILED",
            "assets": "NOT_ATTEMPTED",
            "settings": "NOT_ATTEMPTED",
            "openSpotOrders": "NOT_ATTEMPTED",
            "recentSpotOrders": "NOT_ATTEMPTED",
            "recentSpotFills": "NOT_ATTEMPTED",
            "positions": "NOT_ATTEMPTED",
            "gridBotRegistry": {"status": "UNKNOWN", "configuredCount": 0, "coveredCount": 0},
        }
        snapshot["health"] = {"status": "RED", "failureCount": 1, "unknownCount": 1, "reasons": ["authHealth"]}
        write_snapshot(snapshot)
        log(f"snapshot_written={OUT} snapshotId={snapshot_id} health=RED failures=authHealth")
        return 2

    assets = safe_call(lambda: get_private(session, auth, "/api/v3/account/assets"))
    snapshot["account"]["assets"] = assets

    include_settings = bool(cfg.get("includeAccountSettings", True))
    settings = safe_call(lambda: get_private(session, auth, "/api/v3/account/settings")) if include_settings else None
    if include_settings:
        snapshot["account"]["settings"] = settings

    include_open_orders = bool(cfg.get("includeOpenSpotOrders", True))
    open_orders = safe_call(
        lambda: get_private(session, auth, "/api/v3/trade/unfilled-orders", {"category": "SPOT", "limit": "100"})
    ) if include_open_orders else None
    if include_open_orders:
        snapshot["trade"]["openSpotOrders"] = open_orders

    include_recent_orders = bool(cfg.get("includeRecentSpotOrders", True))
    recent_orders = safe_call(
        lambda: get_private(session, auth, "/api/v3/trade/history-orders", {"category": "SPOT", "limit": "100"})
    ) if include_recent_orders else None
    if include_recent_orders:
        snapshot["trade"]["recentSpotOrders"] = recent_orders

    include_recent_fills = bool(cfg.get("includeRecentSpotFills", True))
    recent_fills = safe_call(
        lambda: get_private(session, auth, "/api/v3/trade/fills", {"category": "SPOT", "limit": "100"})
    ) if include_recent_fills else None
    if include_recent_fills:
        snapshot["trade"]["recentSpotFills"] = recent_fills

    grid_discovery = detect_grid_order_activity(open_orders, recent_orders)
    snapshot["gridDiscovery"] = grid_discovery

    include_positions = bool(cfg.get("includePositions", True))
    position_categories = ["USDT-FUTURES", "USDC-FUTURES"]

    if include_positions and include_settings and isinstance(settings, dict) and settings.get("ok"):
        account_level = str((settings.get("data") or {}).get("accountLevel", "")).lower()
        if account_level == "pro":
            position_categories.append("COIN-FUTURES")

    positions = safe_call(
        lambda: {
            category: get_private(
                session,
                auth,
                "/api/v3/position/current-position",
                {"category": category}
            )
            for category in position_categories
        }
    ) if include_positions else None

    if include_positions:
        snapshot["positions"]["current"] = positions
        snapshot["positions"]["categoriesQueried"] = position_categories

    configured_bot_ids = []
    for raw in cfg.get("botIds", []):
        bot_id = str(raw).strip()
        if bot_id and bot_id not in configured_bot_ids:
            configured_bot_ids.append(bot_id)

    confirmed_empty_raw = bool(cfg.get("botRegistryConfirmedEmpty", False))
    confirmation_ttl_sec = int(cfg.get("botRegistryConfirmationTtlSec", ttl_sec))
    if confirmation_ttl_sec <= 0:
        raise RuntimeError("botRegistryConfirmationTtlSec must be positive")
    confirmation_is_fresh, confirmation_age_sec = confirmation_fresh(
        cfg.get("botRegistryConfirmedEmptyAtUtc"), confirmation_ttl_sec, time.time()
    )
    confirmed_empty = confirmed_empty_raw and confirmation_is_fresh

    discovery_detected = grid_discovery.get("status") == "DETECTED"
    registry_conflict = confirmed_empty and (bool(configured_bot_ids) or discovery_detected)

    covered_bot_ids = 0
    covered_symbols = set()
    bot_failures = []
    for bot_id in configured_bot_ids:
        item = {"botId": bot_id}
        item["detail"] = safe_call(lambda b=bot_id: get_private(session, auth, "/api/v3/trade/grid/bot-detail", {"botId": b}))
        item["orders"] = safe_call(lambda b=bot_id: get_private(session, auth, "/api/v3/trade/grid/list-details", {"botId": b}))
        if item["detail"].get("ok") and item["orders"].get("ok"):
            covered_bot_ids += 1
            detail_data = item["detail"].get("data")
            if isinstance(detail_data, dict) and detail_data.get("symbol"):
                covered_symbols.add(str(detail_data.get("symbol")))
        else:
            bot_failures.append(bot_id)
        snapshot["gridBots"].append(item)
        # list-details limit is 1/sec/UID.
        time.sleep(1.05)

    discovered_symbols = set(grid_discovery.get("symbols") or [])
    discovery_gap = discovery_detected and (
        not configured_bot_ids or not discovered_symbols.issubset(covered_symbols)
    )

    if registry_conflict:
        grid_coverage_status = "CONFLICT"
    elif discovery_gap:
        grid_coverage_status = "DISCOVERY_GAP_NO_BOTID"
    elif configured_bot_ids and covered_bot_ids == len(configured_bot_ids):
        grid_coverage_status = "COMPLETE_FOR_REGISTRY"
    elif configured_bot_ids:
        grid_coverage_status = "FAILED"
    elif confirmed_empty:
        grid_coverage_status = "CONFIRMED_EMPTY_BY_OWNER"
    else:
        grid_coverage_status = "UNKNOWN"

    snapshot["coverage"] = {
        "auth": "COMPLETE",
        "assets": call_coverage(assets),
        "settings": call_coverage(settings, include_settings),
        "openSpotOrders": call_coverage(open_orders, include_open_orders),
        "recentSpotOrders": call_coverage(recent_orders, include_recent_orders),
        "recentSpotFills": call_coverage(recent_fills, include_recent_fills),
        "positions": call_coverage(positions, include_positions),
        "gridBotRegistry": {
            "status": grid_coverage_status,
            "configuredCount": len(configured_bot_ids),
            "coveredCount": covered_bot_ids,
            "coveredSymbols": sorted(covered_symbols),
            "ownerConfirmedEmptyRaw": confirmed_empty_raw,
            "ownerConfirmedEmpty": confirmed_empty,
            "ownerConfirmedEmptyAtUtc": cfg.get("botRegistryConfirmedEmptyAtUtc"),
            "ownerConfirmationTtlSec": confirmation_ttl_sec,
            "ownerConfirmationAgeSec": confirmation_age_sec,
            "ownerConfirmationFresh": confirmation_is_fresh,
            "discoveryStatus": grid_discovery.get("status"),
            "discoveredSymbols": sorted(discovered_symbols),
            "semantic": (
                "ORDER_ACTIVITY_DETECTED_BOTID_UNRESOLVED"
                if grid_coverage_status == "DISCOVERY_GAP_NO_BOTID"
                else "EMPTY_REGISTRY_IS_UNKNOWN_NOT_ZERO"
            ),
        },
    }

    failures = []
    mandatory = {
        "assets": assets,
        "settings": settings if include_settings else {"ok": False},
        "openSpotOrders": open_orders if include_open_orders else {"ok": False},
        "recentSpotOrders": recent_orders if include_recent_orders else {"ok": False},
        "recentSpotFills": recent_fills if include_recent_fills else {"ok": False},
        "positions": positions if include_positions else {"ok": False},
    }
    for name, result in mandatory.items():
        if not isinstance(result, dict) or not result.get("ok", False):
            failures.append(name)
    for bot_id in bot_failures:
        failures.append(f"bot:{bot_id}")
    if grid_coverage_status == "CONFLICT":
        failures.append("gridBotRegistryConflict")

    unknowns = []
    if grid_coverage_status in ("UNKNOWN", "DISCOVERY_GAP_NO_BOTID"):
        unknowns.append("gridBotRegistry")

    # RED is intentional whenever authoritative private-state coverage is incomplete/unknown.
    health_status = "GREEN" if not failures and not unknowns else "RED"
    reasons = failures + unknowns
    snapshot["health"] = {
        "status": health_status,
        "failureCount": len(failures),
        "unknownCount": len(unknowns),
        "reasons": reasons,
    }

    write_snapshot(snapshot)
    log(
        f"snapshot_written={OUT} snapshotId={snapshot_id} health={health_status} "
        f"failures={','.join(failures) if failures else 'none'} unknowns={','.join(unknowns) if unknowns else 'none'}"
    )
    return 0 if health_status == "GREEN" else 2


if __name__ == "__main__":
    sys.exit(main())
