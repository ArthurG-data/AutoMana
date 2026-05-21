import type { ToastMsg } from '../../lib/useToast'

const containerStyle: React.CSSProperties = {
  position: 'fixed',
  bottom: '1.5rem',
  right: '1.5rem',
  display: 'flex',
  flexDirection: 'column',
  gap: '0.5rem',
  zIndex: 9999,
  pointerEvents: 'none',
}

const toastStyle = (type: 'success' | 'error'): React.CSSProperties => ({
  background: type === 'success' ? 'var(--hd-accent, #22c55e)' : 'var(--hd-red, #ef4444)',
  color: '#fff',
  padding: '0.5rem 1rem',
  borderRadius: '6px',
  fontSize: '13px',
  fontWeight: 600,
  boxShadow: '0 2px 10px rgba(0,0,0,0.35)',
  letterSpacing: '0.01em',
})

export function ToastContainer({ toasts }: { toasts: ToastMsg[] }) {
  if (toasts.length === 0) return null
  return (
    <div style={containerStyle}>
      {toasts.map((t) => (
        <div key={t.id} style={toastStyle(t.type)}>
          {t.message}
        </div>
      ))}
    </div>
  )
}
