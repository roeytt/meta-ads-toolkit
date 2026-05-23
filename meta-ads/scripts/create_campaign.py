#!/usr/bin/env python3
"""Create a complete Meta ad campaign from a spec JSON.

Builds the full object tree in one shot:
  campaign -> ad sets -> creatives + ads

Why a script and not Ads Manager UI? Campaigns built from a spec are
reproducible, reviewable (dry-run), and rollback-able (every ID is
logged to a state file). Good for A/B testing flights, agency handoffs,
and any time you want the exact same structure twice.

Safety:
  - Refuses to write without either --dry-run or --confirm.
  - Defaults the created campaign, ad sets, and ads all to PAUSED so
    nothing delivers until you explicitly enable them in Ads Manager.
  - Every object created is recorded in the returned state JSON with
    its ID, so you can delete/pause everything if something went wrong.

Usage:
  python scripts/create_campaign.py --spec spec.json --dry-run
  python scripts/create_campaign.py --spec spec.json --confirm

See references/campaign-creation.md for the spec format.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meta_client import (
    GRAPH_BASE,
    MetaAPIError,
    get,
    get_token,
    get_version,
    normalize_account_id,
    post,
    print_json,
)

# Currencies with no minor unit (Meta returns/accepts whole-unit amounts).
# Source: ISO 4217 zero-decimal list, aligned with Meta's docs.
ZERO_DECIMAL = {"JPY", "KRW", "VND", "ISK", "TWD", "XAF", "XOF", "CLP"}

DEFAULT_PLACEMENTS = {
    "publisher_platforms": ["instagram"],
    "instagram_positions": ["stream", "story", "reels"],
}

VALID_CTAS = {
    "LEARN_MORE", "SIGN_UP", "SHOP_NOW", "BOOK_TRAVEL", "DOWNLOAD",
    "GET_OFFER", "GET_QUOTE", "SUBSCRIBE", "CONTACT_US", "APPLY_NOW",
    "WATCH_MORE", "INSTALL_MOBILE_APP", "USE_APP", "MESSAGE_PAGE",
    "WHATSAPP_MESSAGE", "NO_BUTTON",
}


# ─── Helpers ───────────────────────────────────────────────────────────────
def get_account_currency(account_id: str) -> str:
    """Fetch the account's currency so we can do major→minor conversion correctly."""
    resp = get(account_id, {"fields": "currency"})
    return resp.get("currency", "USD")


def major_to_minor(amount_major: float, currency: str) -> int:
    """Convert 50.00 ILS → 5000 agorot. 1000 JPY → 1000."""
    if currency.upper() in ZERO_DECIMAL:
        return int(round(amount_major))
    return int(round(amount_major * 100))


def resolve_interest_ids(interest_names: list[str]) -> list[dict]:
    """Resolve interest names → {id, name} dicts via Meta's ad interest search.

    Keeps the first match per name. Names with no match are dropped and
    surfaced to the caller as an issue.
    """
    out = []
    seen = set()
    missing = []
    for name in interest_names:
        resp = get("search", {"type": "adinterest", "q": name, "limit": 3})
        hits = resp.get("data", [])
        if not hits:
            missing.append(name)
            continue
        top = hits[0]
        tid = top.get("id")
        if tid and tid not in seen:
            out.append({"id": tid, "name": top.get("name")})
            seen.add(tid)
    if missing:
        print(f"[warn] No interest match for: {missing}", file=sys.stderr)
    return out


def upload_image(account_id: str, image_path: Path) -> str:
    """POST image bytes to /act_.../adimages. Returns the hash Meta assigns."""
    import requests

    url = f"{GRAPH_BASE}/{get_version()}/{account_id}/adimages"
    with image_path.open("rb") as f:
        files = {image_path.name: (image_path.name, f, "image/png")}
        data = {"access_token": get_token()}
        resp = requests.post(url, data=data, files=files, timeout=120)
    if not resp.ok:
        raise RuntimeError(f"Image upload failed ({resp.status_code}): {resp.text[:500]}")
    body = resp.json()
    info = body.get("images", {}).get(image_path.name)
    if not info or not info.get("hash"):
        raise RuntimeError(f"No hash in upload response: {body}")
    return info["hash"]


def is_carousel(ad_cfg: dict) -> bool:
    """True if the ad has carousel_cards (multi-card format)."""
    return bool(ad_cfg.get("carousel_cards"))


def is_dco(ad_cfg: dict) -> bool:
    """True if the ad has multiple messages or multiple headlines (Dynamic Creative)."""
    return (
        (isinstance(ad_cfg.get("messages"), list) and len(ad_cfg["messages"]) > 1)
        or (isinstance(ad_cfg.get("headlines"), list) and len(ad_cfg["headlines"]) > 1)
    )


def build_targeting(t: dict, resolved_interests: list[dict]) -> dict:
    out = {}

    # Geo
    geo = t.get("geo_locations")
    if not geo:
        countries = t.get("countries")
        if countries:
            geo = {"countries": countries}
    if geo:
        out["geo_locations"] = geo

    # Age/gender — with Advantage+ audience, age_max must be 65 (or omitted);
    # the value becomes a suggestion rather than a hard filter.
    # With Advantage+ audience, Meta enforces age_min ≤ 25 and age_max ≥ 65 as
    # hard limits; values outside those bounds are rejected. Skip them silently.
    advantage_on = t.get("advantage_audience", True)
    if "age_min" in t:
        age_min_val = int(t["age_min"])
        if not advantage_on or age_min_val <= 25:
            out["age_min"] = age_min_val
    if "age_max" in t:
        age_max_val = int(t["age_max"])
        if not advantage_on or age_max_val >= 65:
            out["age_max"] = age_max_val
    if "genders" in t:
        out["genders"] = t["genders"]

    # Interests + behaviors via flexible_spec. Each is a separate OR'd entry so
    # the audience matches (any listed interest) OR (any listed behavior).
    flexible_spec = []
    if resolved_interests:
        flexible_spec.append(
            {"interests": [{"id": i["id"], "name": i["name"]} for i in resolved_interests]}
        )
    behavior_ids = t.get("behavior_ids", [])
    if behavior_ids:
        flexible_spec.append({"behaviors": [{"id": bid} for bid in behavior_ids]})
    if flexible_spec:
        out["flexible_spec"] = flexible_spec

    # Placements: omit publisher_platforms entirely when advantage_placements=True
    # so Meta manages all placement decisions automatically.
    if not t.get("advantage_placements", False):
        out["publisher_platforms"] = t.get("publisher_platforms", DEFAULT_PLACEMENTS["publisher_platforms"])
        if "instagram" in out["publisher_platforms"]:
            out["instagram_positions"] = t.get(
                "instagram_positions", DEFAULT_PLACEMENTS["instagram_positions"]
            )
        if "facebook" in out["publisher_platforms"]:
            out["facebook_positions"] = t.get("facebook_positions", ["feed", "story", "video_feeds"])

    # Advantage+ audience expansion.
    # advantage_placements is achieved by omitting publisher_platforms (handled above).
    # The API rejects "advantage_placements" inside targeting_automation — don't send it.
    if t.get("advantage_audience", True):
        out["targeting_automation"] = {"advantage_audience": 1}

    # Custom audiences + excluded audiences (optional)
    if "custom_audiences" in t:
        out["custom_audiences"] = t["custom_audiences"]
    if "excluded_custom_audiences" in t:
        out["excluded_custom_audiences"] = t["excluded_custom_audiences"]

    return out


# ─── Validation ────────────────────────────────────────────────────────────
def validate_spec(spec: dict) -> list[str]:
    """Return a list of human-readable errors. Empty list = valid."""
    errs = []
    if not spec.get("campaign_name"):
        errs.append("campaign_name is required")
    if not spec.get("objective"):
        errs.append("objective is required (e.g. OUTCOME_TRAFFIC, OUTCOME_SALES, OUTCOME_ENGAGEMENT)")
    if not spec.get("landing_url") and spec.get("objective", "").startswith("OUTCOME_TRAFFIC"):
        errs.append("landing_url is required for traffic campaigns")
    identity = spec.get("identity", {})
    if not identity.get("page_id"):
        errs.append("identity.page_id is required")
    if not spec.get("ad_sets"):
        errs.append("at least one ad_set is required")

    for i, a in enumerate(spec.get("ad_sets", [])):
        prefix = f"ad_sets[{i}]"
        if not a.get("name"):
            errs.append(f"{prefix}.name is required")
        if "daily_budget" not in a and "lifetime_budget" not in a:
            errs.append(f"{prefix} needs daily_budget or lifetime_budget (in major units)")
        if not a.get("ads"):
            errs.append(f"{prefix}.ads must have at least one ad")
        # Image required at adset level unless every ad supplies its own image_path
        ads_all_have_image = all(ad.get("image_path") for ad in a.get("ads", []))
        if not a.get("image_hash") and not a.get("image_path") and not ads_all_have_image:
            errs.append(f"{prefix} needs either image_path / image_hash at adset level, or image_path on every ad")
        if a.get("image_path"):
            p = Path(a["image_path"]).expanduser()
            if not p.is_absolute():
                p = (Path.cwd() / p).resolve()
            if not p.exists():
                errs.append(f"{prefix}.image_path does not exist: {p}")
        for j, ad in enumerate(a.get("ads", [])):
            ap = f"{prefix}.ads[{j}]"
            if not ad.get("name"):
                errs.append(f"{ap}.name is required")
            if is_carousel(ad):
                cards = ad.get("carousel_cards", [])
                if len(cards) < 2:
                    errs.append(f"{ap}.carousel_cards must have at least 2 cards")
                for k, card in enumerate(cards):
                    cp = f"{ap}.carousel_cards[{k}]"
                    if not card.get("image_path"):
                        errs.append(f"{cp}.image_path is required")
                    if not card.get("headline"):
                        errs.append(f"{cp}.headline is required")
                    if card.get("image_path"):
                        p = Path(card["image_path"]).expanduser()
                        if not p.is_absolute():
                            p = (Path.cwd() / p).resolve()
                        if not p.exists():
                            errs.append(f"{cp}.image_path does not exist: {p}")
            else:
                has_message = ad.get("message") or (isinstance(ad.get("messages"), list) and ad["messages"])
                has_headline = ad.get("headline") or (isinstance(ad.get("headlines"), list) and ad["headlines"])
                if not has_message:
                    errs.append(f"{ap}.message (or messages) is required")
                if not has_headline:
                    errs.append(f"{ap}.headline (or headlines) is required")
            cta = ad.get("cta", "LEARN_MORE")
            if cta not in VALID_CTAS:
                errs.append(f"{ap}.cta '{cta}' is not a recognized CTA type")
            if ad.get("image_path"):
                p = Path(ad["image_path"]).expanduser()
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                if not p.exists():
                    errs.append(f"{ap}.image_path does not exist: {p}")
            if ad.get("secondary_image_path"):
                p = Path(ad["secondary_image_path"]).expanduser()
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                if not p.exists():
                    errs.append(f"{ap}.secondary_image_path does not exist: {p}")
    return errs


def _plan_ad(ad: dict, default_url: str | None) -> dict:
    """Summarise a single ad for the dry-run plan output."""
    if is_carousel(ad):
        return {
            "name": ad["name"],
            "creative_format": "CAROUSEL",
            "message_preview": (ad.get("message") or "")[:100],
            "cta": ad.get("cta", "LEARN_MORE"),
            "cards": [
                {
                    "headline": c["headline"],
                    "image": c["image_path"],
                    "url": c.get("url") or default_url,
                    "description": c.get("description"),
                }
                for c in ad.get("carousel_cards", [])
            ],
        }
    messages = ad.get("messages") or [ad.get("message", "")]
    headlines = ad.get("headlines") or [ad.get("headline", "")]
    fmt = "DCO (asset_feed_spec)" if (len(messages) > 1 or len(headlines) > 1) else "SINGLE_IMAGE (object_story_spec)"
    if ad.get("secondary_image_path"):
        fmt = "TWO_IMAGE (asset_feed_spec)"
    return {
        "name": ad["name"],
        "creative_format": fmt,
        "headlines": headlines,
        "message_previews": [m.split("\n", 1)[0][:100] + " …" for m in messages],
        "cta": ad.get("cta", "LEARN_MORE"),
        "image": ad.get("image_path") or "<adset_image>",
        "image_9x16": ad.get("secondary_image_path") or None,
        "url": ad.get("url") or default_url,
    }


# ─── Planning (dry-run) ────────────────────────────────────────────────────
def plan(spec: dict, account_id: str) -> dict:
    currency = get_account_currency(account_id)
    out = {
        "account_id": account_id,
        "currency": currency,
        "campaign": {
            "name": spec["campaign_name"],
            "objective": spec["objective"],
            "status": spec.get("status", "PAUSED"),
            "special_ad_categories": spec.get("special_ad_categories", []),
        },
        "identity": spec["identity"],
        "landing_url": spec.get("landing_url"),
        "ad_sets": [],
    }
    total_daily_minor = 0
    total_ads = 0
    for a in spec["ad_sets"]:
        targeting = a.get("targeting", {})

        # Resolve interests now so the dry-run tells the user the real IDs
        interests = []
        if targeting.get("interest_ids"):
            interests = [{"id": i, "name": f"<preset:{i}>"} for i in targeting["interest_ids"]]
        elif targeting.get("interests"):
            interests = resolve_interest_ids(targeting["interests"])

        daily_minor = None
        if "daily_budget" in a:
            daily_minor = major_to_minor(a["daily_budget"], currency)
            total_daily_minor += daily_minor

        out["ad_sets"].append(
            {
                "name": a["name"],
                "daily_budget_major": a.get("daily_budget"),
                "daily_budget_minor": daily_minor,
                "lifetime_budget_major": a.get("lifetime_budget"),
                "billing_event": a.get("billing_event", "LINK_CLICKS"),
                "optimization_goal": a.get("optimization_goal", "LINK_CLICKS"),
                "targeting_summary": {
                    "countries": targeting.get("geo_locations", {}).get("countries")
                    or targeting.get("countries"),
                    "age_range": [targeting.get("age_min"), targeting.get("age_max")],
                    "resolved_interests": interests,
                    "placements": targeting.get(
                        "publisher_platforms", DEFAULT_PLACEMENTS["publisher_platforms"]
                    ),
                },
                "image": a.get("image_path") or f"<prehashed:{a.get('image_hash')}>",
                "ads": [_plan_ad(ad, spec.get("landing_url")) for ad in a["ads"]],
            }
        )
        total_ads += len(a["ads"])

    out["totals"] = {
        "ad_sets": len(spec["ad_sets"]),
        "ads": total_ads,
        "total_daily_budget_minor": total_daily_minor,
        "total_daily_budget_major": total_daily_minor / (1 if currency.upper() in ZERO_DECIMAL else 100),
    }
    return out


# ─── Execution (write) ─────────────────────────────────────────────────────
def execute(spec: dict, account_id: str) -> dict:
    currency = get_account_currency(account_id)
    state: dict = {
        "ok": True,
        "account_id": account_id,
        "currency": currency,
        "created_at": int(time.time()),
        "objects": [],
    }

    # 1. Campaign
    # is_adset_budget_sharing_enabled: False = per-adset budgets (no CBO)
    # True = Campaign Budget Optimization. Default False unless spec says otherwise.
    use_cbo = spec.get("campaign_budget_optimization", False)
    camp_data = {
        "name": spec["campaign_name"],
        "objective": spec["objective"],
        "status": spec.get("status", "PAUSED"),
        "special_ad_categories": json.dumps(spec.get("special_ad_categories", [])),
        "buying_type": spec.get("buying_type", "AUCTION"),
        "is_adset_budget_sharing_enabled": "true" if use_cbo else "false",
    }
    camp = post(f"{account_id}/campaigns", data=camp_data)
    campaign_id = camp["id"]
    state["campaign_id"] = campaign_id
    state["objects"].append({"type": "campaign", "id": campaign_id, "name": spec["campaign_name"]})
    print(f"[+] campaign: {campaign_id} — {spec['campaign_name']}", file=sys.stderr)

    page_id = spec["identity"]["page_id"]
    ig_user_id = spec["identity"].get("instagram_user_id")
    landing_url = spec.get("landing_url")

    out_ad_sets = []
    for a in spec["ad_sets"]:
        targeting_cfg = a.get("targeting", {})

        # Resolve interests
        if targeting_cfg.get("interest_ids"):
            interests = [{"id": i, "name": f"preset-{i}"} for i in targeting_cfg["interest_ids"]]
        elif targeting_cfg.get("interests"):
            interests = resolve_interest_ids(targeting_cfg["interests"])
        else:
            interests = []

        targeting = build_targeting(targeting_cfg, interests)

        # Image (adset-level; may be None if every ad supplies its own image_path)
        if a.get("image_hash"):
            image_hash = a["image_hash"]
        elif a.get("image_path"):
            img_path = Path(a["image_path"]).expanduser()
            if not img_path.is_absolute():
                img_path = (Path.cwd() / img_path).resolve()
            image_hash = upload_image(account_id, img_path)
            state["objects"].append(
                {"type": "image", "hash": image_hash, "file": img_path.name}
            )
            print(f"[+] image: {img_path.name} -> {image_hash[:16]}…", file=sys.stderr)
        else:
            image_hash = None  # per-ad images will be uploaded inside the ads loop

        # Ad set
        adset_data = {
            "name": a["name"],
            "campaign_id": campaign_id,
            "billing_event": a.get("billing_event", "LINK_CLICKS"),
            "optimization_goal": a.get("optimization_goal", "LINK_CLICKS"),
            "bid_strategy": a.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            "targeting": json.dumps(targeting),
            "status": a.get("status", "PAUSED"),
            "start_time": str(int(time.time()) + 3600),
        }
        if "daily_budget" in a:
            adset_data["daily_budget"] = str(major_to_minor(a["daily_budget"], currency))
        if "lifetime_budget" in a:
            adset_data["lifetime_budget"] = str(major_to_minor(a["lifetime_budget"], currency))
            adset_data["end_time"] = a["end_time"]
        if "bid_amount" in a:
            adset_data["bid_amount"] = str(major_to_minor(a["bid_amount"], currency))
        if "promoted_object" in a:
            adset_data["promoted_object"] = json.dumps(a["promoted_object"])

        adset = post(f"{account_id}/adsets", data=adset_data)
        adset_id = adset["id"]
        state["objects"].append({"type": "adset", "id": adset_id, "name": a["name"]})
        print(f"[+] ad set: {adset_id} — {a['name']}", file=sys.stderr)

        ads_created = []
        for ad_cfg in a["ads"]:
            ad_url = ad_cfg.get("url") or landing_url
            ad_cta = ad_cfg.get("cta", "LEARN_MORE")
            creative_name = f"Creative_{ad_cfg['name']}"

            # ── CAROUSEL ──────────────────────────────────────────────────
            if is_carousel(ad_cfg):
                child_attachments = []
                for card in ad_cfg["carousel_cards"]:
                    card_img_path = Path(card["image_path"]).expanduser()
                    if not card_img_path.is_absolute():
                        card_img_path = (Path.cwd() / card_img_path).resolve()
                    card_hash = upload_image(account_id, card_img_path)
                    state["objects"].append({"type": "image", "hash": card_hash, "file": card_img_path.name})
                    print(f"[+] carousel image: {card_img_path.name} -> {card_hash[:16]}…", file=sys.stderr)
                    card_url = card.get("url") or ad_url
                    attachment: dict = {
                        "link": card_url,
                        "image_hash": card_hash,
                        "name": card["headline"],
                        "call_to_action": {"type": ad_cta, "value": {"link": card_url}},
                    }
                    if card.get("description"):
                        attachment["description"] = card["description"]
                    child_attachments.append(attachment)

                carousel_spec: dict = {
                    "page_id": page_id,
                    "link_data": {
                        "link": ad_url,
                        "message": ad_cfg.get("message", ""),
                        "call_to_action": {"type": ad_cta, "value": {"link": ad_url}},
                        "child_attachments": child_attachments,
                        "multi_share_end_card": ad_cfg.get("multi_share_end_card", False),
                        "multi_share_optimized": ad_cfg.get("multi_share_optimized", True),
                    },
                }
                if ig_user_id:
                    carousel_spec["instagram_user_id"] = ig_user_id
                creative = post(
                    f"{account_id}/adcreatives",
                    data={"name": creative_name, "object_story_spec": json.dumps(carousel_spec)},
                )

            # ── DCO / MULTI-IMAGE (asset_feed_spec) ───────────────────────
            else:
                # Per-ad primary image
                if ad_cfg.get("image_path"):
                    per_ad_img_path = Path(ad_cfg["image_path"]).expanduser()
                    if not per_ad_img_path.is_absolute():
                        per_ad_img_path = (Path.cwd() / per_ad_img_path).resolve()
                    ad_image_hash = upload_image(account_id, per_ad_img_path)
                    state["objects"].append({"type": "image", "hash": ad_image_hash, "file": per_ad_img_path.name})
                    print(f"[+] image: {per_ad_img_path.name} -> {ad_image_hash[:16]}…", file=sys.stderr)
                else:
                    ad_image_hash = image_hash

                # Per-ad secondary image (9:16 for Stories/Reels)
                secondary_image_hash = None
                if ad_cfg.get("secondary_image_path"):
                    sec_img_path = Path(ad_cfg["secondary_image_path"]).expanduser()
                    if not sec_img_path.is_absolute():
                        sec_img_path = (Path.cwd() / sec_img_path).resolve()
                    secondary_image_hash = upload_image(account_id, sec_img_path)
                    state["objects"].append({"type": "image", "hash": secondary_image_hash, "file": sec_img_path.name})
                    print(f"[+] image (secondary): {sec_img_path.name} -> {secondary_image_hash[:16]}…", file=sys.stderr)

                messages = ad_cfg.get("messages") or [ad_cfg.get("message", "")]
                headlines = ad_cfg.get("headlines") or [ad_cfg.get("headline", "")]
                use_feed_spec = secondary_image_hash or len(messages) > 1 or len(headlines) > 1

                def _build_object_story_spec_payload(name: str) -> dict:
                    creative_spec = {
                        "page_id": page_id,
                        "link_data": {
                            "link": ad_url,
                            "message": messages[0],
                            "name": headlines[0],
                            "image_hash": ad_image_hash,
                            "call_to_action": {"type": ad_cta, "value": {"link": ad_url}},
                        },
                    }
                    if ad_cfg.get("description"):
                        creative_spec["link_data"]["description"] = ad_cfg["description"]
                    if ig_user_id:
                        creative_spec["instagram_user_id"] = ig_user_id
                    return {"name": name, "object_story_spec": json.dumps(creative_spec)}

                if use_feed_spec:
                    images_list = [{"hash": ad_image_hash}]
                    if secondary_image_hash:
                        images_list.append({"hash": secondary_image_hash})
                    feed_spec: dict = {
                        "images": images_list,
                        "bodies": [{"text": m} for m in messages],
                        "titles": [{"text": h} for h in headlines],
                        "link_urls": [{"website_url": ad_url, "display_url": ad_url}],
                        "call_to_action_types": [ad_cta],
                        "ad_formats": ["SINGLE_IMAGE"],
                    }
                    if ad_cfg.get("description"):
                        feed_spec["descriptions"] = [{"text": ad_cfg["description"]}]
                    asset_payload: dict = {
                        "name": creative_name,
                        "page_id": page_id,
                        "asset_feed_spec": json.dumps(feed_spec),
                    }
                    if ig_user_id:
                        asset_payload["instagram_user_id"] = ig_user_id
                    try:
                        creative = post(f"{account_id}/adcreatives", data=asset_payload)
                    except MetaAPIError as e:
                        if e.body.get("error", {}).get("code") == 3:
                            print(
                                f"[warn] asset_feed_spec not permitted — falling back to "
                                f"object_story_spec for {ad_cfg['name']}. "
                                f"Grant the app dynamic-creative capability in Meta Business Manager.",
                                file=sys.stderr,
                            )
                            creative = post(
                                f"{account_id}/adcreatives",
                                data=_build_object_story_spec_payload(creative_name),
                            )
                        else:
                            raise
                else:
                    creative = post(
                        f"{account_id}/adcreatives",
                        data=_build_object_story_spec_payload(creative_name),
                    )

            creative_id = creative["id"]
            state["objects"].append(
                {"type": "creative", "id": creative_id, "name": creative_name}
            )

            ad = post(
                f"{account_id}/ads",
                data={
                    "name": f"Ad_{ad_cfg['name']}",
                    "adset_id": adset_id,
                    "creative": json.dumps({"creative_id": creative_id}),
                    "status": ad_cfg.get("status", "PAUSED"),
                },
            )
            ad_id = ad["id"]
            state["objects"].append({"type": "ad", "id": ad_id, "name": f"Ad_{ad_cfg['name']}"})
            ads_created.append({"ad_id": ad_id, "creative_id": creative_id, "name": ad_cfg["name"]})
            print(f"[+] ad: {ad_id} — {ad_cfg['name']}", file=sys.stderr)

        out_ad_sets.append(
            {"adset_id": adset_id, "image_hash": image_hash, "ads": ads_created}
        )

    state["ad_sets"] = out_ad_sets
    return state


# ─── Entry point ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Create a Meta ad campaign from a spec JSON",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--spec", required=True, help="Path to campaign spec JSON")
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true", help="Plan only, no writes")
    grp.add_argument("--confirm", action="store_true", help="Actually create everything")
    parser.add_argument("--account-id", default=None, help="Override META_AD_ACCOUNT_ID")
    parser.add_argument(
        "--state-out",
        default=None,
        help="Where to write the state JSON (default: alongside spec with _state suffix)",
    )
    args = parser.parse_args()

    spec_path = Path(args.spec).expanduser().resolve()
    if not spec_path.exists():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        sys.exit(2)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    errs = validate_spec(spec)
    if errs:
        print("Spec validation failed:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)

    account_id = normalize_account_id(args.account_id)

    if args.dry_run:
        try:
            p = plan(spec, account_id)
        except MetaAPIError as e:
            print_json({"ok": False, "error": str(e), "body": e.body})
            sys.exit(1)
        print_json(p)
        return

    # --confirm path
    state_file = Path(args.state_out) if args.state_out else spec_path.with_name(
        f"{spec_path.stem}_state_{int(time.time())}.json"
    )
    try:
        state = execute(spec, account_id)
    except MetaAPIError as e:
        state = {"ok": False, "error": f"{type(e).__name__}: {e}", "api_error_body": e.body}
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print_json(state)
        raise
    except Exception as e:
        state = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print_json(state)
        raise
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[state] -> {state_file}", file=sys.stderr)
    print_json(state)


if __name__ == "__main__":
    main()
