import { Icon, type IconKind } from './Icon'

export type AIStatus =
  | 'ok' | 'over' | 'under' | 'revised' | 'stale'
  | 'ready' | 'watching' | 'listed' | 'vault'

export type AIGroup = 'needs-action' | 'monitoring' | 'settled'

interface StatusConfig {
  label: string
  iconKind: IconKind
  colorVar: string
}

interface GroupConfig {
  label: string
  iconKind: IconKind
  colorVar: string
}

export function getAIGroup(status: AIStatus): AIGroup {
  switch (status) {
    case 'over':
    case 'under':
    case 'stale':
    case 'revised':
      return 'needs-action'
    case 'watching':
    case 'ready':
      return 'monitoring'
    case 'ok':
    case 'listed':
    case 'vault':
      return 'settled'
  }
}

function getStatusConfig(status: AIStatus): StatusConfig {
  switch (status) {
    case 'ok':      return { label: 'On strategy',       iconKind: 'sparkle',   colorVar: 'var(--hd-accent)' }
    case 'over':    return { label: 'Overpriced',         iconKind: 'arrowDown', colorVar: 'var(--hd-red)'    }
    case 'under':   return { label: 'Below market',       iconKind: 'arrowUp',   colorVar: 'var(--hd-amber)'  }
    case 'revised': return { label: 'Bot revised',        iconKind: 'bot',       colorVar: 'var(--hd-blue)'   }
    case 'stale':   return { label: 'Stale',              iconKind: 'flag',      colorVar: 'var(--hd-red)'    }
    case 'ready':   return { label: 'Ready to list',      iconKind: 'flag',      colorVar: 'var(--hd-accent)' }
    case 'watching':return { label: 'Watching for peak',  iconKind: 'sparkle',   colorVar: 'var(--hd-blue)'   }
    case 'listed':  return { label: 'Listed on eBay',     iconKind: 'tag',       colorVar: 'var(--hd-amber)'  }
    case 'vault':   return { label: 'Vault',              iconKind: 'wallet',    colorVar: 'var(--hd-sub)'    }
  }
}

function getGroupConfig(group: AIGroup): GroupConfig {
  switch (group) {
    case 'needs-action': return { label: 'Needs action', iconKind: 'bot',     colorVar: 'var(--hd-red)'    }
    case 'monitoring':   return { label: 'Monitoring',   iconKind: 'sparkle', colorVar: 'var(--hd-blue)'   }
    case 'settled':      return { label: 'Settled',      iconKind: 'sparkle', colorVar: 'var(--hd-accent)' }
  }
}

interface AIBadgeProps {
  status: AIStatus
  showLabel?: boolean
  size?: 'sm' | 'lg'
}

export function AIBadge({ status, showLabel = false, size = 'sm' }: AIBadgeProps) {
  const statusConfig = getStatusConfig(status)
  const group = getAIGroup(status)
  const groupConfig = getGroupConfig(group)
  const iconSize = size === 'lg' ? 16 : 12
  const px = size === 'lg' ? 28 : 20

  const displayColor = showLabel ? statusConfig.colorVar : groupConfig.colorVar
  const displayIcon = showLabel ? statusConfig.iconKind : groupConfig.iconKind

  return (
    <span
      title={statusConfig.label}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        color: displayColor,
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        whiteSpace: 'nowrap',
        padding: showLabel ? '3px 8px 3px 6px' : 0,
        borderRadius: 999,
        background: showLabel
          ? `color-mix(in srgb, ${displayColor} 15%, transparent)`
          : 'transparent',
      }}
    >
      <span
        style={{
          width: px,
          height: px,
          borderRadius: 999,
          background: `color-mix(in srgb, ${displayColor} 15%, transparent)`,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon kind={displayIcon} size={iconSize} color={displayColor} strokeWidth={1.6} />
      </span>
      {showLabel && <span>{statusConfig.label}</span>}
    </span>
  )
}
