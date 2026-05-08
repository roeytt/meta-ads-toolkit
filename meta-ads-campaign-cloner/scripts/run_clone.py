"""
Execute a campaign clone from a spec JSON file.

Usage:
  META_ACCESS_TOKEN=<token> python run_clone.py --spec <path-to-spec.json>

The spec JSON is built by Claude based on the user's request and source campaign structure.
See references/spec_format.md for the full schema.

Output: state JSON with all created object IDs (for rollback if needed).
"""
import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Missing dependency: requests. Run: python -m pip install --user requests", file=sys.stderr)
    sys.exit(1)

TOKEN = os.environ.get("META_ACCESS_TOKEN", "")
API_VER = "v25.0"
BASE = f"https://graph.facebook.com/{API_VER}"


def api_post(path, data=None, files=None):
    url = f"{BASE}/{path}"
    params = {"access_token": TOKEN}
    if files:
        r = requests.post(url, params=params, files=files, data=data or {})
    else:
        r = requests.post(url, params=params, data=data or {})
    d = r.json()
    if "error" in d:
        raise RuntimeError(
            f"API error on POST /{path}:\n{json.dumps(d['error'], indent=2, ensure_ascii=False)}"
        )
    return d


def upload_image(account_id, file_path):
    with open(file_path, "rb") as f:
        ext = os.path.splitext(file_path)[1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        r = requests.post(
            f"{BASE}/{account_id}/adimages",
            params={"access_token": TOKEN},
            files={"filename": (os.path.basename(file_path), f, mime)},
        )
    d = r.json()
    if "error" in d:
        raise RuntimeError(f"Image upload error: {json.dumps(d['error'], ensure_ascii=False)}")
    images = d.get("images", {})
    for _, info in images.items():
        return info["hash"]
    raise RuntimeError(f"No hash in upload response: {d}")


def create_campaign(account_id, spec):
    data = {
        "name": spec["name"],
        "objective": spec["objective"],
        "status": spec.get("status", "PAUSED"),
        "buying_type": spec.get("buying_type", "AUCTION"),
        "special_ad_categories": json.dumps(spec.get("special_ad_categories", [])),
    }
    if "lifetime_budget" in spec:
        data["lifetime_budget"] = str(spec["lifetime_budget"])
    if "daily_budget" in spec:
        data["daily_budget"] = str(spec["daily_budget"])
    if "bid_strategy" in spec:
        data["bid_strategy"] = spec["bid_strategy"]
    d = api_post(f"{account_id}/campaigns", data)
    return d["id"]


def create_adset(account_id, campaign_id, spec):
    data = {
        "name": spec["name"],
        "campaign_id": campaign_id,
        "status": spec.get("status", "PAUSED"),
        "optimization_goal": spec["optimization_goal"],
        "billing_event": spec["billing_event"],
        "targeting": json.dumps(spec["targeting"]),
    }
    if "bid_strategy" in spec:
        data["bid_strategy"] = spec["bid_strategy"]
    if "bid_amount" in spec:
        data["bid_amount"] = str(spec["bid_amount"])
    if "lifetime_budget" in spec:
        data["lifetime_budget"] = str(spec["lifetime_budget"])
    if "daily_budget" in spec:
        data["daily_budget"] = str(spec["daily_budget"])
    if "promoted_object" in spec:
        data["promoted_object"] = json.dumps(spec["promoted_object"])
    if "end_time" in spec:
        data["end_time"] = spec["end_time"]
    if "start_time" in spec:
        data["start_time"] = spec["start_time"]
    if "destination_type" in spec and spec["destination_type"] not in (None, "UNDEFINED", ""):
        data["destination_type"] = spec["destination_type"]
    d = api_post(f"{account_id}/adsets", data)
    return d["id"]


def create_creative(account_id, creative_spec, image_hash):
    bodies = creative_spec.get("bodies", [])
    titles = creative_spec.get("titles", [""])

    object_story_spec = {
        "page_id": creative_spec["page_id"],
        "link_data": {
            "link": creative_spec["link"],
            "image_hash": image_hash,
            "call_to_action": {"type": creative_spec.get("call_to_action", "SIGN_UP")},
        },
    }
    if creative_spec.get("instagram_user_id"):
        object_story_spec["instagram_user_id"] = creative_spec["instagram_user_id"]

    post_data = {"object_story_spec": json.dumps(object_story_spec)}

    if len(bodies) > 1:
        # Multiple text variations — use asset_feed_spec
        asset_feed_spec = {
            "bodies": [{"text": b} for b in bodies],
            "titles": [{"text": t} for t in titles],
            "optimization_type": creative_spec.get("optimization_type", "DEGREES_OF_FREEDOM"),
        }
        post_data["asset_feed_spec"] = json.dumps(asset_feed_spec)
    else:
        # Single body
        post_data["body"] = bodies[0] if bodies else ""
        if titles:
            post_data["title"] = titles[0]

    # Add primary_text if provided
    if creative_spec.get("primary_text"):
        post_data["primary_text"] = creative_spec["primary_text"]

    d = api_post(f"{account_id}/adcreatives", post_data)
    return d["id"]


def create_ad(account_id, adset_id, ad_spec, creative_id, primary_text=None):
    data = {
        "name": ad_spec["name"],
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": ad_spec.get("status", "PAUSED"),
    }
    if primary_text:
        data["adset_spec"] = json.dumps({"primary_text": primary_text})
    d = api_post(f"{account_id}/ads", data)
    return d["id"]


def resolve_bodies(bodies, substitutions):
    """Apply text substitutions to all body texts."""
    result = []
    for body in bodies:
        for old, new in substitutions.items():
            body = body.replace(old, new)
        result.append(body)
    return result


def main():
    parser = argparse.ArgumentParser(description="Execute a campaign clone from a spec JSON.")
    parser.add_argument("--spec", required=True, help="Path to the clone spec JSON file.")
    args = parser.parse_args()

    if not TOKEN:
        print("Error: META_ACCESS_TOKEN not set.", file=sys.stderr)
        sys.exit(1)

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)

    account_id = spec["account_id"]
    image_dir = spec.get("image_dir", ".")
    substitutions = spec.get("copy_substitutions", {})

    state = {
        "spec_file": args.spec,
        "account_id": account_id,
        "campaign_id": None,
        "adsets": [],
    }

    # 1. Create campaign
    print(f"Creating campaign: {spec['campaign']['name']}")
    campaign_id = create_campaign(account_id, spec["campaign"])
    state["campaign_id"] = campaign_id
    print(f"  → Campaign: {campaign_id}")

    # 2. For each ad set
    for asi, adset_spec in enumerate(spec.get("adsets", [])):
        print(f"\nCreating ad set: {adset_spec['name']}")
        adset_id = create_adset(account_id, campaign_id, adset_spec)
        adset_state = {"adset_id": adset_id, "name": adset_spec["name"], "ads": []}
        state["adsets"].append(adset_state)
        print(f"  → Ad set: {adset_id}")

        # 3. For each ad in this ad set
        for ad_spec in adset_spec.get("ads", []):
            ad_name = ad_spec["name"]
            creative_spec = ad_spec["creative"]
            file_path = os.path.join(image_dir, creative_spec["file"])

            print(f"\n  Ad: {ad_name}")
            print(f"    Uploading: {creative_spec['file']}")
            image_hash = upload_image(account_id, file_path)
            print(f"    Image hash: {image_hash}")

            # Apply substitutions to bodies
            bodies = creative_spec.get("bodies", [])
            if substitutions:
                bodies = resolve_bodies(bodies, substitutions)

            resolved_spec = {**creative_spec, "bodies": bodies}

            print(f"    Creating creative ({len(bodies)} body variants)...")
            creative_id = create_creative(account_id, resolved_spec, image_hash)
            print(f"    Creative: {creative_id}")

            print(f"    Creating ad...")
            primary_text = creative_spec.get("primary_text")
            if primary_text and substitutions:
                primary_text = primary_text
                for old, new in substitutions.items():
                    primary_text = primary_text.replace(old, new)
            ad_id = create_ad(account_id, adset_id, ad_spec, creative_id, primary_text)
            print(f"    Ad: {ad_id}")

            adset_state["ads"].append({
                "ad_id": ad_id,
                "name": ad_name,
                "creative_id": creative_id,
                "image_hash": image_hash,
                "file": creative_spec["file"],
            })

    print("\n=== DONE ===")
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return state


if __name__ == "__main__":
    main()
