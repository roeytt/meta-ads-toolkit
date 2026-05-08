# Clone Spec JSON Format

Claude builds this file based on the user's request + the source campaign structure.
It is passed to `run_clone.py` via `--spec <path>`.

---

## Full Example

```json
{
  "account_id": "act_0000000000000000",
  "image_dir": "C:\\path\\to\\creatives\\folder",
  "copy_substitutions": {
    "old date": "new date"
  },
  "campaign": {
    "name": "Campaign | Webinar Invite (15.6.26) | 1.6.26",
    "objective": "OUTCOME_LEADS",
    "status": "PAUSED",
    "buying_type": "AUCTION",
    "lifetime_budget": 500000,
    "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
    "special_ad_categories": []
  },
  "adsets": [
    {
      "name": "Advantage+ audience | 30-55",
      "status": "PAUSED",
      "optimization_goal": "OFFSITE_CONVERSIONS",
      "billing_event": "IMPRESSIONS",
      "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
      "end_time": "2026-06-15T19:30:00+0300",
      "promoted_object": {
        "pixel_id": "0000000000000000",
        "custom_event_type": "COMPLETE_REGISTRATION"
      },
      "targeting": {
        "age_max": 65,
        "age_min": 25,
        "geo_locations": {
          "countries": ["IL"],
          "location_types": ["home", "recent"]
        },
        "brand_safety_content_filter_levels": ["FACEBOOK_RELAXED", "AN_RELAXED"],
        "targeting_automation": {
          "advantage_audience": 1,
          "individual_setting": { "age": 1, "gender": 1 }
        }
      },
      "ads": [
        {
          "name": "Image 1 - 4 copy variants",
          "status": "PAUSED",
          "creative": {
            "file": "1.png",
            "page_id": "0000000000000000",
            "instagram_user_id": "00000000000000000",
            "link": "https://example.com/landing-page/",
            "call_to_action": "SIGN_UP",
            "optimization_type": "DEGREES_OF_FREEDOM",
            "titles": ["Practical training inside >>"],
            "bodies": [
              "body text 1 (with old date — substitution applies automatically)",
              "body text 2",
              "body text 3",
              "body text 4"
            ]
          }
        }
      ]
    }
  ]
}
```

> **Note on placeholders:** the `0000...` IDs above are intentional placeholders. Replace them with real values from your account, page, Instagram, and pixel — typically obtained by running `fetch_structure.py` on a source campaign you want to clone from, then copying the IDs forward.

---

## Field Reference

### Top-level

| Field | Required | Notes |
|-------|----------|-------|
| `account_id` | ✓ | Format: `act_XXXXXXXXX` |
| `image_dir` | ✓ | Absolute path to folder with creative files |
| `copy_substitutions` | | Map of `{"old string": "new string"}`. Applied to all body texts. |

### `campaign`

| Field | Required | Notes |
|-------|----------|-------|
| `name` | ✓ | |
| `objective` | ✓ | e.g. `OUTCOME_LEADS`, `OUTCOME_SALES`, `OUTCOME_TRAFFIC` |
| `status` | | Default: `PAUSED` — always leave PAUSED |
| `buying_type` | | Default: `AUCTION` |
| `lifetime_budget` | one of | In agorot (minor units). ₪5,000 = 500000 |
| `daily_budget` | one of | In agorot |
| `bid_strategy` | | e.g. `LOWEST_COST_WITHOUT_CAP` |
| `special_ad_categories` | | Usually `[]` |

### `adsets[]`

| Field | Required | Notes |
|-------|----------|-------|
| `name` | ✓ | |
| `optimization_goal` | ✓ | e.g. `OFFSITE_CONVERSIONS`, `LINK_CLICKS`, `LEAD_GENERATION` |
| `billing_event` | ✓ | Usually `IMPRESSIONS` |
| `targeting` | ✓ | Full targeting object from Meta API |
| `status` | | Default: `PAUSED` |
| `bid_strategy` | | Inherit from campaign if CBO |
| `lifetime_budget` | | Only set if NOT using CBO (campaign-level budget) |
| `end_time` | | Required when lifetime_budget is used. ISO 8601 with timezone. |
| `start_time` | | Optional. Omit to use current time. |
| `promoted_object` | | Required for conversions campaigns |

### `adsets[].ads[]`

| Field | Required | Notes |
|-------|----------|-------|
| `name` | ✓ | |
| `status` | | Default: `PAUSED` |
| `creative.file` | ✓ | Filename relative to `image_dir` (e.g. `1.png`, `banner.jpg`) |
| `creative.page_id` | ✓ | Facebook Page ID |
| `creative.instagram_user_id` | | Instagram account ID |
| `creative.link` | ✓ | Landing page URL |
| `creative.call_to_action` | | Default: `SIGN_UP`. Other options: `LEARN_MORE`, `SIGN_UP`, `SUBSCRIBE`, `CONTACT_US` |
| `creative.bodies` | ✓ | List of body text strings. 1 = single body. 2-5 = asset_feed_spec with variations. |
| `creative.titles` | ✓ | List of title strings (usually 1). |
| `creative.optimization_type` | | Default: `DEGREES_OF_FREEDOM` (for multi-body). |

---

## Budget: CBO vs Ad Set level

- **CBO (Campaign Budget Optimization)**: budget is set at `campaign.lifetime_budget` or `campaign.daily_budget`.
  Ad sets do NOT have their own budget field — but they still need `end_time` when campaign uses lifetime budget.
- **Ad set level budget**: omit budget from campaign, set `lifetime_budget` or `daily_budget` on each adset.

The source campaign's fetch output makes this clear — if the campaign has a budget field, it's CBO.

---

## Copy substitutions

`copy_substitutions` is a flat map applied to every `bodies` entry across all ads:

```json
"copy_substitutions": {
  "old date": "new date",
  "Webinar #25": "Webinar #26"
}
```

All substitutions are applied in order. The bodies in the spec should contain the **original text**
(copied from the source campaign) — substitutions happen at execution time in `run_clone.py`.

If copy is completely new (not derived from source), put it directly in `bodies` and leave
`copy_substitutions` empty or omit it.
