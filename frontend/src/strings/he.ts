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
    // ---- סקשן "הכנה להושבה" (מוביל את הזוג לקראת ההושבה החכמה) ----
    prep: {
      title: 'הכנה להושבה',
      intro:
        'עוד כמה שלבים קטנים – ו-VEYA תדאג לכל השאר.\nנכיר את האורחים שלכם, נבין את ההעדפות והקבוצות, ואז תוכלו ליצור סידור הושבה חכם בלחיצה אחת.',
      progress: (done: number, total: number) =>
        `${done} מתוך ${total} שלבים הושלמו`,
      stateNotStarted: 'לא התחיל',
      stateInProgress: 'בתהליך',
      stateDone: 'הושלם',
      steps: [
        { title: 'חלוקה לצד חתן או כלה', desc: 'שיוך כל אורח לצד המתאים.' },
        {
          title: 'יצירת קבוצות',
          desc: 'משפחה, חברים, עבודה או כל קבוצה אחרת.',
        },
        {
          title: 'העדפות והערות',
          desc: 'מי חייב לשבת יחד, מי עדיף שלא, וכל הערת ישיבה חשובה.',
        },
        { title: 'סקירה ואישור', desc: 'בדיקה אחרונה לפני יצירת ההושבה.' },
      ],
      reviewSummary: (o: {
        total: number
        groom: number
        bride: number
        groups: number
        prefs: number
      }) =>
        `${o.total} מוזמנים · ${o.groom} בצד החתן · ${o.bride} בצד הכלה · ${o.groups} קבוצות · ${o.prefs} העדפות`,
      cta: '✨ הושבה בקליק',
      ctaHint:
        'VEYA תיצור עבורכם סידור הושבה חכם בהתאם לכל ההעדפות שהגדרתם.',
      ctaLockedHint: 'השלימו את השלבים למעלה כדי ליצור את ההושבה.',
    },
    reserve: {
      title: 'רזרבה וניהול יום האירוע',
      manage: 'ניהול',
      freeSeats: 'מקומות פנויים',
      reserveTables: 'שולחנות רזרבה',
      seated: 'משובצים',
      unseated: 'ללא שולחן',
    },
    auditTitle: 'פעילות אחרונה',
    auditSub: 'מה קרה לאחרונה באירוע שלכם — שליחות, אישורים ועדכונים.',
    auditLabels: {
      send_invitations: 'שליחת הזמנות',
      send_reminders: 'שליחת תזכורות',
      update_event: 'עדכון פרטי אירוע',
      confirm_submit: 'אישור הגעה מהקישור',
      confirm_invalid_token: '⚠ ניסיון גישה לקישור לא תקין',
    } as Record<string, string>,
  },
  guests: {
    // GuestsPage
    loadError: 'לא הצלחנו לטעון את הרשימה, ננסה שוב',
    deleteError: 'לא הצלחנו להסיר, נסו שוב',
    deleteConfirm: (name: string) => `להסיר את ${name} מהרשימה?`,
    searchPlaceholder: 'חיפוש לפי שם או טלפון…',
    pasteButton: '📋 הדבקת רשימה',
    notesButton: '⭐ העדפות קבוצה',
    uploadButton: '⬆ העלאת קובץ אקסל',
    closeForm: 'סגירת הטופס',
    addGuestButton: '+ הוספת מוזמן',
    dupSuffix: (n: number) => ` (${n} כבר היו אצלכם)`,
    importedToast: (created: number, dupSuffix: string) =>
      `הוספנו ${created} מוזמנים לרשימה ✓${dupSuffix}`,
    summary: (total: number, totalPeople: number, confirmedPeople: number) =>
      `${total} מוזמנים · ${totalPeople} אנשים הוזמנו · ${confirmedPeople} אישרו הגעה`,
    colFullName: 'שם מלא',
    colPhone: 'טלפון',
    colSide: 'צד',
    colGroup: 'קבוצה',
    colCount: 'כמות',
    colRsvp: 'אישור הגעה',
    colInviteStatus: 'סטטוס הזמנה',
    colTable: 'שולחן',
    colNotes: 'הערות',
    deleteRow: 'מחיקה',
    editRow: 'עריכה',
    groupButton: '👥 צור קבוצה',
    emptySearch: 'לא נמצאו מוזמנים שתואמים לחיפוש.',
    emptyList: 'הרשימה עדיין ריקה. הוסיפו מוזמן ראשון או ייבאו קובץ אקסל כדי להתחיל.',
    loadingRows: 'טוען…',
    loadMore: (shown: number, total: number) => `טעינת עוד (${shown} מתוך ${total})`,

    // AddGuestForm
    saveErrorGeneric: 'לא הצלחנו לשמור, נסו שוב',
    fullNameLabel: 'שם מלא *',
    fullNamePlaceholder: 'לדוגמה: דני כהן',
    phoneLabel: 'טלפון *',
    phonePlaceholder: '050-123-4567',
    sideLabel: 'צד',
    groupLabelText: 'קבוצה',
    newGroupOption: '➕ קבוצה חדשה…',
    newGroupPlaceholder: 'שם הקבוצה, למשל: חברים מהצבא',
    partySizeLabel: 'כמות אנשים',
    isChildLabel: 'ילד/ה',
    notesFieldLabel: "הערות (העדפות ישיבה וכו')",
    notesFieldPlaceholder: 'לדוגמה: לא לשבת ליד משפחת לוי',
    saving: 'שומר…',
    submitAdd: 'הוספת מוזמן',
    submitEdit: 'שמירת שינויים',

    // GuestTimelineModal
    timelineKindLabels: {
      invitation: 'הזמנה נשלחה',
      reminder: 'תזכורת נשלחה',
      pre_event: 'הודעה לפני האירוע',
      thank_you: 'הודעת תודה',
      reply: 'תשובת המוזמן',
      custom: 'הודעה נשלחה',
    } as Record<string, string>,
    timelineReplied: 'המוזמן הגיב',
    timelineLoadError: 'שגיאה בטעינת ציר הזמן',
    timelineTitle: (name: string) => `ציר זמן — ${name}`,
    closeX: 'סגירה ✕',
    currentStatus: 'סטטוס נוכחי:',
    timelineEmpty: 'עדיין לא נשלחו הודעות למוזמן הזה.',

    // ImportDialog
    importFileError: 'לא הצלחנו לקרוא את הקובץ. ודאו שזה קובץ אקסל תקין.',
    importAddError: 'לא הצלחנו להוסיף את הרשימה, נסו שוב',
    importTitle: 'העלאת קובץ אקסל',
    readingFile: 'רגע, קוראים את הקובץ…',
    importSummaryPrefix: (total: number) => `נמצאו ${total} שורות:`,
    validCount: (n: number) => `${n} תקינות`,
    invalidCount: (n: number) => `${n} עם בעיה (לא נוסיף אותן)`,
    colRowNumber: 'שורה',
    colStatus: 'מצב',
    rowValid: 'תקין',
    importing: 'מייבא…',
    importCount: (n: number) => `ייבוא ${n} מוזמנים`,

    // OnboardingDialog
    onboardingPoints: [
      {
        icon: '📋',
        title: 'מדביקים רשימה — וזהו',
        text: 'רשימה מ-WhatsApp, מאקסל או מכל מקום. VEYA מזהה לבד שם, טלפון וכמות.',
      },
      {
        icon: '✨',
        title: 'קבוצות מסתדרות מעצמן',
        text: 'אנחנו מציעים לכם לאחד משפחות וחברים לקבוצות — אתם רק מאשרים.',
      },
      {
        icon: '🎉',
        title: 'הושבה בקליק',
        text: 'כשהכול מוכן, VEYA מסדרת את השולחנות לפי הקשרים וההעדפות שלכם.',
      },
    ],
    onboardingTitle: 'חסכו לעצמכם שעות של כאב ראש לפני החתונה',
    onboardingSub:
      'ניהול המוזמנים והושבה הם החלק הכי מלחיץ. VEYA כאן כדי לעשות אותו פשוט — צעד אחר צעד, בלי גיליונות מסובכים.',
    onboardingCta: 'בואו נתחיל',

    // GroupNotesPanel
    notesLoadError: 'לא הצלחנו לטעון כרגע, ננסה שוב',
    notesSaveError: 'לא הצלחנו לשמור, נסו שוב',
    notesTitle: 'העדפות קבוצה',
    notesHint:
      'לכל קבוצה אפשר לרשום העדפה קצרה — למשל "רחוק מהרעש" או "קרוב לרחבה". נשמור אותה לכל חברי הקבוצה כדי לעזור בסידור ההושבה.',
    notesEmpty: 'עדיין אין קבוצות. הוסיפו מוזמנים ושייכו אותם לקבוצות כדי להגדיר העדפות.',
    notesInputPlaceholder: 'למשל: רחוק מהרעש',
    notesSaved: 'שמרנו ✓',
    notesDone: 'סיום',
    groupCount: (n: number) => `${n} מוזמנים`,

    // GroupSuggestions
    suggestionCreateError: 'לא הצלחנו ליצור את הקבוצה. נסו שוב.',
    suggestionCreatedToast: (groupName: string, updated: number) =>
      `נוצרה קבוצת '${groupName}' עם ${updated} מוזמנים ✓`,
    suggestionCreating: 'יוצר…',
    suggestionCreateGroup: 'צור קבוצה',
    suggestionNotNow: 'לא עכשיו',

    // PasteImportDialog
    rowIssueNoName: 'חסר שם',
    rowIssueNoPhone: 'חסר טלפון',
    rowIssueBadPhone: 'טלפון לא תקין',
    rowIssueDuplicate: 'כפילות',
    pasteParseError: 'לא הצלחנו לפענח את הרשימה. נסו שוב.',
    pasteImportError: 'לא הצלחנו להוסיף את הרשימה, נסו שוב',
    pasteTitle: 'הדבקת רשימת מוזמנים',
    pasteHint:
      'הדביקו כאן רשימה מ-WhatsApp, מאקסל או מכל מקום — שורה לכל מוזמן. אנחנו נזהה לבד את השם, הטלפון וכמות האנשים.',
    pasteAreaPlaceholder:
      'לדוגמה:\nיוסי כהן 052-1234567\nמשפחת לוי 5 אנשים 050-123-4567\nדנה מזרחי 054 987 6543 (2)',
    parsing: 'מפענח…',
    parseButton: 'פענוח הרשימה',
    pasteReviewHint:
      'הכנו עבורכם את הרשימה. מומלץ לעבור ולוודא שאין טעויות בשם, בטלפון או בכמות. סמנו אילו שורות לייבא.',
    pasteSelectedSummary: (selected: number, total: number) =>
      `נבחרו לייבוא ${selected} מתוך ${total} שורות`,
    selectAll: 'סמן הכל',
    clearAll: 'נקה בחירה',
    colImport: 'ייבוא',
    backToEdit: 'חזרה לעריכת הטקסט',

    // CreateGroupDialog — יצירת קבוצה ושיוך מוזמנים
    createGroupTitle: 'יצירת קבוצה חדשה',
    createGroupHint:
      'תנו שם לקבוצה (למשל "חברים מהצבא" או "משפחת כהן"), וסמנו מי שייך אליה. אפשר להשתמש בזה כדי לשמור קבוצות יחד בהושבה.',
    createGroupNameLabel: 'שם הקבוצה',
    createGroupNamePlaceholder: 'למשל: חברים מהצבא',
    createGroupPickHint: 'בחרו את המוזמנים שישויכו לקבוצה:',
    createGroupSelected: (n: number) => `${n} נבחרו`,
    createGroupSave: 'שמירת הקבוצה',
    createGroupSaving: 'שומר…',
    createGroupNoName: 'רשמו שם לקבוצה',
    createGroupNoGuests: 'בחרו לפחות מוזמן אחד',
    createGroupError: 'לא הצלחנו לשמור את הקבוצה, נסו שוב',
    createGroupSavedToast: (name: string, n: number) =>
      `נוצרה קבוצת '${name}' עם ${n} מוזמנים ✓`,
    createGroupEmpty: 'אין עדיין מוזמנים. הוסיפו מוזמנים כדי ליצור קבוצה.',
    createGroupLoading: 'טוען מוזמנים…',
  },
}
