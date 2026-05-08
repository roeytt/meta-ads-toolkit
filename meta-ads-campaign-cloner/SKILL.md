---
name: meta-ads-campaign-cloner
description: >
  Clones a Meta Ads campaign with new creatives and copy changes. Use this skill whenever the user wants to
  create a new campaign based on an existing one — even partially. Trigger on phrases like:
  "שכפל קמפיין", "תצור קמפיין חדש על בסיס", "עשה קמפיין דומה ל", "duplicate campaign",
  "clone campaign", "new campaign like the last one", "העלה קריאייטיבים חדשים לקמפיין חדש",
  "קמפיין לוובינר הבא", or any request to create a campaign where a previous one serves as a template.
  Also trigger when the user mentions new images/videos for a recurring campaign type.
---

> Built by **Roey Treister** for the "Claude Code × Meta Ads" workshop. Hebrew quick-start: see [README.md](README.md).

# Meta Ads Campaign Cloner

This skill guides a **structured, conversation-driven workflow** for cloning a Meta Ads campaign with
new creatives and/or copy. Nothing is sent to Meta until the user explicitly approves the full plan.

## Setup

- Accounts and tokens: `~/.claude/skills/meta-ads/accounts.json` (shared with the meta-ads skill, optional)
  - If `accounts.json` is missing, fall back to `META_ACCESS_TOKEN` and `META_AD_ACCOUNT_ID` from the user's `.env`.
- Python executable: use whatever is on the user's PATH (`python` on Windows, `python3` on macOS/Linux). If the user has multiple Pythons installed, ask which one they used to install `requests`.
- Always set env vars: `META_ACCESS_TOKEN=<token>` and `PYTHONIOENCODING=utf-8` (the latter prevents Hebrew/Arabic encoding issues on Windows cmd.exe).
- Scripts are in `~/.claude/skills/meta-ads-campaign-cloner/scripts/`
- Meta-ads scripts (list_campaigns, auth_check, etc.) are in `~/.claude/skills/meta-ads/scripts/`

## The Five Phases

Work through these phases in order. Never skip to execution without completing the plan and getting approval.

---

### Phase 1 — Understand the request

Gather the following (some may already be in the user's message):

1. **Account** — match against `accounts.json` (fuzzy, same logic as meta-ads skill). If `accounts.json` is missing, use the default `META_AD_ACCOUNT_ID` from `.env`.
2. **Source campaign** — name or number; if unclear, list campaigns and let the user pick
3. **New campaign name** — exactly as the user specifies
4. **What changes?** — creatives, copy, ad sets, budget, dates, conversion events, or any combination
5. **Working directory** — where are the new image/video files? List them to the user.
6. **End date/time** — only ask if the user explicitly specifies date changes; don't assume end_time is required

Ask only what you don't know. If the user's message already answers most of this, confirm briefly and move on.

---

### Phase 2 — Fetch source campaign structure

Run `fetch_structure.py` to get the full campaign tree:

```
META_ACCESS_TOKEN=<token> PYTHONIOENCODING=utf-8 python scripts/fetch_structure.py \
  --campaign-id <id> --account-id <act_id>
```

This returns a JSON with:
- Campaign-level settings (objective, budget, bid strategy)
- Each ad set (targeting, optimization, promoted_object, dates)
- Each ad and its creative (bodies list, titles, image hash, link, CTA, page_id, ig_user_id)

Use this as the starting point for the new campaign. You'll override only what the user asks to change.

---

### Phase 3 — Plan the new campaign

Build a **spec JSON** that fully describes what will be created. Read `references/spec_format.md` for
the exact schema.

Key decisions to make during planning:

**Creatives:**
- List the files in the working directory. Ask the user to confirm which file maps to which ad
  (or confirm if the numbering is obvious: 1.png → ad 1, 2.png → ad 2, etc.)
- If the user has more/fewer images than the source campaign had ads, adjust accordingly

**Copy:**
- **Simple substitution** (e.g., date change): apply automatically and show the result in the plan
- **New copy**: write it yourself based on the user's brief, then present it for explicit approval
  before including it in the spec. Never put unapproved copy in the spec.
- **Copy from files**: if the user has copy in the working directory, read and use it

**Conversion Event/Promoted Object:**
- **Always copy exactly from the source campaign** — do not assume or change the conversion event type
- If source has "Website purchase", copy "Website purchase" (not PURCHASE, not custom events)
- This is critical for accuracy and must be replicated precisely

**Ad sets:**
- Default: clone each source ad set, apply user-requested overrides (new end time, different budget, etc.)
- If the user wants different ad set structure, define it from scratch
- **Important:** end_time is optional — only include if source campaign has an end date or user explicitly specifies one

**What to keep from source (unless user says otherwise):**
- Campaign objective, bid strategy, budget amount
- Ad set targeting, optimization goal, billing event, **conversion event/promoted_object** (copy exactly)
- Creative title, landing page URL, call-to-action type, page ID, Instagram ID
- Ad names pattern
- Campaign end date/time (if present in source)

---

### Phase 4 — Present the plan and get approval

Before writing a single API call, show the user a clear summary. Example:

```
📋 **תכנית הקמפיין החדש**

**קמפיין:** [שם הקמפיין החדש כפי שהוגדר]
**תקציב:** ₪X,XXX (lifetime) | **מטרה:** OUTCOME_LEADS | **סיום:** [תאריך ושעה]

**סט מודעות:** [תיאור הקהל] | [טווח גילאים]
  מודעה 1 — תמונה: 1.png | קופי: N גרסאות (החלפות: [סיכום])
  מודעה 2 — תמונה: 2.png | קופי: N גרסאות
  ...

הכל יווצר PAUSED. אחרי שתאמת ב-Ads Manager תוכל להפעיל.

**כדי לאשר כתוב: בצע**
```

Wait for explicit confirmation ("בצע", "confirm", "כן", "go ahead"). Do not proceed without it.
A general "ok" or "👍" is not confirmation — ask again if unclear.

---

### Phase 5 — Execute

Once confirmed, run `run_clone.py` with the spec file:

```
META_ACCESS_TOKEN=<token> PYTHONIOENCODING=utf-8 python scripts/run_clone.py \
  --spec <path-to-spec.json>
```

The script creates everything in order: campaign → ad sets → (upload image → create creative → create ad) × N.
It outputs a state JSON with all created IDs.

If it fails partway through, the state JSON shows what was already created. Do not re-run blindly —
check what exists first, fix the issue, and continue from where it stopped.

After success, report:
- Campaign ID and name
- How many ad sets and ads were created
- Remind the user: everything is PAUSED, activate from Ads Manager when ready

---

## Copy handling details

**Simple substitution:** Replace all occurrences of the old string in every body text.
Show the user the before/after for at least one body so they can verify.

**New copy written by Claude:** Follow this mini-flow:
1. Ask the user for a brief or topic
2. Write all body variations (match the count from the source campaign)
3. Present them clearly, numbered
4. Wait for explicit approval or requested changes
5. Only after approval, put the copy in the spec

**Copy files in directory:** If you see `.txt` or `.md` files alongside the images, ask the user
if those are the new body texts. Read them and use them as-is (after confirming with the user).

---

## Notes on videos

For video creatives, the upload flow is different (async processing). If the user brings `.mp4` or
similar files, note that video support requires a different workflow and handle it manually via the
Meta-ads skill's API patterns. Image creatives (PNG, JPG) are fully supported by `run_clone.py`.

---

## Working with multiple ad sets

If the source campaign has multiple ad sets, or the user wants a different ad set structure:
- List all source ad sets in the plan
- For each, show targeting summary and which ads belong to it
- Let the user confirm or adjust per-ad-set before building the spec
