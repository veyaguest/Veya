import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * רשת ביטחון גלובלית: אם קומפוננטה כלשהי קורסת ברינדור (שגיאה לא צפויה),
 * מציגים מסך VEYA מעוצב במקום מסך לבן ריק. הנתונים עצמם לא נפגעים —
 * הם שמורים בשרת, לא בזיכרון של הדף — ורענון פשוט מחזיר את המשתמש לפעולה.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('VEYA — שגיאה לא צפויה ברינדור:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" dir="rtl">
          <div className="error-boundary-card">
            <div className="error-boundary-logo">V E Y A</div>
            <h1>משהו השתבש</h1>
            <p>אל דאגה, המידע שלכם נשמר. נסו לטעון את הדף מחדש.</p>
            <button
              type="button"
              className="btn-primary"
              onClick={() => window.location.reload()}
            >
              טעינה מחדש
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
