import type { FC } from 'react';
import { hapticLight } from '../utils/haptics';

export type Tab = 'dashboard' | 'favorites' | 'alerts' | 'agent' | 'settings';

interface Props {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
  alertCount: number;
  favoriteCount: number;
}

const IconMarket: FC<{ active: boolean }> = ({ active }) => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={active ? 2 : 1.75} strokeLinecap="round" strokeLinejoin="round">
    {/* Ascending trend line */}
    <polyline points="2,17 8.5,10.5 13,14.5 22,5" />
    {/* Arrow head at top-right */}
    <polyline points="17,5 22,5 22,10" />
    {/* X-axis baseline */}
    <line x1="2" y1="20" x2="22" y2="20" strokeOpacity={0.35} />
  </svg>
);

const IconFavorites: FC<{ active: boolean }> = ({ active }) => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={active ? 2 : 1.75} strokeLinecap="round" strokeLinejoin="round">
    {/* Bookmark body */}
    <path d="M6 3h12a1 1 0 011 1v16.5l-7-3.5-7 3.5V4a1 1 0 011-1z" />
    {/* Star inside bookmark (small, centered at 12,11) */}
    <polygon points="12,7.2 13.1,10.2 16.2,10.2 13.7,12 14.6,15 12,13.2 9.4,15 10.3,12 7.8,10.2 10.9,10.2" />
  </svg>
);

const IconAlerts: FC<{ active: boolean }> = ({ active }) => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={active ? 2 : 1.75} strokeLinecap="round" strokeLinejoin="round">
    {/* Bell body */}
    <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" />
    {/* Clapper */}
    <path d="M13.73 21a2 2 0 01-3.46 0" />
  </svg>
);

const IconAgent: FC<{ active: boolean }> = ({ active }) => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={active ? 2 : 1.75} strokeLinecap="round" strokeLinejoin="round">
    <rect x="5" y="7" width="14" height="11" rx="3" />
    <path d="M9 7V5a3 3 0 016 0v2" />
    <circle cx="9.5" cy="12.5" r="1" />
    <circle cx="14.5" cy="12.5" r="1" />
    <path d="M10 16h4" />
    <path d="M3 12h2M19 12h2" />
  </svg>
);

const IconSettings: FC<{ active: boolean }> = ({ active }) => (
  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth={active ? 2 : 1.75} strokeLinecap="round" strokeLinejoin="round">
    {/* Center circle */}
    <circle cx="12" cy="12" r="3" />
    {/* Gear ring */}
    <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
  </svg>
);

const TABS: { id: Tab; label: string; Icon: FC<{ active: boolean }> }[] = [
  { id: 'dashboard',  label: 'Mercato',      Icon: IconMarket    },
  { id: 'favorites',  label: 'Preferiti',    Icon: IconFavorites },
  { id: 'alerts',     label: 'Allarmi',      Icon: IconAlerts    },
  { id: 'agent',      label: 'Agente',       Icon: IconAgent     },
  { id: 'settings',   label: 'Impostazioni', Icon: IconSettings  },
];

const Navbar: FC<Props> = ({ activeTab, onTabChange, alertCount, favoriteCount }) => {
  const badgeFor = (id: Tab) =>
    id === 'favorites' ? favoriteCount : id === 'alerts' ? alertCount : 0;

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 safe-bottom"
      style={{ background: '#0B1220', borderTop: '1px solid #263248' }}
    >
      <div className="flex max-w-lg mx-auto" style={{ height: 72 }}>
        {TABS.map(({ id, label, Icon }) => {
          const isActive = activeTab === id;
          const badge = badgeFor(id);

          return (
            <button
              key={id}
              onClick={() => { hapticLight(); onTabChange(id); }}
              className="flex-1 flex flex-col items-center justify-center gap-[5px] relative transition-colors duration-150"
              style={{ color: isActive ? '#3B82F6' : '#8B95A7' }}
            >
              {/* Radial glow behind active icon */}
              {isActive && (
                <span
                  className="absolute pointer-events-none"
                  style={{
                    top: '50%', left: '50%',
                    transform: 'translate(-50%, -62%)',
                    width: 48, height: 48, borderRadius: '50%',
                    background: 'radial-gradient(circle, rgba(59,130,246,0.18) 0%, transparent 72%)',
                  }}
                />
              )}

              {/* Icon + badge */}
              <div className="relative" style={{ opacity: isActive ? 1 : 0.72 }}>
                <Icon active={isActive} />
                {badge > 0 && (
                  <span
                    className="absolute -top-1 -right-2 text-white font-bold flex items-center justify-center"
                    style={{
                      fontSize: 10, minWidth: 15, height: 15,
                      padding: '0 3px', borderRadius: 8,
                      background: '#EF4444', lineHeight: 1,
                    }}
                  >
                    {badge > 99 ? '99+' : badge}
                  </span>
                )}
              </div>

              {/* Label */}
              <span style={{ fontSize: 11, fontWeight: 500, letterSpacing: 0.15, lineHeight: 1 }}>
                {label}
              </span>

              {/* Active pill indicator */}
              {isActive && (
                <span
                  className="absolute bottom-[5px]"
                  style={{
                    width: 22, height: 4, borderRadius: 4,
                    background: '#3B82F6',
                    boxShadow: '0 0 6px rgba(59,130,246,0.6)',
                  }}
                />
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};

export default Navbar;
