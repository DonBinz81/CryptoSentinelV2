import { useState, type FC } from 'react';
import type { UpdateResult } from '../utils/update';
import { APK_PAGES_URL, downloadAndInstall, openDownloadsFolder } from '../utils/update';

interface Props {
  update: UpdateResult;
  dlState: 'idle' | 'downloading' | 'done' | 'error';
  onIgnore: () => void;
  onSnooze: () => void;
  onDismiss: () => void;
  onDownloadStart: () => void;
}

const UpdateNotification: FC<Props> = ({ update, dlState, onIgnore, onSnooze, onDismiss, onDownloadStart }) => {
  const [showModal, setShowModal] = useState(false);

  const apkUrl = update.downloadUrl ?? APK_PAGES_URL;

  const handleDownload = async () => {
    setShowModal(false);
    onDownloadStart();
    await downloadAndInstall(apkUrl);
  };

  const handleOpenDownloads = async () => {
    await openDownloadsFolder();
    onDismiss();
  };

  const modalBox = "bg-dark-800 rounded-2xl w-full max-w-sm p-5 shadow-2xl border border-dark-600 flex flex-col max-h-[85vh]";
  const backdrop = "fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4";

  return (
    <>
      {/* Floating indicator */}
      {dlState === 'idle' && (
        <button
          onClick={() => setShowModal(true)}
          className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center"
          aria-label="Aggiornamento disponibile"
        >
          <span className="absolute w-full h-full rounded-full bg-accent-green/25 animate-ping" />
          <span className="absolute w-full h-full rounded-full bg-accent-green/15 border border-accent-green/40" />
          <svg className="relative z-10 w-5 h-5 text-accent-green drop-shadow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        </button>
      )}

      {dlState === 'downloading' && (
        <div className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center">
          <span className="absolute w-full h-full rounded-full bg-accent-blue/15 border border-accent-blue/40" />
          <svg className="relative z-10 w-5 h-5 text-accent-blue animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        </div>
      )}

      {/* Segno di spunta cliccabile: apre direttamente la cartella Download */}
      {dlState === 'done' && (
        <button
          onClick={handleOpenDownloads}
          className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center"
          aria-label="Apri cartella Download"
        >
          <span className="absolute w-full h-full rounded-full bg-accent-green/20 border border-accent-green/40" />
          <svg className="relative z-10 w-5 h-5 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </button>
      )}

      {/* Errore download: tap per riprovare */}
      {dlState === 'error' && (
        <button
          onClick={handleDownload}
          className="fixed bottom-24 right-4 z-30 w-12 h-12 flex items-center justify-center"
          aria-label="Download fallito — riprova"
        >
          <span className="absolute w-full h-full rounded-full bg-accent-red/20 border border-accent-red/40" />
          <svg className="relative z-10 w-5 h-5 text-accent-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
          </svg>
        </button>
      )}

      {/* Modal — solo stato idle: dettagli aggiornamento */}
      {showModal && (
        <div className={backdrop} onClick={onSnooze}>
          <div className={modalBox} onClick={(e) => e.stopPropagation()} onTouchMove={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <span className="w-8 h-8 rounded-full bg-accent-green/20 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                </span>
                <h2 className="text-white font-bold text-base">Aggiornamento disponibile</h2>
              </div>
              <button onClick={() => { setShowModal(false); onSnooze(); }} className="text-gray-500 hover:text-gray-300 text-xl leading-none">×</button>
            </div>

            <div className="bg-dark-700 rounded-xl px-4 py-3 mb-4">
              <div className="flex items-center justify-between mb-1">
                <p className="text-xs text-gray-500">CryptoSentinelAI</p>
                <span className="flex-shrink-0 text-xs font-semibold text-accent-green bg-accent-green/10 px-2.5 py-1 rounded-full">Nuova</span>
              </div>
              <p className="text-white font-bold text-lg font-mono leading-snug break-words">
                {update.releaseName ?? (update.buildNumber ? `Build #${update.buildNumber}` : 'Nuova versione')}
              </p>
              <p className="text-xs text-gray-500 mt-1">{update.releaseDate}</p>
            </div>

            {update.releaseNotes && (
              <div className="mb-4 flex flex-col min-h-0">
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex-shrink-0">Note di rilascio</p>
                <div className="overflow-y-auto max-h-40 overscroll-contain">
                  <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">{update.releaseNotes}</p>
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => { setShowModal(false); onIgnore(); }}
                className="flex-1 py-2.5 rounded-xl text-xs text-gray-500 hover:text-gray-300 transition-colors"
                style={{ background: 'rgba(255,255,255,0.04)' }}
              >
                Ignora
              </button>
              <button
                onClick={() => { setShowModal(false); onSnooze(); }}
                className="flex-1 py-2.5 bg-dark-700 text-gray-300 text-sm rounded-xl hover:bg-dark-600 transition-colors"
              >
                Dopo
              </button>
              <button
                onClick={handleDownload}
                className="flex-1 py-2.5 bg-accent-green text-white text-sm font-semibold rounded-xl hover:opacity-90 transition-opacity"
              >
                Scarica
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default UpdateNotification;
