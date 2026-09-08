# VEYA — Design Tokens

> **מסמך נגזר.** נוצר אוטומטית מ-`public/veya-site.css` על ידי
> `scripts/build-token-doc.mjs`. אין לערוך אותו ביד — ערכו את
> `content/brand-layer.css` (טוקנים חדשים) והריצו `npm run build:brand`.

מקור האמת של הטוקנים הוא ה-CSS. המסמך הזה קיים כדי שאפשר יהיה לקרוא
אותם בלי לפתוח גיליון של 327 כללים.

## צבע — רקע ומשטח

| טוקן | ערך | הערה |
|---|---|---|
| `--ivory` | `#fbf6ee` |  |
| `--ivory-2` | `#f6efe2` |  |
| `--cream` | `#ffffff` |  |
| `--ink` | `#17130d` |  |
| `--ink-2` | `#211b12` |  |

## צבע — טקסט

| טוקן | ערך | הערה |
|---|---|---|
| `--charcoal` | `#2b2620` |  |
| `--body` | `#4a4438` |  |
| `--muted` | `#6a6252` |  |
| `--cream-text` | `#f5efe2` |  |

## צבע — מותג

| טוקן | ערך | הערה |
|---|---|---|
| `--gold` | `#c9a227` |  |
| `--gold-light` | `#e4c96b` |  |
| `--gold-deep` | `#836a26` |  |

## צבע — גבול

| טוקן | ערך | הערה |
|---|---|---|
| `--line` | `#e5dec9` |  |

## צבע — סמנטי

| טוקן | ערך | הערה |
|---|---|---|
| `--success` | `#1f7a45` | 4.97:1 — טקסט הצלחה |
| `--warning` | `#a1541a` | 5.14:1 — נבדל מהזהב בכוונה |
| `--error` | `#8f3226` | 6.80:1 — טקסט שגיאה |
| `--error-bg` | `#fbeae7` |  |
| `--error-border` | `#dda99f` | חוזק מ-#e6b9b1 כדי שהגבול ייראה |
| `--green` | `#2f9e5f` |  |

## רדיוס

| טוקן | ערך | הערה |
|---|---|---|
| `--radius-sm` | `8px` |  |
| `--radius-md` | `14px` |  |
| `--radius-lg` | `18px` |  |
| `--radius-xl` | `28px` |  |
| `--radius-pill` | `999px` |  |

## צל

| טוקן | ערך | הערה |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(43, 38, 32, 0.05)` |  |
| `--shadow-md` | `0 14px 30px -22px rgba(43, 38, 32, 0.40)` |  |
| `--shadow-lg` | `0 26px 60px -30px rgba(43, 38, 32, 0.38)` |  |

## תנועה

| טוקן | ערך | הערה |
|---|---|---|
| `--motion-fast` | `180ms` |  |
| `--motion-normal` | `420ms` |  |
| `--motion-slow` | `620ms` |  |
| `--ease-out` | `cubic-bezier(0.23, 1, 0.32, 1)` |  |
| `--ease-in-out` | `cubic-bezier(0.77, 0, 0.175, 1)` |  |

## גופן

| טוקן | ערך | הערה |
|---|---|---|
| `--font-body` | `'Assistant', system-ui, -apple-system, 'Segoe UI', sans-serif` |  |
| `--font-display` | `'Frank Ruhl Libre', Georgia, 'Times New Roman', serif` |  |
| `--font-num` | `'Assistant', system-ui, sans-serif` |  |

## כללים

1. **אין hex בקומפוננטה.** צבע שנושא משמעות עובר דרך טוקן סמנטי.
2. **`--green` הוא לאייקון בלבד** — 3.16:1 מספיק לגרפיקה ולא לטקסט.
   טקסט הצלחה משתמש ב-`--success`.
3. **סולם הרדיוס סגור** לחמישה ערכים. אין להוסיף ערך שישי בלי סיבה.
4. **תנועה על transform/opacity בלבד**, ותמיד מתחת ל-`prefers-reduced-motion`.
