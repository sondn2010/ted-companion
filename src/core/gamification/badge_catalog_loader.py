"""Đọc + kiểm tra `assets/badges/badge_catalog.json` (catalog huy hiệu dạng dữ liệu).

Module thuần Python (không Qt): dùng chung cho app (phase 04 evaluator) và scripts/generate_badge_images.py.
Entry sai (metric/op/window/tier lạ, thiếu field) bị bỏ qua + log, trừ khi `strict=True` (dùng trong test/script).
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ted")

BADGES_DIR = Path(__file__).resolve().parents[3] / "assets" / "badges"
CATALOG_PATH = BADGES_DIR / "badge_catalog.json"

WINDOWS = ("day", "week", "lifetime")
OPS = (">=", "<=")
TIERS = ("bronze", "silver", "gold", "special")
# Metric hợp lệ v1 (khớp registry ở badge_metric_calculators, phase 04) + prev_week_xp cho guard của week_growth
KNOWN_METRICS = frozenset({
    "focus_minutes", "focus_sessions", "clean_sessions", "tasks_done", "quiz_answered", "quiz_correct",
    "quiz_accuracy_pct", "agenda_done", "writing_graded", "study_days", "active_days", "best_streak_days",
    "outings", "breaks_taken", "meeting_minutes", "away_minutes", "energy", "health", "health_avg",
    "screen_load_avg", "engagement_avg", "energy_avg", "peak_level", "comeback", "xp_total",
    "xp_growth_pct", "level_growth", "prev_week_xp", "meetings_done", "teacher_sessions",
})


class CatalogError(ValueError):
    """Catalog sai định dạng."""


@dataclass(frozen=True)
class BadgeGuard:
    """Điều kiện phụ: metric >= value (vd quiz_answered >= 20 cho rule độ chính xác)."""
    metric: str
    value: float


@dataclass(frozen=True)
class BadgeRule:
    metric: str
    window: str  # day | week | lifetime
    op: str  # >= | <=
    value: float
    min: Optional[BadgeGuard] = None


@dataclass(frozen=True)
class BadgeDef:
    id: str
    category: str
    tier: str
    name: dict  # {"vi","en"}
    desc: dict  # {"vi","en"}
    rule: BadgeRule
    image: str
    prompt: str  # chủ thể ảnh (dùng khi sinh ảnh)

    def image_path(self) -> Path:
        return BADGES_DIR / self.image


@dataclass(frozen=True)
class BadgeCatalog:
    style_prefix: str
    tier_phrases: dict
    locked_image: str
    badges: tuple


def _parse_guard(raw) -> Optional[BadgeGuard]:
    if not raw:
        return None
    if raw["metric"] not in KNOWN_METRICS:
        raise CatalogError(f"guard metric lạ: {raw['metric']}")
    return BadgeGuard(raw["metric"], float(raw["value"]))


def _parse_badge(raw: dict) -> BadgeDef:
    try:
        r = raw["rule"]
        if r["metric"] not in KNOWN_METRICS:
            raise CatalogError(f"metric lạ: {r['metric']}")
        if r["window"] not in WINDOWS:
            raise CatalogError(f"window lạ: {r['window']}")
        if r["op"] not in OPS:
            raise CatalogError(f"op lạ: {r['op']}")
        if raw["tier"] not in TIERS:
            raise CatalogError(f"tier lạ: {raw['tier']}")
        for key in ("name", "desc"):
            if not raw[key].get("vi") or not raw[key].get("en"):
                raise CatalogError(f"thiếu {key}.vi/en")
        rule = BadgeRule(r["metric"], r["window"], r["op"], float(r["value"]), _parse_guard(r.get("min")))
        return BadgeDef(raw["id"], raw["category"], raw["tier"], dict(raw["name"]), dict(raw["desc"]),
                        rule, raw["image"], raw["prompt"])
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise CatalogError(f"badge '{raw.get('id', '?')}' sai: {exc!r}") from exc


def load_badge_catalog(path: Path = CATALOG_PATH, strict: bool = False) -> BadgeCatalog:
    """Đọc catalog. strict=False: entry hỏng/trùng id bị bỏ qua + log; strict=True: raise CatalogError."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        prefix = data["style_prefix"]
        tiers = data["tier_phrases"]
        raw_badges = data["badges"]
    except (OSError, ValueError, KeyError) as exc:
        raise CatalogError(f"không đọc được catalog {path}: {exc!r}") from exc
    if "{TIER}" not in prefix or set(tiers) != set(TIERS):
        raise CatalogError("style_prefix cần {TIER} và tier_phrases đủ 4 tier")
    badges, seen = [], set()
    for raw in raw_badges:
        try:
            badge = _parse_badge(raw)
            if badge.id in seen:
                raise CatalogError(f"trùng id: {badge.id}")
        except CatalogError:
            if strict:
                raise
            logger.warning("Bỏ qua badge sai trong catalog", exc_info=True)
            continue
        seen.add(badge.id)
        badges.append(badge)
    return BadgeCatalog(prefix, dict(tiers), data.get("locked_image", "_locked.png"), tuple(badges))
