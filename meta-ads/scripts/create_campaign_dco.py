#!/usr/bin/env python3
"""Create a Meta campaign with Dynamic Creative (multi-body, multi-headline).

Extends the single-creative pattern from create_campaign.py to support
asset_feed_spec with arrays of bodies + titles per ad. Meta auto-tests
the body+headline combinations and surfaces the best performer.

Differences from create_campaign.py:
  * Ad spec accepts `messages: [str, ...]` (1-5) and `headlines: [str, ...]` (1-5)
    instead of (or in addition to) singular `message`/`headline`.
  * Asset_feed_spec is used whenever messages>1 OR headlines>1.
  * Age constraints are respected as audience controls even when
    advantage_audience is enabled (matches Meta's current API behavior).
  * Otherwise the spec format and safety semantics are identical
    — read references/write-actions.md before --confirm.

Usage:
  python scripts/create_campaign_dco.py --spec spec.json --account-id act_X --dry-run
  python scripts/create_campaign_dco.py --spec spec.json --account-id act_X --confirm
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from meta_client import MetaAPIError, normalize_account_id, post, print_json
from create_campaign import (
    DEFAULT_PLACEMENTS,
    VALID_CTAS,
    ZERO_DECIMAL,
    get_account_currency,
    major_to_minor,
    resolve_interest_ids,
    upload_image,
)


# ─── Targeting (audience-controls-aware) ───────────────────────────────────
def build_targeting_strict_age(t: dict, resolved_interests: list[dict]) -> dict:
    """Like create_campaign.build_targeting but keeps age controls
    even with advantage_audience=true (Meta's current API supports
    age 18-65 as hard audience controls alongside Advantage+ Audience)."""
    out: dict = {}

    geo = t.get("geo_locations")
    if not geo:
        countries = t.get("countries")
        if countries:
            geo = {"countries": countries}
    if geo:
        out["geo_locations"] = geo

    if "age_min" in t:
        out["age_min"] = int(t["age_min"])
    if "age_max" in t:
        out["age_max"] = int(t["age_max"])
    if "genders" in t:
        out["genders"] = t["genders"]

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

    if not t.get("advantage_placements", False):
        out["publisher_platforms"] = t.get(
            "publisher_platforms", DEFAULT_PLACEMENTS["publisher_platforms"]
        )
        if "instagram" in out["publisher_platforms"]:
            out["instagram_positions"] = t.get(
                "instagram_positions", DEFAULT_PLACEMENTS["instagram_positions"]
            )
        if "facebook" in out["publisher_platforms"]:
            out["facebook_positions"] = t.get(
                "facebook_positions", ["feed", "story", "video_feeds"]
            )

    # Meta requires advantage_audience to be set explicitly (0 or 1), not omitted.
    out["targeting_automation"] = {"advantage_audience": 1 if t.get("advantage_audience", True) else 0}

    if "custom_audiences" in t:
        out["custom_audiences"] = t["custom_audiences"]
    if "excluded_custom_audiences" in t:
        out["excluded_custom_audiences"] = t["excluded_custom_audiences"]

    return out


# ─── Validation ────────────────────────────────────────────────────────────
def _collect_messages(ad: dict) -> list[str]:
    if "messages" in ad and isinstance(ad["messages"], list):
        return [m for m in ad["messages"] if m]
    if ad.get("message"):
        return [ad["message"]]
    return []


def _collect_headlines(ad: dict) -> list[str]:
    if "headlines" in ad and isinstance(ad["headlines"], list):
        return [h for h in ad["headlines"] if h]
    if ad.get("headline"):
        return [ad["headline"]]
    return []


def validate_spec(spec: dict) -> list[str]:
    errs = []
    if not spec.get("campaign_name"):
        errs.append("campaign_name is required")
    if not spec.get("objective"):
        errs.append("objective is required")
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
            errs.append(f"{prefix} needs daily_budget or lifetime_budget")
        if a.get("lifetime_budget") and not a.get("end_time"):
            errs.append(f"{prefix} lifetime_budget requires end_time")
        if not a.get("ads"):
            errs.append(f"{prefix}.ads must have at least one ad")
        for j, ad in enumerate(a.get("ads", [])):
            ap = f"{prefix}.ads[{j}]"
            if not ad.get("name"):
                errs.append(f"{ap}.name is required")
            msgs = _collect_messages(ad)
            hdls = _collect_headlines(ad)
            if not msgs:
                errs.append(f"{ap}: provide 'message' (str) or 'messages' (list[str], 1-5)")
            if len(msgs) > 5:
                errs.append(f"{ap}.messages cannot exceed 5 (Meta DCO cap)")
            if not hdls:
                errs.append(f"{ap}: provide 'headline' (str) or 'headlines' (list[str], 1-5)")
            if len(hdls) > 5:
                errs.append(f"{ap}.headlines cannot exceed 5 (Meta DCO cap)")
            cta = ad.get("cta", "LEARN_MORE")
            if cta not in VALID_CTAS:
                errs.append(f"{ap}.cta '{cta}' is not a recognized CTA type")
            if not ad.get("image_path") and not ad.get("image_hash"):
                errs.append(f"{ap} needs image_path or image_hash")
            if ad.get("image_path"):
                p = Path(ad["image_path"]).expanduser()
                if not p.is_absolute():
                    p = (Path.cwd() / p).resolve()
                if not p.exists():
                    errs.append(f"{ap}.image_path does not exist: {p}")
    return errs


# ─── Planning ──────────────────────────────────────────────────────────────
def plan(spec: dict, account_id: str) -> dict:
    currency = get_account_currency(account_id)
    plan_out = {
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
    total_lifetime_minor = 0
    total_ads = 0
    for a in spec["ad_sets"]:
        t = a.get("targeting", {})
        if t.get("interest_ids"):
            interests = [{"id": i, "name": f"<preset:{i}>"} for i in t["interest_ids"]]
        elif t.get("interests"):
            interests = resolve_interest_ids(t["interests"])
        else:
            interests = []

        lifetime_minor = (
            major_to_minor(a["lifetime_budget"], currency) if "lifetime_budget" in a else None
        )
        if lifetime_minor:
            total_lifetime_minor += lifetime_minor

        ads_summary = []
        for ad in a["ads"]:
            msgs = _collect_messages(ad)
            hdls = _collect_headlines(ad)
            ads_summary.append(
                {
                    "name": ad["name"],
                    "image": ad.get("image_path") or f"<prehashed:{ad.get('image_hash')}>",
                    "headlines": hdls,
                    "messages_count": len(msgs),
                    "message_previews": [m.split("\n", 1)[0][:80] + "…" for m in msgs],
                    "cta": ad.get("cta", "LEARN_MORE"),
                    "url": ad.get("url") or spec.get("landing_url"),
                    "creative_format": (
                        "asset_feed_spec (DCO)" if (len(msgs) > 1 or len(hdls) > 1) else "object_story_spec"
                    ),
                }
            )

        plan_out["ad_sets"].append(
            {
                "name": a["name"],
                "lifetime_budget_major": a.get("lifetime_budget"),
                "lifetime_budget_minor": lifetime_minor,
                "start_time": a.get("start_time"),
                "end_time": a.get("end_time"),
                "billing_event": a.get("billing_event", "IMPRESSIONS"),
                "optimization_goal": a.get("optimization_goal", "OFFSITE_CONVERSIONS"),
                "bid_strategy": a.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
                "promoted_object": a.get("promoted_object"),
                "targeting_summary": {
                    "geo": t.get("geo_locations") or {"countries": t.get("countries")},
                    "age": [t.get("age_min"), t.get("age_max")],
                    "genders": t.get("genders"),
                    "advantage_audience": t.get("advantage_audience", True),
                    "advantage_placements": t.get("advantage_placements", False),
                    "custom_audiences": t.get("custom_audiences"),
                    "interests": interests,
                },
                "ads": ads_summary,
            }
        )
        total_ads += len(a["ads"])

    plan_out["totals"] = {
        "ad_sets": len(spec["ad_sets"]),
        "ads": total_ads,
        "total_lifetime_minor": total_lifetime_minor,
        "total_lifetime_major": (
            total_lifetime_minor / (1 if currency.upper() in ZERO_DECIMAL else 100)
        ),
    }
    return plan_out


# ─── Execution ─────────────────────────────────────────────────────────────
def execute(spec: dict, account_id: str) -> dict:
    currency = get_account_currency(account_id)
    state: dict = {
        "ok": True,
        "account_id": account_id,
        "currency": currency,
        "created_at": int(time.time()),
        "objects": [],
    }

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

    # Cache image uploads by file path so we don't re-upload the same file
    image_cache: dict[str, str] = {}

    out_ad_sets = []
    for a in spec["ad_sets"]:
        t_cfg = a.get("targeting", {})

        if t_cfg.get("interest_ids"):
            interests = [{"id": i, "name": f"preset-{i}"} for i in t_cfg["interest_ids"]]
        elif t_cfg.get("interests"):
            interests = resolve_interest_ids(t_cfg["interests"])
        else:
            interests = []

        targeting = build_targeting_strict_age(t_cfg, interests)

        adset_data = {
            "name": a["name"],
            "campaign_id": campaign_id,
            "billing_event": a.get("billing_event", "IMPRESSIONS"),
            "optimization_goal": a.get("optimization_goal", "OFFSITE_CONVERSIONS"),
            "bid_strategy": a.get("bid_strategy", "LOWEST_COST_WITHOUT_CAP"),
            "targeting": json.dumps(targeting),
            "status": a.get("status", "PAUSED"),
        }
        if "start_time" in a:
            adset_data["start_time"] = a["start_time"]
        if "lifetime_budget" in a:
            adset_data["lifetime_budget"] = str(major_to_minor(a["lifetime_budget"], currency))
            adset_data["end_time"] = a["end_time"]
        elif "daily_budget" in a:
            adset_data["daily_budget"] = str(major_to_minor(a["daily_budget"], currency))
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
            # Image upload (cached)
            if ad_cfg.get("image_hash"):
                image_hash = ad_cfg["image_hash"]
            else:
                img_path = Path(ad_cfg["image_path"]).expanduser()
                if not img_path.is_absolute():
                    img_path = (Path.cwd() / img_path).resolve()
                key = str(img_path)
                if key in image_cache:
                    image_hash = image_cache[key]
                else:
                    image_hash = upload_image(account_id, img_path)
                    image_cache[key] = image_hash
                    state["objects"].append(
                        {"type": "image", "hash": image_hash, "file": img_path.name}
                    )
                    print(f"[+] image: {img_path.name} -> {image_hash[:16]}…", file=sys.stderr)

            msgs = _collect_messages(ad_cfg)
            hdls = _collect_headlines(ad_cfg)
            ad_url = ad_cfg.get("url") or landing_url
            ad_cta = ad_cfg.get("cta", "LEARN_MORE")

            use_dco = len(msgs) > 1 or len(hdls) > 1

            creative_name = f"Creative_{ad_cfg['name']}"
            if use_dco:
                feed_spec: dict = {
                    "images": [{"hash": image_hash}],
                    "bodies": [{"text": m} for m in msgs],
                    "titles": [{"text": h} for h in hdls],
                    "link_urls": [{"website_url": ad_url, "display_url": ad_url}],
                    "call_to_action_types": [ad_cta],
                    "ad_formats": ["SINGLE_IMAGE"],
                }
                if ad_cfg.get("descriptions"):
                    feed_spec["descriptions"] = [{"text": d} for d in ad_cfg["descriptions"]]
                elif ad_cfg.get("description"):
                    feed_spec["descriptions"] = [{"text": ad_cfg["description"]}]
                payload = {
                    "name": creative_name,
                    "page_id": page_id,
                    "asset_feed_spec": json.dumps(feed_spec),
                }
                if ig_user_id:
                    payload["instagram_user_id"] = ig_user_id
            else:
                osys = {
                    "page_id": page_id,
                    "link_data": {
                        "link": ad_url,
                        "message": msgs[0],
                        "name": hdls[0],
                        "image_hash": image_hash,
                        "call_to_action": {"type": ad_cta, "value": {"link": ad_url}},
                    },
                }
                if ad_cfg.get("description"):
                    osys["link_data"]["description"] = ad_cfg["description"]
                if ig_user_id:
                    osys["instagram_user_id"] = ig_user_id
                payload = {"name": creative_name, "object_story_spec": json.dumps(osys)}

            try:
                creative = post(f"{account_id}/adcreatives", data=payload)
            except MetaAPIError as e:
                # Capture full error context in state for debugging
                state["objects"].append({"type": "creative_failed", "ad": ad_cfg["name"], "error": str(e), "body": e.body})
                raise

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

        out_ad_sets.append({"adset_id": adset_id, "ads": ads_created})

    state["ad_sets"] = out_ad_sets
    return state


# ─── Entry ─────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--dry-run", action="store_true")
    grp.add_argument("--confirm", action="store_true")
    ap.add_argument("--account-id", default=None)
    ap.add_argument("--state-out", default=None)
    args = ap.parse_args()

    spec_path = Path(args.spec).expanduser().resolve()
    if not spec_path.exists():
        print(f"spec not found: {spec_path}", file=sys.stderr)
        return 2
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    errs = validate_spec(spec)
    if errs:
        print("Spec validation failed:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 2

    account_id = normalize_account_id(args.account_id)

    if args.dry_run:
        try:
            p = plan(spec, account_id)
        except MetaAPIError as e:
            print_json({"ok": False, "error": str(e), "body": e.body})
            return 1
        print_json(p)
        return 0

    state_file = (
        Path(args.state_out)
        if args.state_out
        else spec_path.with_name(f"{spec_path.stem}_state_{int(time.time())}.json")
    )
    try:
        state = execute(spec, account_id)
    except MetaAPIError as e:
        state = {"ok": False, "error": str(e), "api_error_body": e.body}
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print_json(state)
        return 1
    except Exception as e:
        state = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        print_json(state)
        return 1
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[state] -> {state_file}", file=sys.stderr)
    print_json(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
