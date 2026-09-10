import './VeyaLoader.css'

type LoaderSize = 'sm' | 'md' | 'lg'

/**
 * גדלים אחידים לכל המערכת:
 *  - sm (18px): טעינה בתוך כפתור או פעולה קטנה
 *  - md (32px): טעינה בתוך אזור תוכן
 *  - lg (64px): מסך טעינה מרכזי / מסך טעינה מלא
 * אפשר גם להעביר מספר פיקסלים מפורש כשצריך גודל ביניים.
 */
const SIZE_PX: Record<LoaderSize, number> = { sm: 18, md: 32, lg: 64 }

interface VeyaLoaderProps {
  /** 'sm' | 'md' | 'lg' או מספר פיקסלים. ברירת מחדל: 'md'. */
  size?: LoaderSize | number
  /** טקסט ל-aria-label (מוקרא למשתמשי קורא-מסך). ברירת מחדל: "טוען". */
  label?: string
  /** display:inline-flex — לשימוש בתוך כפתור או שורת טקסט. */
  inline?: boolean
  /** aria-hidden בלבד, בלי role — כשה-loader יושב בתוך אזור שכבר מכריז על טעינה (role="status"). */
  decorative?: boolean
  /** מחלקה נוספת ל-span העוטף. */
  className?: string
}

/**
 * VeyaLoader — אנימציית הטעינה האחידה והממותגת של VEYA: הלוגו העגול הקיים
 * מסתובב חלק ב-360° (linear, ~1.4s). CSS בלבד, ללא dependency.
 *
 * זו שכבת UI בלבד — היא לא מנהלת state של טעינה. מציגים אותה רק כשבאמת
 * מתבצעת טעינה, במקום ספינר גנרי קיים.
 */
export function VeyaLoader({
  size = 'md',
  label = 'טוען',
  inline = false,
  decorative = false,
  className = '',
}: VeyaLoaderProps) {
  const px = typeof size === 'number' ? size : SIZE_PX[size]
  const a11y = decorative
    ? { 'aria-hidden': true as const }
    : { role: 'status' as const, 'aria-live': 'polite' as const, 'aria-label': label }

  return (
    <span
      className={`veya-loader${inline ? ' veya-loader--inline' : ''}${className ? ` ${className}` : ''}`}
      {...a11y}
    >
      <img
        src="/logo_nobg.png"
        alt=""
        aria-hidden="true"
        width={px}
        height={px}
        className="veya-loader-logo"
        draggable={false}
      />
    </span>
  )
}
