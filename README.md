# meta-ads-toolkit

> שני סקילים ל-Claude Code שהופכים את ניהול הקמפיינים במטא לפרומפט בעברית.
> נבנה ע"י **[Roey Treister](https://github.com/roeytt)** עבור הוורקשופ "Claude Code × פרסום במטא".

[English](#english) | [עברית](#hebrew)

---

<a id="hebrew"></a>

## מה יש כאן?

שני סקילים שעובדים יחד:

| סקיל | תפקיד |
|---|---|
| **[meta-ads](./meta-ads/)** | סקיל ראשי — קריאת ביצועים, ניתוחי fatigue/anomaly, יצירת קמפיין מאפס, הקפאה, שינוי תקציב, שכפול. |
| **[meta-ads-campaign-cloner](./meta-ads-campaign-cloner/)** | סקיל ייעודי — שכפול קמפיין מנצח עם וריאציות חדשות (קריאייטיב, קופי, תאריך). |

הסקילים תוכננו ל-Claude Code על Windows / macOS / Linux. הם משתמשים ב-Marketing API של מטא ישירות, בלי שרתים ביניים.

## התקנה — שורה אחת ב-Claude Code

תפתח שיחה חדשה ב-Claude Code, ותגיד לו:

```
תיכנס ל-https://github.com/roeytt/meta-ads-toolkit
תוריד את שתי התיקיות "meta-ads" ו-"meta-ads-campaign-cloner"
ותעתיק אותן ל-~/.claude/skills/
```

Claude יבצע `git clone` או יוריד קובץ-קובץ דרך GitHub raw URLs. אחרי 30 שניות שני הסקילים מותקנים אצלך, ו-Claude Code יזהה אותם בפעם הבאה שתפתח שיחה חדשה.

## הגדרה ראשונית

אחרי ההתקנה, יש שלב חד-פעמי של חיבור ל-Meta API:
- תיצור אפליקציה ב-`developers.facebook.com`
- תוציא טוקן (System User או 60-day user token)
- תמלא קובץ `.env`

ההוראות המפורטות נמצאות ב-[`meta-ads/references/setup.md`](./meta-ads/references/setup.md). זה לוקח 15-25 דקות בפעם הראשונה. אחרי זה לא תצטרך לעשות אותו שוב.

## איך זה עובד בפועל?

אחרי ההתקנה, אתה פותח שיחה עם Claude Code ושואל בעברית:

```
איך הקמפיינים שלי עבדו ב-30 הימים האחרונים?
```

```
תיצור לי קמפיין חדש לקורס שלי, יעד Conversions,
תקציב 100 שקל ליום, קהל יעד בעלי עסקים בישראל 30-55.
הקריאייטיב נמצא בתיקייה C:\creatives\new\.
תייצר את זה PAUSED.
```

```
תשכפל את הקמפיין "וובינר 14.5.26" — זהה אבל לתאריך 28.5.26,
התמונות החדשות בתיקייה C:\creatives\webinar_28-5\.
```

Claude יחליט אילו סקריפטים להפעיל, ירוץ עליהם, ויחזיר לך את התשובה בשפה שאתה כתבת.

## כללי בטיחות

הסקילים מבצעים פעולות אמיתיות מול חשבון המודעות שלך. הכלל הבסיסי:

> **כל פעולת כתיבה (הקפאה, שינוי תקציב, יצירה) דורשת אישור מפורש שלך בצ'אט לפני שהיא קורית.**

קרא את [`meta-ads/references/write-actions.md`](./meta-ads/references/write-actions.md) לפני שאתה מתחיל לעשות פעולות כתיבה.

**טוקנים הם כמו סיסמאות לחשבון המודעות שלך.** אל תשתף אותם, אל תשמור אותם ב-git ציבורי, ואל תשלח אותם בצ'אט/אימייל. הקובץ `.env` שאתה ממלא נמצא ב-`.gitignore` — אל תוציא אותו משם.

---

<a id="english"></a>

## What's in this repo?

Two Claude Code skills that work together to manage Meta ads (Facebook, Instagram, Click-to-WhatsApp) via natural-language prompts.

| Skill | Purpose |
|---|---|
| **[meta-ads](./meta-ads/)** | Main skill — read performance, run fatigue/anomaly analyses, create campaigns from scratch, pause, change budgets, duplicate. |
| **[meta-ads-campaign-cloner](./meta-ads-campaign-cloner/)** | Specialized skill — clone a winning campaign with new creatives, copy, or dates. |

Built for Claude Code on Windows / macOS / Linux. Uses the Meta Marketing API directly, no intermediate servers.

## Quick install

In a Claude Code session, just say:

```
Clone https://github.com/roeytt/meta-ads-toolkit and copy
the meta-ads and meta-ads-campaign-cloner folders into ~/.claude/skills/
```

Claude will run `git clone` and place the skills in your skills directory. Restart your Claude Code session and the skills will be available.

## First-time setup

You'll need to connect to Meta's API once:
- Create a Meta developer app
- Generate an access token (System User token or 60-day user token)
- Fill in a `.env` file

Detailed walkthrough: [`meta-ads/references/setup.md`](./meta-ads/references/setup.md). About 15-25 minutes the first time. Then you're set.

## License

MIT — see [LICENSE](./LICENSE).

## Author

**Roey Treister** — Meta ads instructor, runs the Hebrew course "פרסם זאת בעצמך" for Israeli business owners.

- GitHub: [@roeytt](https://github.com/roeytt)
