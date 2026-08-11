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
    confirm: 'אישור',
    close: 'סגירה',
    delete: 'מחיקה',
    edit: 'עריכה',
    add: 'הוספה',
    remove: 'הסרה',
    retry: 'ניסיון חוזר',
    done: 'סיום',
    back: 'חזרה',
    loading: 'טוען…',
    saving: 'שומר…',
    working: 'רגע…',
  },

  // ========================================================================
  //  errors — הודעות שגיאה מרוכזות (מוצגות למשתמש דרך setError/toast).
  //  מפתחות נפרדים גם לניסוחים דומים עד סימן פיסוק אחד — כי הטקסט המדויק
  //  נמסר על-ידי הקומפוננטה שלכדה את השגיאה, וכל שינוי הוא שינוי UX.
  // ========================================================================
  errors: {
    // מסך הזוג — משותפים
    loadGenericRetry: 'לא הצלחנו לטעון כרגע, ננסה שוב',
    // ProfileDialog
    profileSaveFailed: 'לא הצלחנו לשמור את השינוי, נסו שוב',
    profilePasswordFailed: 'לא הצלחנו לעדכן את הסיסמה, נסו שוב',
    profileExportFailed: 'לא הצלחנו לייצא את המידע, נסו שוב',
    profileDeleteFailed: 'לא הצלחנו למחוק את החשבון, נסו שוב',
    profileLogoutAllFailed: 'לא הצלחנו להוציא אתכם מכל המכשירים, נסו שוב',
    // ReconsentModal
    consentSaveFailed: 'לא הצלחנו לשמור את האישור, נסו שוב',
    // AuthPage
    authGoogleNoToken: 'לא התקבל טוקן מגוגל',
    authGoogleNotConfigured: 'התחברות עם גוגל אינה מוגדרת כרגע',
    authGoogleSupabase: 'Supabase לא קיבל את הטוקן של גוגל',
    authGoogleFailed: 'התחברות עם גוגל נכשלה',
    authLoginFailed: 'לא הצלחנו להתחבר. בדקו את הפרטים ונסו שוב.',
    // EventControls / OnboardingWizard
    eventCreateFailed: 'לא הצלחנו ליצור את האירוע, נסו שוב',
    imageTypeError: 'אפשר להעלות קובץ תמונה בלבד',
    imageSize3MB: 'התמונה גדולה מדי — עד 50MB',
    onboardingHostsMissing: (label: string) => `נשמח לדעת קודם את שמות ${label}`,
    onboardingHostAMissing: (label: string) => `נשמח לדעת קודם את ${label}`,
    // EventMembersDialog
    membersLoadFailed: 'לא הצלחנו לטעון את רשימת הגישה',
    membersAddFailed: 'לא הצלחנו להוסיף גישה',
    membersUpdateFailed: 'לא הצלחנו לעדכן הרשאות',
    membersRemoveFailed: 'לא הצלחנו להסיר את הגישה',
    // ConfirmPage — המוזמן!
    confirmLoadFailed: 'לא הצלחנו לטעון את ההזמנה. נסו לרענן את הדף.',
    confirmSubmitFailed: 'לא הצלחנו לשלוח את התשובה. נסו שוב.',
    // HallPage
    hallLoadFailed: 'לא הצלחנו לטעון את מפת האולם, ננסה שוב',
    hallNotesLoadFailed: 'לא הצלחנו לקרוא את ההערות, ננסה שוב',
    hallChoiceSaveFailed: 'לא הצלחנו לשמור את הבחירה, נסו שוב',
    hallImageTypeError: 'יש לבחור קובץ תמונה (JPG/PNG).',
    hallImage4MB: 'התמונה גדולה מדי (עד 4MB). נסו תמונה קטנה יותר.',
    hallAutoSaveFailed: 'לא הצלחנו לשמור אוטומטית — נמשיך לנסות',
    hallSeatingFailed: 'לא הצלחנו לסדר כרגע, ננסה שוב',
    // הערה: hallSeatingCollision ו-hallSeatingNoRoom הוסרו — התנגשות מוצגת
    // עכשיו בכרטיס דוח מפורט (strings.hall.conflictTitle) עם רשימת ההפרות
    // בפועל, במקום הודעת שגיאה כללית שלא אמרה למשתמש מה נכשל ואצל מי.
    // MessageBuilder
    messagesLoadFailed: 'לא הצלחנו לטעון את ההודעות, ננסה שוב',
    messageSaveFailed: 'לא הצלחנו לשמור, נסו שוב',
    messagesLibraryLoadFailed: 'לא הצלחנו לטעון את ספריית ההודעות',
    // RsvpPage
    rsvpStateLoadFailed: 'לא הצלחנו לטעון את המצב, ננסה שוב',
    rsvpDataLoadFailed: 'לא הצלחנו לטעון את נתוני אישורי ההגעה, ננסה שוב',
    rsvpTemplateSaveFailed: 'לא הצלחנו לשמור את התבנית, נסו שוב',
    rsvpInvitationsSendFailed: 'לא הצלחנו לשלוח את ההזמנות, נסו שוב',
    rsvpRemindersSendFailed: 'לא הצלחנו לשלוח את התזכורות, נסו שוב',
    rsvpAnswerUpdateFailed: 'לא הצלחנו לעדכן את התשובה, נסו שוב',
    // RsvpTimeline
    timelineLoadFailed: 'לא הצלחנו לטעון את היומן, ננסה שוב',
    // AutomationQueueTab
    queueLoadFailed: 'לא הצלחנו לטעון את התור, ננסה שוב',
    queueSendFailed: 'לא הצלחנו לשלוח, נסו שוב',
    // AutomationRulesTab
    rulesLoadFailed: 'לא הצלחנו לטעון את החוקים, ננסה שוב',
    ruleNameRequired: 'צריך לתת שם לחוק',
    ruleSaveFailed: 'לא הצלחנו לשמור את החוק, נסו שוב',
    ruleUpdateFailed: 'לא הצלחנו לעדכן את החוק, נסו שוב',
    ruleDeleteFailed: 'לא הצלחנו למחוק את החוק, נסו שוב',
    // AutomationTemplatesTab
    templatesLoadFailed: 'לא הצלחנו לטעון את התבניות, ננסה שוב',
    templateNameRequired: 'צריך לתת שם לתבנית',
    templateSaveFailed: 'לא הצלחנו לשמור את התבנית, נסו שוב',
    templateDeleteFailed: 'לא הצלחנו למחוק את התבנית, נסו שוב',
    // AdminApp
    adminDashboardLoadFailed: 'לא הצלחנו לטעון את לוח הבקרה, ננסה שוב',
    adminUserLoadFailed: 'לא הצלחנו לטעון את פרטי המשתמש, ננסה שוב',
    adminUserSaveFailed: 'לא הצלחנו לשמור את הפרטים, נסו שוב',
    adminPasswordResetFailed: 'לא הצלחנו לאפס את הסיסמה, נסו שוב',
    adminActionFailed: 'לא הצלחנו לבצע את הפעולה, נסו שוב',
    adminDeleteFailed: 'לא הצלחנו למחוק, נסו שוב',
    adminImpersonateFailed: 'לא הצלחנו להתחבר בשם המשתמש, נסו שוב',
    adminUsersLoadFailed: 'לא הצלחנו לטעון את רשימת המשתמשים, ננסה שוב',
    adminEventsLoadFailed: 'לא הצלחנו לטעון את רשימת האירועים, ננסה שוב',
    adminEventEnterFailed: 'לא הצלחנו להיכנס לאירוע, נסו שוב',
    adminVenuesLoadFailed: 'לא הצלחנו לטעון את רשימת האולמות, ננסה שוב',
    adminVenueDeleteFailed: 'לא הצלחנו למחוק את האולם, נסו שוב',
    adminVenueNameRequired: 'שם האולם לא יכול להיות ריק',
    adminVenueSaveFailed: 'לא הצלחנו לשמור את האולם, נסו שוב',
    adminVenueMergeTargetRequired: 'יש לבחור אולם יעד למיזוג',
    adminVenueMergeFailed: 'לא הצלחנו למזג, נסו שוב',
    adminAuditLoadFailed: 'לא הצלחנו לטעון את היומן, ננסה שוב',
    // AdminPage (VEYA workflow admin)
    adminAccountCreateFailed: 'לא הצלחנו ליצור את החשבון, נסו שוב',
    adminSaveFailedRetry: 'לא הצלחנו לשמור, נסו שוב',
    adminDeleteFailedRetry: 'לא הצלחנו למחוק, נסו שוב',
    adminAddFailedRetry: 'לא הצלחנו להוסיף, נסו שוב',
    adminDefaultsLoadFailed: 'לא הצלחנו לטעון את ברירות המחדל, ננסה שוב',
    // HallPage — assignNote (עוזר הושבה, לא setError)
    hallRecommendFailed: 'לא הצלחנו להמליץ כרגע',
    hallAssignFailed: 'לא הצלחנו לשבץ כרגע',
    // RsvpPage — סטטוסים דרך callbacks
    rsvpSendGenericRetry: 'לא הצלחנו לשלוח כרגע, ננסה שוב',
    rsvpGuestsLoadFailed: 'לא הצלחנו לטעון את רשימת המוזמנים',
    rsvpSendPartialFail: 'השליחה הסתיימה — חלק נכשלו',
  },

  // ========================================================================
  //  toasts — הודעות הצלחה חיוביות שמוצגות דרך setNote / notification.
  // ========================================================================
  toasts: {
    profileUpdated: 'הפרטים עודכנו',
    passwordUpdated: 'הסיסמה עודכנה. מכשירים אחרים נותקו.',
    messageSaved: 'שמרנו את ההודעה ✓',
    messageLoaded: 'הודעה נטענה מהספרייה — אפשר לערוך ואז לשמור',
    templateCreated: 'התבנית נוצרה ✓',
    templateSaved: 'התבנית נשמרה ✓',
    passwordResetNote: 'איפוס סיסמה עצמאי בדרך — בינתיים כתבו לנו ונעזור.',
    adminUserDetailsSaved: 'הפרטים נשמרו',
    invitationsSent: 'ההזמנות נשלחו',
  },

  // ========================================================================
  //  messages — עורך ההודעות למוזמנים (MessageBuilder) וספריית הנוסחים.
  //  כל טקסט שהזוג רואה במסך הזה חי כאן, לא בתוך הקומפוננטה.
  // ========================================================================
  messages: {
    titleFull: 'ההודעות שלכם',
    titleInvitation: 'ההזמנה שלכם',
    subtitleFull:
      'בחרו נוסח מוכן מהספרייה, או ערכו אותו בעצמכם. כך זה ייראה למוזמנים ב-WhatsApp.',
    subtitleInvitation:
      'בחרו נוסח הזמנה מוכן מהספרייה, או כתבו את שלכם. כך זה ייראה למוזמנים ב-WhatsApp.',
    emptyState: 'ההודעות ייווצרו אוטומטית ברגע שתפעילו את מסלול אישורי ההגעה.',

    // כרטיס בחירת ההודעה
    pickerTitle: 'איזו הודעה עורכים',
    // כרטיס העורך
    editorTitle: 'נוסח ההודעה',
    editorPlaceholder: 'כתבו כאן את ההודעה למוזמנים…',
    libraryButton: 'נוסחים מוכנים',
    libraryButtonFor: (kind: string) => `נוסחים מוכנים ל${kind}`,
    libraryButtonHint: 'עשרות נוסחים בכל סגנון, עם כל הפרטים של האירוע כבר בפנים',
    editorHint: 'רוצים לערוך בעצמכם? אפשר גם ישירות כאן',
    save: 'שמירת ההודעה',
    saving: 'שומרים…',
    unsaved: 'יש שינויים שלא נשמרו',
    all: 'הכול',

    // תצוגה מקדימה
    previewTitle: 'כך זה ייראה למוזמן',
    previewEmpty: 'אין עדיין נוסח להודעה',
    previewNote:
      'שורה שכל הפרטים שבה עדיין ריקים לא תישלח — היא נעלמת מההודעה מעצמה.',
    previewNow: 'עכשיו',

    // ספריית הנוסחים
    libraryTitle: 'ספריית הנוסחים',
    libraryTitleFor: (cat: string) => `נוסחים ל${cat}`,
    libraryLoading: 'טוענים נוסחים…',
    librarySearch: 'חיפוש בנוסחים…',
    libraryCategory: 'קטגוריה',
    libraryStyle: 'סגנון',
    libraryNoResults: 'לא נמצאו נוסחים מתאימים לסינון',
    libraryPickPrompt: 'בחרו נוסח מהרשימה כדי לראות תצוגה מקדימה',
    libraryUse: 'שימוש בנוסח הזה',
    libraryPreviewOf: (name: string) => `תצוגה מקדימה — ${name}`,
    close: 'סגירה',

    // ---- כרטיס "מעקב אחרי המוזמנים" — מצב ההודעות שנשלחו (לא RSVP) ----
    statusCard: {
      title: 'מעקב אחרי המוזמנים',
      subtitle:
        'אנחנו עוקבים אחרי מצב ההודעות שנשלחו ומעדכנים אתכם מי קיבל ומי דורש טיפול.',
      loadError: 'לא הצלחנו לטעון את מצב ההודעות כרגע. ננסה שוב',
      sent: '✓ נשלחו',
      delivered: '✓✓ נמסרו למכשיר',
      read: '👁 נקראו',
      failed: '⚠️ לא נמסרו',
      invalidNumber: '📵 מספר לא זמין',
      blocked: '🔒 חסומים',
      queued: '⏳ ממתינים לשליחה',
      readNote: 'סטטוס "נקראו" מגיע רק כשהמוזמן לא כיבה אישורי קריאה בוואטסאפ.',
    },
  },

  // ========================================================================
  //  legal — טקסטים משפטיים (Cookies, Reconsent, Footer, AuthPage checkboxes).
  //  נפרד ממש כי שגיאה כאן = חשיפה רגולטורית.
  // ========================================================================
  legal: {
    // CookieBanner (legal/03-cookie-policy.md §3)
    cookieAriaLabel: 'הסכמת Cookies',
    cookieBody:
      'אנחנו משתמשים בעוגיות הכרחיות לתפעול השירות (כמו שמירת החיבור\n              שלך). עוגיות נוספות (סטטיסטיקה/שיפור) יופעלו רק באישורך המפורש.\n              פרטים ב',
    cookiePolicyLink: 'מדיניות ה-Cookies',
    cookieAcceptAll: 'קבל הכל',
    cookieRejectNonEssential: 'דחה לא-הכרחיים',
    cookieCustomize: 'הגדרות מותאמות',
    cookieEssentialLabel: 'עוגיות הכרחיות (חובה לתפעול השירות)',
    cookieAnalyticsLabel: 'עוגיות סטטיסטיקה/שיפור (כרגע אינן בשימוש בפועל)',
    cookieSavePrefs: 'שמירת ההעדפות',
    cookieBack: 'חזרה',
    // ReconsentModal
    reconsentTitle: 'עדכנו את התנאים שלנו',
    reconsentBody:
      'תנאי השימוש ומדיניות הפרטיות של VEYA עודכנו מאז שאישרתם אותם לאחרונה.\n          כדי להמשיך להשתמש במערכת, יש לאשר את הגרסה העדכנית:',
    reconsentTermsLink: 'תנאי השימוש',
    reconsentPrivacyLink: 'מדיניות הפרטיות',
    reconsentSubmit: 'אני מאשר/ת וממשיך/ה',
    // Footer
    footerLinksLabel: 'קישורים משפטיים',
    footerTerms: 'תנאי שימוש',
    footerPrivacy: 'מדיניות פרטיות',
    footerCookies: 'מדיניות Cookies',
    footerAccessibility: 'הצהרת נגישות',
    footerContact: 'יצירת קשר',
    footerCopy: '© VEYA · מערכת לניהול אירועים',
    // AuthPage — checkboxes המשפטיים (Frontend #2 בטסקליסט)
    authAgreePrefix: 'אני מאשר/ת את',
    authAgreeAnd: 'ואת',
    authTermsLink: 'תנאי השימוש',
    authPrivacyLink: 'מדיניות הפרטיות',
    authMarketingOptIn: 'אני מעוניין/ת לקבל עדכונים מ-VEYA',
    authGoogleAgreePrefix: 'בהתחברות עם גוגל אני מאשר/ת את',
  },


  dashboard: {
    loadError: 'לא הצלחנו לטעון כרגע. ננסה שוב',
    saveError: 'לא הצלחנו לשמור את הפרטים. נסו שוב',
    imageTypeError: 'אפשר להעלות קובץ תמונה בלבד',
    imageSizeError: 'התמונה גדולה מדי — עד 50MB',
    venuePlaceholder: 'שם האולם',
    venueAddressPlaceholder: 'כתובת האולם (לניווט בהזמנות)',
    dateLabel: 'תאריך האירוע',
    timeLabel: 'שעת האירוע',
    commitLabel: 'יום ההתחייבות לאולם',
    commitExplain:
      'כמה ימים לפני האירוע צריך למסור לאולם מספר סופי? ביום הזה כל אישורי ההגעה נסגרים, ולוח הזמנים שלהם נבנה לאחור סביבו.',
    commitLockedValue: (n: number | string) => `${n} ימים לפני האירוע`,
    commitLockedNote:
      '🔒 כבר בחרתם — הבחירה נעולה כי לוח הזמנים כבר בנוי סביבה.',
    commitSelectPlaceholder: 'בחרו מספר ימים…',
    commitOptionLabel: (n: number) => `${n} ימים לפני האירוע`,
    commitWarn: 'שימו לב: אחרי השמירה אי אפשר לשנות את הבחירה.',
    imageLabel: 'תמונת ההזמנה',
    imageAlt: 'תצוגה מקדימה של ההזמנה',
    imageRemove: 'הסרת התמונה',
    imageUpload: '⬆ העלאת תמונת הזמנה',
    imageUploadHint: 'זו התמונה שתישלח למוזמנים בהזמנה',
    venueFallback:
      'עוד לא הזנתם את פרטי האירוע — בואו נשלים את השמות, האולם והתאריך',
    editButton: '✎ עריכת פרטים',
    rsvpTitle: 'תמונת מצב — אישורי הגעה',
    rsvpSub: (confirmed: number, total: number) =>
      `${confirmed} אישרו הגעה מתוך ${total}`,
    loadingData: 'טוען נתונים…',
    segConfirmed: 'אישרו הגעה',
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
    // ---- Dashboard v2 — מחרוזות לעיצוב מחדש ----
    countdownToday: 'האירוע היום!',
    countdownDays: 'ימים',
    countdownHours: 'שעות',
    countdownMinutes: 'דקות',
    countdownSeconds: 'שניות',
    countdownAriaLabel: (days: number, hours: number, minutes: number) =>
      `נותרו ${days} ימים, ${hours} שעות ו-${minutes} דקות לאירוע`,
    rsvpSummary: (confirmed: number, total: number) =>
      `${confirmed} מתוך ${total} מוזמנים אישרו הגעה`,
    donutCardTitle: 'סטטוס אישורי הגעה',
    donutResponseBadge: (pct: number) => `${pct}% ענו`,
    // ---- מד ההושבה החצי-עגול (Gauge) — מחליף את הדונאט המלא ----
    gaugeLabel: 'אישורי הגעה',
    gaugeStatusMaybe: 'מתלבטים',
    gaugeStatusDeclined: 'לא מגיעים',
    kpiConfirmed: 'מגיעים',
    kpiPending: 'ממתינים',
    invitePlaceholder: 'העלו תמונת הזמנה',
    // ---- באנר "יש מוזמנים בלי הזמנה" — מעל עדכוני אישורי ההגעה ----
    inviteBannerTitle: (count: number) =>
      `💌 עוד ${count} מוזמנים נשארו ללא הזמנה`,
    inviteBannerDesc:
      'זה הזמן להשלים את השליחה ולהמשיך להתקדם עם הכנות האירוע.',
    inviteBannerCta: 'שליחת הזמנות',
    // ---- Feed עדכוני אישורי הגעה — במקום כרטיסי הסטטיסטיקה הכפולים ----
    feedTitle: 'עדכוני אישורי הגעה',
    feedEmpty: 'עדיין אין עדכונים — ברגע שמוזמנים יתחילו לענות, תראו כאן כל עדכון בזמן אמת.',
    feedConfirmed: (name: string) => `${name} אישר/ה הגעה`,
    feedDeclined: (name: string) => `${name} לא מגיע/ה`,
    feedMaybe: (name: string) => `${name} מתלבט/ת`,
    // ---- "סידורי הושבה בלי כאב הראש" — הכרטיס המרכזי בעמודה הימנית ----
    seatingHelperTitle: 'סידורי הושבה בלי כאב הראש',
    seatingHelperDesc:
      'כמעט כל זוג מוצא את עצמו בימים שלפני האירוע שובר את הראש על סידורי ההושבה. במקום להעביר אנשים בין שולחנות במשך שעות, מספיק להגדיר קבוצות והעדפות — ואנחנו נבנה לכם הושבה חכמה בלחיצה אחת.',
    seatingHelperSteps: [
      'הוספת מוזמנים',
      'יצירת קבוצות',
      'הוספת הערות והעדפות הושבה',
      'מעבר לסידור הושבה חכם',
    ],
    seatingHelperCta: 'התחילו להכין את ההושבה',
    seatingHelperCtaReady: 'מעבר לסידור הושבה חכם',
    // ---- מוקאפ WhatsApp/אייפון — כיתוב ההזמנה מתחת לתמונה בבועה ----
    inviteCaptionNamed: (celebration: string, names: string) =>
      `הנכם מוזמנים ל${celebration} של ${names}`,
    inviteCaptionGeneric: (celebration: string) =>
      `הנכם מוזמנים ל${celebration} שלנו`,
    emptyTitle: 'הכול מתחיל מכאן',
    emptyDesc: 'הוסיפו מוזמנים כדי לראות את תמונת המצב.',
    emptyCta: 'הוספת מוזמנים',
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
    deleteTitle: 'הסרת מוזמן',
    deleteConfirm: (name: string) => `להסיר את ${name} מהרשימה?`,
    deleteConfirmButton: 'כן, להסיר',
    searchPlaceholder: 'חיפוש לפי שם או טלפון…',
    importMenuButton: '⬆ ייבוא מוזמנים',
    pasteButton: '📋 הדבקה מרשימה קיימת',
    notesButton: '⭐ העדפות קבוצה',
    uploadButton: '📄 ייבוא מקובץ Excel / CSV',
    contactsButton: '👤 ייבוא מאנשי קשר',
    closeForm: 'סגירת הטופס',
    addGuestButton: '+ הוספת מוזמן',
    dupSuffix: (n: number) => ` (${n} כבר היו אצלכם)`,
    importedToast: (created: number, dupSuffix: string) =>
      `הוספנו ${created} מוזמנים לרשימה ✓${dupSuffix}`,
    summary: (total: number, totalPeople: number, confirmedPeople: number, guestsLabel = 'מוזמנים') =>
      `${total} ${guestsLabel} · ${totalPeople} אנשים הוזמנו · ${confirmedPeople} אישרו הגעה`,
    colFullName: 'שם מלא',
    colPhone: 'טלפון',
    colSide: 'צד',
    colGroup: 'קבוצה',
    colCount: 'כמות',
    colRsvp: 'אישור הגעה',
    colInviteStatus: 'סטטוס הזמנה',
    colTable: 'שולחן',
    colNotes: 'הערה פנימית',
    colSeatingNotes: 'הערות הושבה',
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
    // שני שדות הערות נפרדים. ההפרדה קיימת כדי שהערה תפעולית ("צריך לחזור
    // אליו") לא תתפרש בטעות כאילוץ ישיבה — רק השדה השני מגיע למנוע.
    notesFieldLabel: 'הערה פנימית',
    notesFieldPlaceholder: 'לדוגמה: דיברנו איתו, צריך לחזור אליו',
    notesFieldHint: 'לשימושכם בלבד. לא משפיעה על סידור ההושבה.',
    seatingNotesLabel: 'הערות הושבה',
    seatingNotesPlaceholder: 'לדוגמה: לא לשבת ליד משפחת לוי · קרוב לבר · רחוק מהרעש',
    seatingNotesHint: 'רק מה שכתוב כאן נלקח בחשבון בסידור ההושבה.',

    // באנר "מצאנו הערות שנראות כמו העדפות ישיבה"
    noteSplitTitle: (n: number) =>
      n === 1
        ? 'מצאנו הערה אחת שנראית כמו העדפת ישיבה'
        : `מצאנו ${n} הערות שנראות כמו העדפות ישיבה`,
    noteSplitBody:
      'הן שמורות כהערה פנימית, ולכן לא נלקחות בחשבון בסידור ההושבה. אפשר להעביר אותן לשדה "הערות הושבה".',
    noteSplitPreview: 'הצגת ההערות',
    noteSplitHide: 'הסתרה',
    noteSplitApply: 'העברה להערות הושבה',
    noteSplitDismiss: 'לא עכשיו',
    noteSplitDone: (n: number) => `${n} הערות הועברו להערות הושבה`,
    noteSplitError: 'לא הצלחנו להעביר כרגע. נסו שוב',
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
        icon: '👥',
        title: 'קבוצות מסתדרות מעצמן',
        text: 'אנחנו מציעים לכם לאחד משפחות וחברים לקבוצות — אתם רק מאשרים.',
      },
      {
        icon: '🪑',
        title: 'הושבה בקליק',
        text: 'כשהכול מוכן, VEYA מסדרת את השולחנות לפי הקשרים וההעדפות שלכם.',
      },
    ],
    onboardingTitle: 'חסכו לעצמכם שעות של כאב ראש לפני האירוע',
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
    rowIssueNoCount: 'חסרה כמות',
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
    colCountDetected: 'כמות שהוזנה',
    colCountTotal: 'סה"כ אנשים',
    backToEdit: 'חזרה לעריכת הטקסט',

    // ContactsImportDialog
    contactsTitle: 'ייבוא מאנשי קשר',
    contactsHint:
      'בחרו אנשי קשר מהטלפון — נמשוך את השם והטלפון שלהם אוטומטית. תוכלו לבדוק, לערוך או להסיר לפני שמוסיפים אותם לרשימה. זמין כרגע בדפדפן Chrome באנדרואיד בלבד.',
    contactsUnsupported:
      'הדפדפן הזה לא תומך בבחירת אנשי קשר. אפשר להשתמש ב"הדבקה מרשימה קיימת" או בייבוא מאקסל במקום.',
    contactsPickButton: 'בחירת אנשי קשר',
    contactsPicking: 'פותחים את אנשי הקשר…',
    contactsPickError: 'לא הצלחנו לפתוח את אנשי הקשר. נסו שוב.',
    contactsReviewHint:
      'בדקו את הרשימה לפני ההוספה — אפשר לערוך שם וטלפון או להסיר מי שלא צריך. שום דבר לא נוסף עד שתלחצו על הוספה.',
    contactsHiddenDuplicates: (n: number) =>
      `${n} אנשי קשר כבר נמצאים ברשימת המוזמנים ולא הוצגו.`,
    contactsEmptyAfterDedup:
      'כל אנשי הקשר שנבחרו כבר קיימים ברשימת המוזמנים.',
    backToPick: 'בחירה מחדש',

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

  // ==========================================================================
  //  hall — מסך סידור ההושבה ומפת האולם.
  // ==========================================================================
  hall: {
    // "הושבה בקליק" — הפעולה המרכזית של המסך.
    oneClickButton: 'הושבה בקליק',
    oneClickRunning: 'מסדרים…',
    oneClickHint:
      'סידור חכם לפי הקבוצות, הערות ההושבה, האילוצים ומבנה האולם — בלחיצה אחת.',
    fillEmptyButton: 'השלמת מי שללא שולחן',
    fillEmptyHint: 'משבץ רק את מי שעדיין אין לו שולחן. אף אחד מהמשובצים לא זז.',

    // סיכום אחרי הרצה
    doneTitle: 'הסידור מוכן',
    doneSummary: (people: number, tables: number) =>
      `${people} מוזמנים שובצו ב-${tables} שולחנות`,

    // דרישה 5 — הודעת ההתנגשות, בניסוח שנקבע מראש.
    conflictTitle:
      'יש התנגשות בין העדפות הישיבה. אפשר לשנות אילוצים או להריץ את הסידור מחדש.',
    conflictHint: 'הסידור לא נשמר. אלה הדברים שלא הצלחנו לפתור:',
    conflictMore: (n: number) =>
      n === 1 ? 'ועוד מוזמן אחד' : `ועוד ${n} מוזמנים באותו מצב`,

    // דרישה 6 — ביטול ושחזור.
    undoButton: '↩ החזרת הסידור הקודם',
    undoRunning: 'מחזירים…',
    undoHint: 'מחזיר את המוזמנים למקומות שהיו לפני ההושבה בקליק.',
    undoDone: (n: number) =>
      n === 1 ? 'מוזמן אחד הוחזר למקומו הקודם' : `${n} מוזמנים הוחזרו למקומות הקודמים`,
    undoError: 'לא הצלחנו להחזיר את הסידור הקודם. נסו שוב',

    // דרישה 7 — לשונית ההגדרות.
    settingsTab: 'הגדרות הושבה',
    constraintsTitle: 'אילוצים והעדפות',
    constraintsHint:
      'אנחנו קוראים את הערות ההושבה והופכים אותן לכללים — מי לשבת עם מי, וממי להרחיק.',
    constraintsRecheck: 'בדיקת ההערות',
    constraintsChecking: 'בודקים…',
    constraintsSummary: (guests: number, found: number, pending: number) =>
      `נבדקו ${guests} · ${found} העדפות זוהו · ${pending} ממתינות להבהרה`,
    constraintsNonePending: 'אין הבהרות ממתינות ✓',
    clarificationQuestion: (who: string, what: string, target: string) =>
      `${who} ביקש/ה ${what} "${target}" — למי הכוונה?`,
    clarificationNone: 'אף אחד מהם',

    // סיבוב שולחן — גרירת הידית מעל השולחן, בדיוק כמו אלמנטי המפה (בר וכו')
    rotationLabel: 'זווית השולחן',

    // סרגל הפעולות הצף שמופיע מיד עם בחירת שולחן על המפה — בלי לפתוח חלון.
    tableDetails: 'פרטי שולחן',
    duplicateTable: 'שכפול שולחן',
    deleteTable: 'מחיקת שולחן',
    // כפתור-גשר: כשהגיליון נפתח מרשימת השולחנות/מהחיפוש (לא מהקשה על
    // המפה), עדיין אין שולחן "נבחר" על המפה. סוגר את הגיליון ובוחר אותו,
    // כדי שידית הסיבוב וסרגל הפעולות יופיעו מיד.
    selectOnMap: 'בחירה על המפה לסיבוב',
  },
}
