import { useEffect, useState } from 'react'

/**
 * מחזיר האם שאילתת מדיה מתקיימת כרגע, ומתעדכן כשהיא משתנה.
 *
 * למה hook ולא CSS בלבד: יש מקומות שבהם ההבדל בין מובייל לדסקטופ אינו
 * *סידור* של אותו DOM אלא **מה בכלל מרונדר** — למשל בעורך האולם, שבו
 * בטלפון הקנבס והפאנל מחליפים זה את זה (מסך אחד בכל רגע), ואילו בדסקטופ
 * שניהם קיימים במקביל. CSS לא יכול להחזיר אלמנט שלא רונדר.
 *
 * ``matchMedia`` ולא ``resize`` — הדפדפן מודיע רק כשהתשובה באמת השתנתה,
 * במקום עשרות אירועים בזמן גרירת חלון.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches,
  )

  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = () => setMatches(mq.matches)
    mq.addEventListener('change', onChange)
    onChange()
    return () => mq.removeEventListener('change', onChange)
  }, [query])

  return matches
}

/**
 * נקודת המעבר של עורך האולם ממודל מגע למודל עכבר.
 *
 * 1024px ולא 760: בין 760 ל-1024 (טאבלט לרוחב) יש מספיק רוחב לפאנל צדדי
 * אבל הקלט עדיין מגע — ושם מודל המגע הוא הנכון. הפיצול הוא לפי סוג
 * האינטראקציה, לא רק לפי מספר פיקסלים.
 */
export const HALL_DESKTOP_QUERY = '(min-width: 1024px) and (pointer: fine)'
