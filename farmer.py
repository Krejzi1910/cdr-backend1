"""
Background farmer for Color Dice Rigged. v1.1

v1.1 changes:
  - Uses curl_cffi (Chrome TLS impersonation) to bypass Cloudflare bot detection
  - Falls back to httpx if curl_cffi unavailable
  - Logs 403 response body for diagnosis
  - Adds realistic browser headers (Sec-Fetch-*, Referer, Accept-Encoding)
"""

import asyncio
import re
import random
import time
import logging
from typing import Optional, List

log = logging.getLogger("cdr.farmer")

# Try curl_cffi first (better Cloudflare bypass via TLS fingerprint)
try:
    from curl_cffi.requests import AsyncSession as _CurlSession
    HAS_CURL_CFFI = True
    log.info("Using curl_cffi (Chrome 120 TLS impersonation)")
except ImportError:
    import httpx
    HAS_CURL_CFFI = False
    log.warning("curl_cffi not available, falling back to httpx")

ROLL_BASE = "https://www.online-dice.com/roll-color-dice/"
SITE_HOME = "https://www.online-dice.com/"
SITE_TO_NAME = {
    "blue": "Blue", "green": "Green", "red": "Red",
    "purple": "Purple", "darkorange": "Orange", "gold": "Yellow"
}
DICE_RE = re.compile(r"color:([a-z]+)!important;['\"]\s+class=['\"]df-solid-small-dot-d6-1")
RESULT_ID_RE = re.compile(r"Result ID:\s*<span[^>]*>([^<]+)</span>", re.IGNORECASE)

TIERS = [
    (2,  800,  1500),
    (1, 2000,  3500),
    (1, 8000, 15000),
]
COOLDOWNS_SEC = [60, 300, 1800]
RECOVERY_QUIET_SEC = 300

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def parse_roll(html: str) -> dict:
    region = html
    t = html.find('id="tabletop"')
    if t >= 0:
        r = html.find("Result ID", t)
        region = html[t:r if r >= 0 else t + 6000]
    colors = []
    for m in DICE_RE.finditer(region):
        name = SITE_TO_NAME.get(m.group(1))
        if name:
            colors.append(name)
    token = None
    tm = RESULT_ID_RE.search(html)
    if tm:
        token = tm.group(1).strip()
    return {"token": token, "count": len(colors), "colors": colors}


def detect_block(status: int, body: str) -> Optional[str]:
    if status in (429, 403, 503) or 520 <= status <= 525:
        return f"http_{status}"
    snippet = (body or "")[:4096].lower()
    if "error 1015" in snippet or "rate limited" in snippet:
        return "cf_1015"
    if "just a moment" in snippet or "challenge-platform" in snippet:
        return "cf_challenge"
    if "attention required" in snippet and "cloudflare" in snippet:
        return "cf_block"
    return None


class Farmer:
    def __init__(self, db, dice_rotation: List[int]):
        self.db = db
        self.dice_rotation = dice_rotation
        self._stop = False
        self.tier = 0
        self.cooldown_until = 0
        self.last_block_ts = 0
        self._rolls_in_last_60s = []
        self._block_body_logged = False
        self._init_client()

    def _init_client(self):
        if HAS_CURL_CFFI:
            self.client = _CurlSession(
                impersonate="chrome120",
                timeout=20,
            )
            self._is_curl = True
        else:
            self.client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0),
                http2=True,
                follow_redirects=True,
            )
            self._is_curl = False

    def stop(self):
        self._stop = True

    def _enter_cooldown(self, reason: str):
        now = time.time()
        if self.cooldown_until > now:
            return
        step = min(self.tier, len(COOLDOWNS_SEC) - 1)
        wait = COOLDOWNS_SEC[step]
        self.cooldown_until = now + wait
        self.last_block_ts = now
        self.tier = min(self.tier + 1, len(TIERS) - 1)
        log.warning("Cooldown %ss (tier=%d, reason=%s)", wait, self.tier, reason)

    def _maybe_recover(self):
        now = time.time()
        if self.cooldown_until and now >= self.cooldown_until:
            self.cooldown_until = 0
        if self.last_block_ts and (now - self.last_block_ts) > RECOVERY_QUIET_SEC:
            if self.tier > 0:
                self.tier -= 1
                log.info("Recovered to tier=%d", self.tier)
                self.last_block_ts = now if self.tier > 0 else 0

    def _current_tier_params(self):
        return TIERS[min(self.tier, len(TIERS) - 1)]

    def current_rate(self) -> float:
        now = time.time()
        self._rolls_in_last_60s = [t for t in self._rolls_in_last_60s if now - t < 60]
        return round(len(self._rolls_in_last_60s) / 60.0, 3)

    def _headers(self, ua: str, referer: str) -> dict:
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer,
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    async def fetch_roll(self, count: int) -> dict:
        url = f"{ROLL_BASE}{count}/?h=pv"
        ua = random.choice(USER_AGENTS)
        headers = self._headers(ua, referer=SITE_HOME)
        try:
            if self._is_curl:
                r = await self.client.get(url, headers=headers, allow_redirects=True)
                status = r.status_code
                body = r.text
            else:
                r = await self.client.get(url, headers=headers)
                status = r.status_code
                body = r.text

            reason = detect_block(status, body)
            if reason:
                # log first block body once for diagnostics
                if not self._block_body_logged:
                    snippet = (body or "")[:500].replace("\n", " ")
                    log.warning("BLOCK_BODY (status=%d): %s", status, snippet)
                    self._block_body_logged = True
                self._enter_cooldown(reason)
                return {"ok": False, "reason": reason, "status": status}

            parsed = parse_roll(body)
            if not parsed["token"] or parsed["count"] != count:
                return {"ok": False, "reason": "parse_fail"}
            self._rolls_in_last_60s.append(time.time())
            self._block_body_logged = False  # reset on success
            return {"ok": True, **parsed}
        except Exception as e:
            return {"ok": False, "reason": f"http_err:{type(e).__name__}:{str(e)[:100]}"}

    async def run_forever(self):
        log.info("Farmer started (rotation=%s, impl=%s)", self.dice_rotation,
                 "curl_cffi" if self._is_curl else "httpx")
        rotation_idx = 0
        try:
            while not self._stop:
                self._maybe_recover()
                if self.cooldown_until > time.time():
                    await asyncio.sleep(min(5, self.cooldown_until - time.time()))
                    continue

                concurrency, dmin, dmax = self._current_tier_params()
                tasks = []
                for _ in range(concurrency):
                    count = self.dice_rotation[rotation_idx % len(self.dice_rotation)]
                    rotation_idx += 1
                    tasks.append(asyncio.create_task(self._one_roll(count)))
                await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(random.uniform(dmin / 1000.0, dmax / 1000.0))
        except asyncio.CancelledError:
            log.info("Farmer cancelled")
            raise
        finally:
            try:
                if self._is_curl:
                    await self.client.close()
                else:
                    await self.client.aclose()
            except Exception:
                pass

    async def _one_roll(self, count: int):
        r = await self.fetch_roll(count)
        if r.get("ok"):
            combo = f"{r['count']}|{','.join(r['colors'])}"
            self.db.insert_roll(r["token"], combo, r["count"], r["colors"])

    async def burst_find(self, combo_key: str, count: int, colors: List[str],
                         max_rolls: int = 80, timeout_sec: int = 15) -> Optional[str]:
        end_ts = time.time() + timeout_sec
        rolls = 0
        while time.time() < end_ts and rolls < max_rolls and not self._stop:
            self._maybe_recover()
            if self.cooldown_until > time.time():
                return None
            r = await self.fetch_roll(count)
            rolls += 1
            if r.get("ok"):
                rc = f"{r['count']}|{','.join(r['colors'])}"
                self.db.insert_roll(r["token"], rc, r["count"], r["colors"])
                if rc == combo_key:
                    return r["token"]
            _, dmin, dmax = self._current_tier_params()
            await asyncio.sleep(random.uniform(max(0.2, dmin / 2000.0), max(0.4, dmax / 2000.0)))
        return None
