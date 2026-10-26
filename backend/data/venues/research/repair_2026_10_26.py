"""תיקון חד-פעמי (26.10.2026) לרשומות שנרשמו עם הזזת עמודה ב-add.py.

הבעיה: בשורות הקלט נכתב שדה ריק מיותר לפני המקור, ולכן ה-URL נשמר בשדה note,
ההערה בשדה phone, והטלפון (כשהיה) נחתך. התיקון: מזיזים חזרה, מפענחים קיצורי
מקור (@X) לפי הקבוצה שבה הוגדרו, ומשחזרים 8 טלפונים מאתרים רשמיים שנחתכו.
הקובץ המקורי נשמר לפני התיקון מחוץ למאגר.
"""
import json, pathlib

P = pathlib.Path(__file__).with_name("candidates.jsonl")
TA = "אולמות אירועים תל אביב/ירושלים/חיפה/ראשון"
GD = "פתח תקווה/חולון/בת ים/רמת גן/גבעתיים/בני ברק"
SH = "נתניה/השרון/רחובות-נס ציונה/אשדוד"
SO = "אשקלון/קריית גת/שדרות/נתיבות/אופקים/מודיעין/לוד/רמלה/חדרה-קיסריה"
NO = "צפון: עפולה/נוף הגליל/טבריה/ראש פינה/כרמיאל/עכו/נהריה/עמק יזרעאל"
JM = "בית שמש/מבשרת/הרי ירושלים/מעלה אדומים/גוש עציון/שומרון/מודיעין עילית"
UL = "ulam.co.il ירושלים עמוד 1 (בלי דפדוף — תנאי שימוש)"
SM = "בריתות/לופטים/מסעדות חדר פרטי/וילות"
BQ = 'בוטיק ת"א-יפו / גנים ירושלים / קטנים חיפה / שפלה'
GU = "גליל עליון/מערבי/כנרת/חוף הכרמל/באר שבע-גנים"
REFS = {
    (TA, "@H"): "https://halocation.co.il/loctaion/%D7%91%D7%AA%D7%9C-%D7%90%D7%91%D7%99%D7%91-%D7%99%D7%A4%D7%95/",
    (TA, "@EH"): "https://event-halls.co.il/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%91%D7%99%D7%A4%D7%95/",
    (TA, "@BT"): "https://www.britot.co.il/?page=tel_aviv_all_places",
    (TA, "@T"): "https://www.t.co.il/80-s1344-%D7%92%D7%A0%D7%99+%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D+/+%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%AA%D7%9C+%D7%90%D7%91%D7%99%D7%91.html",
    (TA, "@ME"): "https://mekomot-eruim.co.il/event-halls?city=Tel+Aviv",
    (TA, "@HF"): "https://www.hafakot.co.il/place/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%91%D7%99%D7%A4%D7%95/",
    (TA, "@J"): "https://www.ulam.co.il/listing-region/%D7%99%D7%A8%D7%95%D7%A9%D7%9C%D7%99%D7%9D/",
    (TA, "@GH"): "https://www.gallery279.co.il/",
    (TA, "@BK"): "https://www.britot.co.il/?page=krayot_places",
    (TA, "@RL"): "https://www.britot.co.il/?page=brit_rishon",
    (GD, "@PT"): "https://www.britot.co.il/?page=petah_tukva_places",
    (GD, "@HL"): "https://www.britot.co.il/?page=hulon_places",
    (GD, "@RG"): "https://rgcity.co.il/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%91%D7%A8%D7%9E%D7%AA-%D7%92%D7%9F/",
    (GD, "@RT"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%91%D7%A0%D7%99+%D7%91%D7%A8%D7%A7",
    (GD, "@DP"): "https://www.datipage.co.il/biz/search/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA+%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D,%D7%91%D7%A0%D7%99+%D7%91%D7%A8%D7%A7",
    (SH, "@NT"): "https://www.britot.co.il/?page=netanya_places",
    (SH, "@RTN"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%A0%D7%AA%D7%A0%D7%99%D7%94",
    (SH, "@SH"): "https://www.britot.co.il/?page=raanana_places",
    (SH, "@AS"): "https://ashdodnet.com/%D7%90%D7%99%D7%A0%D7%93%D7%A7%D7%A1/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%95%D7%92%D7%A0%D7%99-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D",
    (SO, "@MD"): "https://www.mdas.org.il/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-2/",
    (SO, "@KG"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%A7%D7%A8%D7%99%D7%99%D7%AA+%D7%92%D7%AA",
    (SO, "@NV"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%A0%D7%AA%D7%99%D7%91%D7%95%D7%AA",
    (NO, "@RA"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%A2%D7%A4%D7%95%D7%9C%D7%94",
    (NO, "@KR"): "https://www.karmieli.co.il/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA/",
    (JM, "@BS"): "https://www.hafakot.co.il/place/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA-%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%91%D7%91%D7%99%D7%AA-%D7%A9%D7%9E%D7%A9/",
    (JM, "@MV"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA+%D7%95%D7%92%D7%A0%D7%99+%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%9E%D7%91%D7%A9%D7%A8%D7%AA+%D7%A6%D7%99%D7%95%D7%9F",
    (JM, "@MA"): "https://rsrv.rest/he/maale-adumim",
    (JM, "@MI"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA+%D7%95%D7%92%D7%A0%D7%99+%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%9E%D7%95%D7%93%D7%99%D7%A2%D7%99%D7%9F+%D7%A2%D7%99%D7%9C%D7%99%D7%AA",
    (UL, "@U"): "https://www.ulam.co.il/listing-region/%D7%99%D7%A8%D7%95%D7%A9%D7%9C%D7%99%D7%9D/",
    (SM, "@BC"): "https://www.britot.co.il/?page=merkaz_restaurant",
    (SM, "@LT"): "https://www.rrr.co.il/lofts/Tel-Aviv.asp",
    (SM, "@JR"): "https://mekomot-eruim.co.il/restaurants-with-private-room?area=Jerusalem",
    (SM, "@VN"): "https://www.hafakot.co.il/place/%D7%95%D7%99%D7%9C%D7%95%D7%AA-%D7%9C%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%95%D7%99%D7%9C%D7%94-%D7%9C%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D-%D7%91%D7%A6%D7%A4%D7%95%D7%9F/",
    (BQ, "@TB"): "https://www.britot.co.il/?page=tel_aviv_all_places",
    (BQ, "@JG"): "https://mazaltov.walla.co.il/event-place/eventsgardens/jerusalem_area/",
    (BQ, "@HS"): "https://barbatmitzva.co.il/small-places-restaurants-for-events?area=Haifa",
    (BQ, "@SF"): "https://mazaltov.walla.co.il/event-place/eventsgardens/shfela/",
    (GU, "@KS"): "https://rotter.net/pro/%D7%97%D7%99%D7%A4%D7%95%D7%A9/%D7%90%D7%95%D7%9C%D7%9E%D7%95%D7%AA%20%D7%95%D7%92%D7%A0%D7%99%20%D7%90%D7%99%D7%A8%D7%95%D7%A2%D7%99%D7%9D/%D7%A7%D7%A8%D7%99%D7%99%D7%AA+%D7%A9%D7%9E%D7%95%D7%A0%D7%94",
}
# טלפונים שנחתכו — כולם הופיעו באתר הרשמי של המקום (לא בפורטל).
PHONES = {"ויטראז'": "08-9402020", "ממילא גן אירועים": "08-6990066", "אדמה ADAMA": "08-8565060",
          "Tres Events טרס": "073-7798661", "אולמי פאר": "04-6597478", "אצולת העמק": "04-6402026",
          "אידיליה אירועים במושבה": "052-8994454", "שרונית": "09-8949095"}

rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines() if l.strip()]
fixed = unresolved = 0
for r in rows:
    if r.get("channel") != "web_search" or r.get("source_url") or not (r.get("note") or "").startswith(("http", "@")):
        continue
    src = r["note"]
    if src.startswith("@"):
        src = REFS.get((r["query"], src))
        if not src:
            unresolved += 1
            print("UNRESOLVED", r["query"], r["note"], r["name"])
            continue
    r["source_url"], r["note"], r["phone"] = src, r.get("phone"), PHONES.get(r["name"])
    fixed += 1
P.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print("fixed", fixed, "unresolved", unresolved)

# שלב 2: בשלוש הקבוצות הראשונות (לפני שנוסף שדה הטלפון) ההערה עצמה נחתכה.
# משחזרים את ההערות שמשפיעות על סטטוס/סימון לבדיקה (מתוך יומן המחקר).
NOTES = {
    ("פוגאטה", "ראשון לציון"): "CLOSED: נסגר, במקומו אולמי לאו",
    ("אמדאו", "גבעתיים"): "UNSURE: עמוד אחד מציין שנסגרה",
    ("המוזיאון", "חולון"): "כתובת לא עקבית (הסתת 17/19)",
    ("טזורו Tesoro", "רמת השרון"): "עיר לא ודאית (רמת השרון/תל אביב)",
    ("וולקאן", "ירושלים"): "ייתכן אותו מתחם כמו אופוריה (גנרל קניג 39)",
    ("דברו איתי", "תל אביב-יפו"): "כמה כתובות במקור",
    ("128 אירועים", "תל אביב-יפו"): "רמת החייל",
    ("אנטריקוט ירושלים", "ירושלים"): "מסעדה + חדר פרטי + אולם",
    ("אלמוג", "חיפה"): "במתחם מלון ליאונרדו",
    ("סיאל Ciel", "חיפה"): "שני אולמות 250/500",
    ("ריה RIYA", "פתח תקווה"): "אזור התעשייה סגולה",
    ("סליה אירועים", "חולון"): "3 מתחמים",
    ("רנסאנס גן אירועים", "גבעתיים"): "שני אולמות",
    ("מנהטן אירועים", "רמת גן"): "מתחם הבורסה",
    ("Upper Events אפר", "רמת גן"): "מגדלי התאומים",
    ("אוהלי אברהם", "בני ברק"): "קריית הרצוג",
    ("אולם בית אשר", "בני ברק"): "מקור 2019 — פעילות לא נבדקה",
    ("אולם סאטמר בני ברק", "בני ברק"): "מקור 2019 — פעילות לא נבדקה",
    ("נרניה מרכז אירועים וקונגרסים", "באר שבע"): "נפתח 2009",
    ("הינומה באר שבע", "באר שבע"): "ליד התחנה המרכזית",
    ("ארי מרכז אירועים", "באר שבע"): "אתר רשמי",
}
rows = [json.loads(l) for l in P.read_text(encoding="utf-8").splitlines() if l.strip()]
restored = 0
for r in rows:
    n = NOTES.get((r["name"], r.get("city")))
    if n and r.get("note") != n:
        r["note"] = n
        restored += 1
P.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
print("notes restored", restored)
