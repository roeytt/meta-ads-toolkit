"""
Fetch the full structure of a Meta Ads campaign:
campaign settings → ad sets → ads → creative details (including all asset_feed_spec bodies).

Usage:
  META_ACCESS_TOKEN=<token> python fetch_structure.py --campaign-id <id> --account-id <act_id>

Output: JSON to stdout.
"""
import argparse
import json
import os
import sys

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Run: python -m pip install --user requests", file=sys.stderr)
    sys.exit(1)

TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
API_VER = "v25.0"
BASE = f"https://graph.facebook.com/{API_VER}"


def get(path, params=None):
    p = {"access_token": TOKEN, **(params or {})}
    r = requests.get(f"{BASE}/{path}", params=p)
    d = r.json()
    if "error" in d:
        raise RuntimeError(f"API error on /{path}: {json.dumps(d['error'], ensure_ascii=False)}")
    return d


def paginate(path, params=None):
    results = []
    p = {"access_token": TOKEN, **(params or {})}
    url = f"{BASE}/{path}"
    while url:
        r = requests.get(url, params=p)
        d = r.json()
        if "error" in d:
            raise RuntimeError(f"API error on {url}: {json.dumps(d['error'], ensure_ascii=False)}")
        results.extend(d.get("data", []))
        url = d.get("paging", {}).get("next")
        p = {}  # next URL already has params
    return results


def fetch_creative(creative_id):
    d = get(creative_id, {
        "fields": "id,name,body,title,asset_feed_spec,object_story_spec,image_url"
    })
    creative = {"id": d.get("id"), "name": d.get("name")}

    # Extract bodies and titles from asset_feed_spec if present
    afs = d.get("asset_feed_spec", {})
    if afs:
        creative["bodies"] = [b["text"] for b in afs.get("bodies", [])]
        creative["titles"] = [t["text"] for t in afs.get("titles", [])]
        creative["optimization_type"] = afs.get("optimization_type", "DEGREES_OF_FREEDOM")
    else:
        # Single-body creative
        creative["bodies"] = [d.get("body", "")]
        creative["titles"] = [d.get("title", "")]
        creative["optimization_type"] = None

    # Extract image hash, link, CTA, page, ig from object_story_spec
    oss = d.get("object_story_spec", {})
    creative["page_id"] = oss.get("page_id")
    creative["instagram_user_id"] = oss.get("instagram_user_id")
    link_data = oss.get("link_data", {})
    creative["link"] = link_data.get("link")
    creative["image_hash"] = link_data.get("image_hash")
    cta = link_data.get("call_to_action", {})
    creative["call_to_action"] = cta.get("type")
    creative["image_url"] = d.get("image_url")

    return creative


def fetch_ads(adset_id):
    raw = paginate(f"{adset_id}/ads", {"fields": "id,name,status,creative{id}"})
    ads = []
    for ad in raw:
        creative_id = ad.get("creative", {}).get("id")
        creative = fetch_creative(creative_id) if creative_id else {}
        ads.append({
            "id": ad["id"],
            "name": ad.get("name"),
            "status": ad.get("status"),
            "creative": creative,
        })
    return ads


def fetch_adsets(campaign_id):
    fields = (
        "id,name,status,targeting,optimization_goal,billing_event,"
        "bid_strategy,lifetime_budget,daily_budget,start_time,end_time,"
        "promoted_object,destination_type"
    )
    raw = paginate(f"{campaign_id}/adsets", {"fields": fields})
    adsets = []
    for adset in raw:
        adset["ads"] = fetch_ads(adset["id"])
        # Convert budget to major units for readability
        for key in ("lifetime_budget", "daily_budget"):
            if key in adset:
                adset[f"{key}_major"] = int(adset[key]) / 100
        adsets.append(adset)
    return adsets


def fetch_campaign(campaign_id):
    fields = (
        "id,name,objective,status,buying_type,lifetime_budget,daily_budget,"
        "bid_strategy,special_ad_categories,start_time,stop_time"
    )
    d = get(campaign_id, {"fields": fields})
    for key in ("lifetime_budget", "daily_budget"):
        if key in d:
            d[f"{key}_major"] = int(d[key]) / 100
    return d


def main():
    parser = argparse.ArgumentParser(description="Fetch full Meta Ads campaign structure.")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()

    if not TOKEN:
        print("Error: META_ACCESS_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    campaign = fetch_campaign(args.campaign_id)
    campaign["adsets"] = fetch_adsets(args.campaign_id)

    json.dump({"ok": True, "campaign": campaign}, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
