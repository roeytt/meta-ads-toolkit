"""
update_ad_copy.py — append text to Primary Text of all ads in a campaign.
Usage:
  python scripts/update_ad_copy.py --campaign-id <id> --append "<text>" [--dry-run] [--confirm]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import meta_client as mc


def fetch_ads(campaign_id: str) -> list[dict]:
    fields = "id,name,creative{id,object_story_spec}"
    return list(mc.paginate(f"/{campaign_id}/ads", params={"fields": fields}))


def parse_ad(ad: dict) -> dict:
    c = ad.get("creative", {})
    oss = c.get("object_story_spec", {})
    ld = oss.get("link_data", {})
    return {
        "ad_id": ad["id"],
        "ad_name": ad.get("name", ""),
        "creative_id": c.get("id", ""),
        "message": ld.get("message", ""),
        "oss": oss,
    }


def create_updated_creative(account_id: str, parsed: dict, new_message: str) -> str:
    oss = dict(parsed["oss"])
    oss["link_data"] = dict(oss.get("link_data", {}))
    oss["link_data"]["message"] = new_message

    payload = {
        "object_story_spec": json.dumps(oss),
    }
    resp = mc.post(f"/{account_id}/adcreatives", data=payload)
    return resp["id"]


def update_ad_creative(ad_id: str, creative_id: str) -> dict:
    return mc.post(f"/{ad_id}", data={"creative": json.dumps({"creative_id": creative_id})})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--append", dest="append_text", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args()

    if not args.append_text:
        args.append_text = os.environ.get("UPDATE_APPEND_TEXT", "")
    if not args.append_text:
        print(json.dumps({"ok": False, "error": "--append or UPDATE_APPEND_TEXT env var required"}))
        return 1

    if not args.dry_run and not args.confirm:
        print(json.dumps({"ok": False, "error": "Pass --dry-run to preview or --confirm to execute."}))
        return 1

    ads = fetch_ads(args.campaign_id)
    parsed_ads = [parse_ad(a) for a in ads]

    cta = args.append_text
    plan = []
    for p in parsed_ads:
        current = p["message"]
        if current.rstrip().endswith(cta):
            new_msg = current  # already there
            status = "already_present"
        else:
            new_msg = current.rstrip() + "\n\n" + cta
            status = "will_update"
        plan.append({**p, "new_message": new_msg, "status": status})

    if args.dry_run:
        output = []
        for item in plan:
            output.append({
                "ad_id": item["ad_id"],
                "ad_name": item["ad_name"],
                "status": item["status"],
                "message_before": item["message"][-80:] + "..." if len(item["message"]) > 80 else item["message"],
                "message_after_tail": item["new_message"][-120:],
            })
        mc.print_json({"ok": True, "mode": "dry_run", "ads": output})
        return 0

    # --confirm: execute
    results = []
    for item in plan:
        if item["status"] == "already_present":
            results.append({"ad_id": item["ad_id"], "ad_name": item["ad_name"], "result": "skipped_already_present"})
            continue
        try:
            new_creative_id = create_updated_creative(args.account_id, item, item["new_message"])
            update_ad_creative(item["ad_id"], new_creative_id)
            results.append({
                "ad_id": item["ad_id"],
                "ad_name": item["ad_name"],
                "old_creative_id": item["creative_id"],
                "new_creative_id": new_creative_id,
                "result": "updated",
            })
        except Exception as e:
            results.append({"ad_id": item["ad_id"], "ad_name": item["ad_name"], "result": "error", "error": str(e)})

    mc.print_json({"ok": True, "mode": "confirm", "results": results})
    return 0


if __name__ == "__main__":
    sys.exit(main())
