/**
 * תמונת המצב לצילום בדף הנחיתה — ``DashboardPage`` האמיתי של VEYA,
 * על נתוני אירוע שנמצא באמצע הדרך. אין כאן שום ציור של מסך: רק
 * השרת מוחלף (``demoDashboard``), והמסך הוא זה של המוצר.
 */
import { DashboardPage } from '../components/DashboardPage'
import { installDashboardDemo } from './demoDashboard'
import './demo.css'

installDashboardDemo()

export function DemoDashboard() {
  return (
    <div className="demo-stage demo-stage-plain">
      <DashboardPage />
    </div>
  )
}
