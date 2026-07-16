/**
 * מקור אמת יחיד לכל הטקסטים בעברית שהזוג רואה במערכת.
 *
 * למה זה כאן ולא בתוך הקומפוננטות: כדי שאפשר יהיה לשלוט על השפה של VEYA
 * ממקום אחד — לבדוק עקביות מונחים, לתקן ניסוח, לבדוק אורך טקסט לפני
 * שהוא פוגע בעיצוב — בלי לחפש בין עשרות קבצי קומפוננטות.
 *
 * חשוב: הקובץ הזה גדל בהדרגה, מסך אחר מסך, כחלק משדרוג הטקסטים של
 * VEYA (ראו CLAUDE.md). קומפוננטה שעדיין לא עברה ריכוז ממשיכה להחזיק
 * את הטקסטים שלה בקוד עצמו עד שמגיע תורה.
 *
 * עקרונות הניסוח: פנייה בלשון רבים לזוג ("אתם"/"שלכם"), עברית מדוברת-
 * מקצועית וחמה בלי ניסוחים מתורגמים ("נשמח אם תוכלו לשקול"), כתיב מלא,
 * ומספרים בספרות. מילון מונחים אחיד: "מוזמנים" (לא "אורחים"), "אישור
 * הגעה", "שולחן/מקומות ישיבה", "מפת האולם", "סידור ההושבה", "תזכורת",
 * "הזמנה", "צד", "קבוצה", "ממתינים לתשובה", "לא מגיעים".
 */

export const strings = {
  common: {
    save: 'שמירה',
    cancel: 'ביטול',
  },
  dashboard: {
    loadError: 'לא הצלחנו לטעון כרגע. ננסה שוב',
    saveError: 'לא הצלחנו לשמור את הפרטים. נסו שוב',
    imageTypeError: 'אפשר להעלות קובץ תמונה בלבד',
    imageSizeError: 'התמונה גדולה מדי — עד 3MB',
    groomPlaceholder: 'שם החתן',
    bridePlaceholder: 'שם הכלה',
    venuePlaceholder: 'שם האולם',
    venueAddressPlaceholder: 'כתובת האולם (לניווט בהזמנות)',
    dateLabel: 'תאריך האירוע',
    timeLabel: 'שעת האירוע',
    commitLabel: 'יום ההתחייבות לאולם',
    commitExplain:
      'כמה ימים לפני החתונה צריך למסור לאולם מספר סופי? ביום הזה כל אישורי ההגעה נסגרים, ולוח הזמנים שלהם נבנה לאחור סביבו.',
    commitLockedValue: (n: number | string) => `${n} ימים לפני האירוע`,
    commitLockedNote:
      '🔒 כבר בחרתם — הבחירה נעולה כי לוח הזמנים כבר בנוי סביבה.',
    commitSelectPlaceholder: 'בחרו מספר ימים…',
    commitOptionLabel: (n: number) => `${n} ימים לפני האירוע`,
    commitWarn: 'שימו לב: אחרי השמירה אי אפשר לשנות את הבחירה.',
    imageLabel: 'תמונת ההזמנה',
    imageAlt: 'תצוגה מקדימה של ההזמנה',
    imageBubbleLabel: 'הזמנה לחתונה',
    imageRemove: 'הסרת התמונה',
    imageUpload: '⬆ העלאת תמונת הזמנה',
    imageUploadHint: 'זו התמונה שתישלח למוזמנים בהזמנה',
    inviteImgAlt: 'הזמנה לחתונה',
    coupleFallback: 'החתונה שלנו',
    venueFallback:
      'עוד לא הזנתם את פרטי האירוע — בואו נשלים את שמות בני הזוג, האולם והתאריך',
    editButton: '✎ עריכת פרטים',
    rsvpTitle: 'תמונת מצב — אישורי הגעה',
    rsvpSub: (confirmed: number, total: number) =>
      `${confirmed} אישרו הגעה מתוך ${total}`,
    loadingData: 'טוען נתונים…',
    segConfirmed: 'אישרו הגעה',
    segMaybe: 'לא החליטו',
    segDeclined: 'לא מגיעים',
    segPending: 'ממתינים לתשובה',
    centerLabel: 'אישרו הגעה',
    legendMaybe: 'לא החליטו (אולי)',
    statTotalGuests: 'מוזמנים ברשימה',
    statTotalPeople: 'סך האנשים',
    statConfirmed: 'אישרו הגעה',
    statResponseRate: 'שיעור מענה',
    clarificationsAlert: (n: number) =>
      `⚠ יש ${n} הבהרות שממתינות לכם. נשלים אותן יחד במסך "מפת אולם והושבה".`,
    bySide: 'לפי צד',
    byGroup: 'לפי קבוצה',
    seatingTitle: 'הושבה',
    tablesAssigned: 'שולחנות שובצו',
    guestsSeated: 'מוזמנים משובצים',
    invitationsSent: 'הזמנות שנשלחו',
    auditTitle: 'יומן פעילות ואבטחה',
    auditSub: 'תיעוד הפעולות הרגישות האחרונות: שליחות, עדכונים וגישה לקישורים.',
    auditLabels: {
      send_invitations: 'שליחת הזמנות',
      send_reminders: 'שליחת תזכורות',
      update_event: 'עדכון פרטי אירוע',
      confirm_submit: 'אישור הגעה מהקישור',
      confirm_invalid_token: '⚠ ניסיון גישה לקישור לא תקין',
    } as Record<string, string>,
  },
}
