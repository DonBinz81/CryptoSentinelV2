import type { FC } from 'react';

/**
 * Faro CryptoSentinelV2 AI.
 * Torre blu, luce ARANCIONE BITCOIN (#F7931A): il fascio caldo su torre fredda
 * rende l'icona riconoscibile a colpo d'occhio anche in miniatura, e richiama
 * l'arancione di "Crypto" nel titolo.
 */
const LogoLighthouse: FC = () => (
  <svg width="40" height="48" viewBox="0 0 40 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="cslh_tower" x1="20" y1="8" x2="20" y2="42" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stopColor="#93C5FD" />
        <stop offset="55%" stopColor="#3B82F6" />
        <stop offset="100%" stopColor="#1E3A8A" />
      </linearGradient>
      <radialGradient id="cslh_lamp" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stopColor="#FDBA74" stopOpacity="0.65" />
        <stop offset="100%" stopColor="#F7931A" stopOpacity="0" />
      </radialGradient>
    </defs>

    {/* Alone ambientale: caldo, per staccare dallo sfondo scuro */}
    <ellipse cx="20" cy="23" rx="15" ry="19" fill="#F7931A" fillOpacity="0.06" />

    {/* Fascio di luce — in alto a sinistra (principale) */}
    <path d="M20,9 L0,0 L4,9 Z" fill="#F7931A" fillOpacity="0.42" />
    <path d="M20,9 L1,3 L0,12 Z" fill="#FDBA74" fillOpacity="0.20" />
    {/* Fascio di luce — in alto a destra (secondario) */}
    <path d="M20,9 L38,1 L36,9 Z" fill="#F7931A" fillOpacity="0.18" />

    {/* Alone della lampada */}
    <circle cx="20" cy="9" r="8" fill="url(#cslh_lamp)" />

    {/* Basamento */}
    <rect x="9" y="42" width="22" height="4.5" rx="2.25" fill="#1E3A8A" fillOpacity="0.9" />

    {/* Corpo della torre (rastremato) */}
    <path d="M11.5,42 L16,22 L24,22 L28.5,42 Z" fill="url(#cslh_tower)" />

    {/* Fasce decorative sulla torre */}
    <path d="M12.2,38.5 L27.8,38.5 L28.3,36.5 L11.7,36.5 Z" fill="#1E3A8A" fillOpacity="0.5" />
    <path d="M13.2,32 L26.8,32 L27.2,30 L12.8,30 Z" fill="#1E3A8A" fillOpacity="0.5" />

    {/* Ballatoio */}
    <rect x="13.5" y="21" width="13" height="2" rx="1" fill="#60A5FA" />
    {/* Ringhiera */}
    <line x1="16"   y1="21" x2="16"   y2="23" stroke="#93C5FD" strokeWidth="0.7" strokeOpacity="0.55" />
    <line x1="18.5" y1="21" x2="18.5" y2="23" stroke="#93C5FD" strokeWidth="0.7" strokeOpacity="0.55" />
    <line x1="21"   y1="21" x2="21"   y2="23" stroke="#93C5FD" strokeWidth="0.7" strokeOpacity="0.55" />
    <line x1="23.5" y1="21" x2="23.5" y2="23" stroke="#93C5FD" strokeWidth="0.7" strokeOpacity="0.55" />

    {/* Lanterna: vetri caldi, e' la sorgente della luce */}
    <rect x="15.5" y="13.5" width="9" height="7.5" rx="1.5" fill="#B45309" />
    <rect x="16.5" y="14.5" width="3"   height="5.5" rx="0.75" fill="#FDBA74" fillOpacity="0.55" />
    <rect x="20"   y="14.5" width="3.5" height="5.5" rx="0.75" fill="#FDBA74" fillOpacity="0.35" />

    {/* Cupola */}
    <path d="M14,13.5 L20,6.5 L26,13.5 Z" fill="#2563EB" />
    <path d="M15.5,13.5 L20,8 L22,13.5 Z" fill="#60A5FA" fillOpacity="0.25" />

    {/* Antenna */}
    <line x1="20" y1="6.5" x2="20" y2="3.5" stroke="#93C5FD" strokeWidth="0.9" strokeLinecap="round" strokeOpacity="0.8" />

    {/* Lampada — bagliore a strati, dal caldo al bianco */}
    <circle cx="20" cy="9" r="4.5" fill="#F7931A" fillOpacity="0.28" />
    <circle cx="20" cy="9" r="2.5" fill="#FDBA74" fillOpacity="0.85" />
    <circle cx="20" cy="9" r="1.4" fill="#FFF7ED" fillOpacity="0.98" />

    {/* Onda alla base */}
    <path
      d="M5,45.5 Q9,44.2 13,45.5 Q17,46.8 21,45.5 Q25,44.2 29,45.5 Q33,46.8 37,45.5"
      stroke="#60A5FA" strokeWidth="0.8" fill="none" strokeOpacity="0.4" strokeLinecap="round"
    />
  </svg>
);

export default LogoLighthouse;
