import type { SettingRow, SettingValue } from '../../rulesApi'

/** שדה עריכה אחד להגדרה — מספר / כן-לא / בחירה. בלי שמירה עצמית. */
export function SettingControl({
  setting,
  value,
  disabled,
  onChange,
}: {
  setting: SettingRow
  value: SettingValue
  disabled?: boolean
  onChange: (v: SettingValue) => void
}) {
  if (setting.type === 'bool') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={Boolean(value)}
        aria-label={setting.label}
        className={`adm-switch${value ? ' is-on' : ''}`}
        disabled={disabled}
        onClick={() => onChange(!value)}
      >
        <span className="adm-switch-knob" />
      </button>
    )
  }
  if (setting.type === 'int') {
    const n = Number(value)
    const min = setting.min ?? -Infinity
    const max = setting.max ?? Infinity
    return (
      <span className="adm-stepper">
        <button type="button" className="adm-btn adm-btn-sm" disabled={disabled || n <= min} onClick={() => onChange(n - 1)} aria-label="פחות">
          −
        </button>
        <input
          type="number"
          className="adm-input adm-input-sm"
          value={n}
          min={setting.min ?? undefined}
          max={setting.max ?? undefined}
          disabled={disabled}
          aria-label={setting.label}
          onChange={(e) => {
            const v = Number(e.target.value)
            if (!Number.isNaN(v)) onChange(Math.min(max, Math.max(min, v)))
          }}
        />
        <button type="button" className="adm-btn adm-btn-sm" disabled={disabled || n >= max} onClick={() => onChange(n + 1)} aria-label="יותר">
          +
        </button>
        {setting.unit && <span className="adm-muted">{setting.unit}</span>}
      </span>
    )
  }
  if (setting.type === 'choice') {
    return (
      <select className="adm-input adm-input-sm" value={String(value)} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-label={setting.label}>
        {setting.choices.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
    )
  }
  return <span>{String(value)}</span>
}
