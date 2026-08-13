import { type FC, useState, useEffect, useRef, useCallback } from 'react';

const SESSION_KEY = 'cs_splash_shown';
const AUTO_DISMISS_MS = 8000;

const SPLASH_BG = '#0a1220';

interface Props {
  onDone: () => void;
}

const SplashOverlay: FC<Props> = ({ onDone }) => {
  const [visible, setVisible] = useState(true);
  const [iframeReady, setIframeReady] = useState(false);
  const dismissed = useRef(false);

  const dismiss = useCallback(() => {
    if (dismissed.current) return;
    dismissed.current = true;
    sessionStorage.setItem(SESSION_KEY, '1');
    setVisible(false);
    setTimeout(onDone, 380);
  }, [onDone]);

  useEffect(() => {
    const t = setTimeout(dismiss, AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [dismiss]);

  return (
    <div
      className="fixed inset-0 z-[9999]"
      style={{
        background: SPLASH_BG,
        transition: 'opacity 380ms ease',
        opacity: visible ? 1 : 0,
        pointerEvents: visible ? 'auto' : 'none',
      }}
      onClick={dismiss}
    >
      <iframe
        src="/splash.html"
        className="w-full h-full border-none block"
        title="Splash"
        style={{
          transition: 'opacity 300ms ease',
          opacity: iframeReady ? 1 : 0,
        }}
        onLoad={() => setIframeReady(true)}
      />
      {/* transparent overlay to capture clicks that would otherwise be swallowed by the iframe */}
      <div className="absolute inset-0" onClick={dismiss} />
    </div>
  );
};

export function shouldShowSplash(): boolean {
  return !sessionStorage.getItem(SESSION_KEY);
}

export default SplashOverlay;
