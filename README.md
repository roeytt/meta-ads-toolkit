# meta-ads-toolkit

> סקילים ל-Claude Code שהופכים את ניהול הקמפיינים במטא לפרומפט בעברית.
> נבנה ע"י **[Roey Treister](https://github.com/roeytt)** עבור הוורקשופ "Claude Code × פרסום במטא".

[English](#english) | [עברית](#hebrew)

---

<a id="hebrew"></a>

## מה יש כאן?

שלושה סקילים שעובדים יחד:

| סקיל | תפקיד |
|---|---|
| **[brief-builder](./brief-builder/)** | אשף שיחה — שואל שאלות ובונה בריף מלא לקמפיין (יעד, קהל, תקציב, קריאייטיב, בידינג). |
| **[meta-ads](./meta-ads/)** | סקיל ראשי — קריאת ביצועים, ניתוחי fatigue/anomaly, יצירת קמפיין מאפס, הקפאה, שינוי תקציב, שכפול. תומך בקרוסלה ו-DCO. |
| **[meta-ads-campaign-cloner](./meta-ads-campaign-cloner/)** | סקיל ייעודי — שכפול קמפיין מנצח עם וריאציות חדשות (קריאייטיב, קופי, תאריך). |

הסקילים תוכננו ל-Claude Code על Windows / macOS / Linux. הם משתמשים ב-Marketing API של מטא ישירות, בלי שרתים ביניים.

## התקנה — שורה אחת ב-Claude Code

תפתח שיחה חדשה ב-Claude Code, ותגיד לו:

```
תתקין סקיל מ-https://github.com/roeytt/meta-ads-toolkit/raw/main/brief-builder.skill
```

```
תתקין סקיל מ-https://github.com/roeytt/meta-ads-toolkit/raw/main/meta-ads.skill
```

Claude יוריד, יסרוק, ויתקין אוטומטית. אחרי 30 שניות הסקיל מותקן ב-`~/.claude/skills/`.

## הגדרה ראשונית (לסקיל meta-ads)

אחרי התקנת `meta-ads`, יש שלב חד-פעמי של חיבור ל-Meta API:
- תיצור אפליקציה ב-`developers.facebook.com`
- תוציא טוקן (System User או 60-day user token)
- תמלא קובץ `accounts.json`

ההוראות המפורטות נמצאות ב-[`meta-ads/references/setup.md`](./meta-ads/references/setup.md). זה לוקח 15-25 דקות בפעם הראשונה.

## איך זה עובד בפועל?

**שלב א — בניית הבריף (brief-builder):**
```
אני רוצה לפרסם קמפיין חדש
```
Claude ישאל שאלות מובנות ויפלוט בריף מוכן להקמה.

**שלב ב — הקמת הקמפיין (meta-ads):**
```
תקים לי את הקמפיין לפי הבריף
```
Claude יריץ `create_campaign.py`, יציג תוכנית, ויחכה לאישור שלך לפני שנוגע בחשבון.

## כללי בטיחות

הסקילים מבצעים פעולות אמיתיות מול חשבון המודעות שלך. הכלל הבסיסי:

> **כל פעולת כתיבה (הקפאה, שינוי תקציב, יצירה) דורשת אישור מפורש שלך בצ'אט לפני שהיא קורית.**

קרא את [`meta-ads/references/write-actions.md`](./meta-ads/references/write-actions.md) לפני שאתה מתחיל לעשות פעולות כתיבה.

**טוקנים הם כמו סיסמאות לחשבון המודעות שלך.** אל תשתף אותם, אל תשמור אותם ב-git ציבורי, ואל תשלח אותם בצ'אט/אימייל.

---

<a id="english"></a>

## What's in this repo?

Three Claude Code skills for managing Meta ads (Facebook, Instagram, Click-to-WhatsApp) via natural-language prompts.

| Skill | Purpose |
|---|---|
| **[brief-builder](./brief-builder/)** | Campaign brief wizard — asks structured questions and outputs a full campaign brief ready for execution. |
| **[meta-ads](./meta-ads/)** | Main skill — read performance, fatigue/anomaly analyses, create campaigns (including carousel & DCO), pause, change budgets, duplicate. |
| **[meta-ads-campaign-cloner](./meta-ads-campaign-cloner/)** | Clone a winning campaign with new creatives, copy, or dates. |

Built for Claude Code on Windows / macOS / Linux. Uses the Meta Marketing API directly, no intermediate servers.

## Quick install

In a new Claude Code session, say:

```
Install skill from https://github.com/roeytt/meta-ads-toolkit/raw/main/brief-builder.skill
```

```
Install skill from https://github.com/roeytt/meta-ads-toolkit/raw/main/meta-ads.skill
```

## First-time setup (meta-ads)

You'll need to connect to Meta's API once:
- Create a Meta developer app
- Generate an access token (System User token or 60-day user token)
- Fill in `accounts.json`

Detailed walkthrough: [`meta-ads/references/setup.md`](./meta-ads/references/setup.md). About 15-25 minutes the first time.

## License

MIT — see [LICENSE](./LICENSE).

## Author

**Roey Treister** — Meta ads instructor, runs the Hebrew course "פרסם זאת בעצמך" for Israeli business owners.

- GitHub: [@roeytt](https://github.com/roeytt)
