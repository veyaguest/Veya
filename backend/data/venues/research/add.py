"""כלי עזר למחקר: מוסיף ממצאים לקובץ candidates.jsonl.

קלט (stdin), שורה לכל מקום, מופרד ב-|:
  שם | עיר | כתובת | סוג | אתר | קיבולת | מקור(URL) | הערה | טלפון (רק מאתר רשמי)
שדה ריק = לא ידוע (נשמר כ-null). הקיבולת: "200" או "50-300".
הקובץ הוא יומן גולמי (append-only) — הניקוי והדדופ נעשים ב-build_dataset.py.
"""
import json, sys, datetime, pathlib

OUT = pathlib.Path(__file__).with_name("candidates.jsonl")
query = sys.argv[1] if len(sys.argv) > 1 else ""
today = datetime.date.today().isoformat()
raw_lines = sys.stdin.read().splitlines()
# יומן קלט גולמי — כדי שאפשר יהיה לשחזר/לתקן רשומה מהטקסט המקורי (ראו repair_2026_10_26.py).
with OUT.with_name("add_log.txt").open("a", encoding="utf-8") as lf:
    lf.write(f"### {today} | {query}\n" + "\n".join(raw_lines) + "\n")
n = 0
refs = {}  # "@S1=https://..." מגדיר קיצור למקור שחוזר בכמה שורות
with OUT.open("a", encoding="utf-8") as f:
    pending = []
    for line in raw_lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@") and "=" in line.split("|")[0]:
            k, v = line.split("=", 1); refs[k.strip()] = v.strip(); continue
        parts = [p.strip() for p in line.split("|")] + [""] * 9
        name, city, addr, kind, web, cap, src, note, phone = parts[:9]
        # הגנה מפני הזזת עמודה (הבאג של 26.10): URL/קיצור מחוץ לשדה המקור → עוצרים הכול.
        if any(x.startswith(("http", "@")) for x in (cap, note, phone)) or (src and not src.startswith(("http", "@"))):
            sys.exit(f"שורה לא תקינה (עמודות מוזזות?) — לא נשמר כלום: {line}")
        if not src:
            sys.exit(f"חסר מקור — כל רשומה חייבת מקור: {line}")
        if web and not web.startswith("http"):
            sys.exit(f"שדה האתר חייב להיות URL: {line}")
        if src.startswith("@") and src not in refs:
            sys.exit(f"קיצור מקור לא מוגדר {src}: {line}")
        src = refs.get(src, src)
        cmin = cmax = None
        if cap:
            if "-" in cap:
                a, b = cap.split("-", 1); cmin, cmax = int(a), int(b)
            else:
                cmax = int(cap)
        rec = {"name": name, "city": city or None, "address": addr or None, "kind": kind or None,
               "website": web or None, "capacity_min": cmin, "capacity_max": cmax,
               "source_url": src or None, "phone": phone or None, "note": note or None, "query": query, "found": today,
               "channel": "web_search"}
        pending.append(rec)
    for rec in pending:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n"); n += 1
print(f"+{n} -> {sum(1 for _ in OUT.open())} total")
