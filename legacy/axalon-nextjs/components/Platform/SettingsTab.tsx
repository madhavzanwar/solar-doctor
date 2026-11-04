'use client'

import { RefreshCw, Save, SlidersHorizontal } from 'lucide-react'
import { useSettings } from '@/components/Platform/hooks/useSettings'
import { AlertTestPanel } from '@/components/Platform/AlertTestPanel'
import { FusionCalibrationPanel } from '@/components/Platform/FusionCalibrationPanel'
import { useAuth } from '@/components/Platform/AuthGate'
import { UsersSharingPanel } from '@/components/Platform/UsersSharingPanel'

function Chip({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'info' | 'ok' | 'crit' | 'muted'
}) {
  return (
    <div className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{value}</span>
    </div>
  )
}

function SettingField({
  group,
  fieldKey,
  value,
  onChange,
}: {
  group: string
  fieldKey: string
  value: unknown
  onChange: (group: string, key: string, value: unknown) => void
}) {
  // Nested dicts (rare, e.g. severity_colors) — render as read-only JSON, simplest path
  if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
    return (
      <label className="setting-row wide">
        <span>{fieldKey}</span>
        <textarea
          rows={3}
          value={JSON.stringify(value, null, 2)}
          onChange={(e) => {
            try {
              onChange(group, fieldKey, JSON.parse(e.target.value))
            } catch {
              /* keep raw value as text on bad JSON */
            }
          }}
        />
      </label>
    )
  }
  if (typeof value === 'boolean') {
    return (
      <label className="setting-row toggle">
        <span>{fieldKey}</span>
        <input
          type="checkbox"
          checked={value}
          onChange={(e) => onChange(group, fieldKey, e.target.checked)}
        />
      </label>
    )
  }
  if (typeof value === 'number') {
    return (
      <label className="setting-row">
        <span>{fieldKey}</span>
        <input
          type="number"
          step="any"
          value={value}
          onChange={(e) => onChange(group, fieldKey, Number(e.target.value))}
        />
      </label>
    )
  }
  if (Array.isArray(value)) {
    return (
      <label className="setting-row wide">
        <span>{fieldKey}</span>
        <input
          type="text"
          value={value.join(', ')}
          onChange={(e) =>
            onChange(
              group,
              fieldKey,
              e.target.value
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean)
                .map((s) => (Number.isFinite(Number(s)) ? Number(s) : s)),
            )
          }
        />
      </label>
    )
  }
  return (
    <label className="setting-row">
      <span>{fieldKey}</span>
      <input
        type="text"
        value={String(value ?? '')}
        onChange={(e) => onChange(group, fieldKey, e.target.value)}
      />
    </label>
  )
}

export function SettingsTab() {
  const {
    settings,
    loading: settingsBusy,
    dirty: settingsDirty,
    message: settingsMsg,
    update: updateSetting,
    save: saveSettings,
  } = useSettings()
  const { mode, isAdmin } = useAuth()
  // settings.yaml drives the detector for every customer: admin-only with accounts on.
  const canEditSettings = mode !== 'users' || isAdmin

  return (
    <section className="tab-section">
      <header className="cmdbar">
        <div className="cmdbar-titles">
          <div className="eyebrow">
            <SlidersHorizontal size={13} />
            platform/config/settings.yaml
          </div>
          <h1>Settings</h1>
        </div>
        <div className="chips">
          <Chip
            label="Status"
            value={settingsDirty ? 'Unsaved' : 'In sync'}
            tone={settingsDirty ? 'crit' : 'ok'}
          />
          <Chip
            label="Groups"
            value={String(settings ? Object.keys(settings).length : 0)}
            tone="muted"
          />
        </div>
      </header>

      {/* Both POST to admin-only endpoints in users mode; hide them from everyone else. */}
      {canEditSettings && (
        <>
          <AlertTestPanel />
          <FusionCalibrationPanel />
        </>
      )}

      {settingsBusy && !settings && <div className="empty">Loading settings…</div>}
      {settings && (
        <div className="settings-grid">
          {Object.entries(settings).map(([group, entries]) => (
            <section className="panel" key={group}>
              <div className="panel-head">
                <div>
                  <div className="panel-title">{group}</div>
                  <p>{Object.keys(entries || {}).length} field(s)</p>
                </div>
              </div>
              <div className="settings-fields">
                {Object.entries(entries || {}).map(([key, value]) => (
                  <SettingField
                    key={key}
                    group={group}
                    fieldKey={key}
                    value={value}
                    onChange={updateSetting}
                  />
                ))}
              </div>
            </section>
          ))}

          {canEditSettings ? (
            <div className="settings-actions">
              <span className="save-msg">{settingsMsg}</span>
              <button
                type="button"
                className="primary"
                disabled={!settingsDirty || settingsBusy}
                onClick={saveSettings}
              >
                {settingsBusy ? <RefreshCw size={17} /> : <Save size={17} />}
                Save changes
              </button>
            </div>
          ) : (
            <div className="settings-actions">
              <span className="save-msg">Read-only — only an admin can change settings.</span>
            </div>
          )}
        </div>
      )}

      {isAdmin && (
        <>
          <header className="cmdbar">
            <div className="cmdbar-titles">
              <div className="eyebrow">accounts · project access · share links</div>
              <h1>Users &amp; sharing</h1>
            </div>
          </header>
          <UsersSharingPanel />
        </>
      )}
    </section>
  )
}
