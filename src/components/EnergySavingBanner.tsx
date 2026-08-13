import { type FC } from 'react';
import { Capacitor } from '@capacitor/core';
import { openBatterySettings } from '../utils/energySaving';

interface Props {
  dismissed: boolean;
  onDismiss: () => void;
}

const EnergySavingBanner: FC<Props> = ({ dismissed, onDismiss }) => {
  if (!Capacitor.isNativePlatform() || dismissed) return null;

  const handleOpen = () => {
    openBatterySettings();
    onDismiss();
  };

  return (
    <div className="bg-accent-yellow/10 border border-accent-yellow/30 rounded-xl px-4 py-3 flex items-center gap-3 mb-3">
      <span className="text-xl flex-shrink-0">🔋</span>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-gray-300">
          Disabilita il risparmio energetico per garantire gli aggiornamenti in background.
        </p>
      </div>
      <button
        onClick={handleOpen}
        className="flex-shrink-0 text-xs bg-accent-yellow text-dark-900 px-3 py-1.5 rounded-lg font-semibold hover:opacity-90 transition-opacity"
      >
        Disabilita
      </button>
      <button
        onClick={onDismiss}
        className="flex-shrink-0 text-gray-500 hover:text-gray-300 text-lg leading-none"
        aria-label="Chiudi"
      >
        ×
      </button>
    </div>
  );
};

export default EnergySavingBanner;
