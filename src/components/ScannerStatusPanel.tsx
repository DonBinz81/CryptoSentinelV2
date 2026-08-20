import type { FC } from 'react';
import type { ScannerMarketStatus, ScannerStatusResponse } from '../services/agentApi';

// Risponde alla domanda che l'utente si fa quando il bot resta fermo: "sta cercando
// e non trova, o qualcosa lo blocca?" I tre casi hanno urgenze diverse e devono
// leggersi a colpo d'occhio, come il banner del guardiano (vedi GuardianBanner.tsx):
// silenzioso quando va tutto bene, netto quando serve attenzione.

/** Codici del motore -> italiano leggibile. Un codice non in lista si mostra cosi'
 * com'e': meglio un termine tecnico visibile che un'informazione persa. */
const MOTIVI: Record<string, string> = {
  spot_filters_not_satisfied: 'nessun segnale valido',
  perp_filters_not_satisfied: 'nessun segnale valido',
  market_risk_off: 'regime rischio-off su BTC',
  market_reversal_waiting: 'inversione in attesa di conferma',
  market_reversal_long_blocked: 'inversione: long bloccati',
  market_reversal_short_blocked: 'inversione: short bloccati',
  btc_trend_shock_blocked: 'shock BTC in corso',
  guardian_red_capital_preservation: 'guardiano in rosso',
};

const traduci = (codice: string): string => MOTIVI[codice] ?? codice;

/** "3 min fa" — coerente con quantoFa() del banner del guardiano. */
const quantoFa = (iso: string | null): string | null => {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  const min = Math.floor((Date.now() - t) / 60000);
  if (min < 1) return 'ora';
  if (min < 60) return `${min} min fa`;
  const ore = Math.floor(min / 60);
  return `${ore} ${ore === 1 ? 'ora' : 'ore'} fa`;
};

/** Un solo asset filtrato su un'ampia lista e' rumore statistico, non un blocco da
 * segnalare: coi dati reali del primo deploy (1 filtrato su 28 perp) un banner
 * "filtri attivi" avrebbe contraddetto la lettura corretta — "sta cercando e non
 * trova" — fatta sugli stessi identici numeri. Un errore invece conta sempre: non
 * e' rumore, e' qualcosa che si e' rotto. */
const marcatoBloccato = (m: ScannerMarketStatus): boolean =>
  m.error > 0 || m.filter >= Math.max(2, Math.ceil(m.scanned * 0.2));

/** Il motivo che spiega meglio un mercato fermo: il piu' frequente fra quelli che
 * non sono "nessun segnale valido" — quello e' il caso normale, non la notizia. */
const motivoPrincipale = (m: ScannerMarketStatus): string | null => {
  const rilevanti = Object.entries(m.reasons).filter(([codice]) => !codice.endsWith('_filters_not_satisfied'));
  if (rilevanti.length === 0) return null;
  const [codice] = rilevanti.sort((a, b) => b[1] - a[1])[0];
  return traduci(codice);
};

const RigaMercato: FC<{ label: string; m: ScannerMarketStatus | null }> = ({ label, m }) => {
  if (!m || m.scanned === 0) {
    return (
      <div className="flex items-center justify-between py-1.5">
        <span className="text-xs text-gray-500">{label}</span>
        <span className="text-xs text-gray-600">nessun asset in lista</span>
      </div>
    );
  }
  const bloccato = marcatoBloccato(m);
  const motivo = motivoPrincipale(m);
  return (
    <div className="flex items-center justify-between py-1.5">
      <span className="text-xs text-gray-500">{label}</span>
      {bloccato ? (
        <span className="text-xs font-semibold text-accent-yellow">
          {m.filter + m.error} bloccati{motivo ? `: ${motivo}` : ''}
        </span>
      ) : (
        <span className="text-xs text-gray-400">
          in cerca su <b className="text-gray-300">{m.scanned}</b> asset
        </span>
      )}
    </div>
  );
};

export const ScannerStatusPanel: FC<{ status: ScannerStatusResponse | null | undefined }> = ({ status }) => {
  if (!status) return null;

  // Nessun ciclo ancora registrato (es. subito dopo un riavvio): non e' un allarme,
  // e' solo presto. Un chip discreto invece di un banner vuoto o fuorviante.
  if (!status.available) {
    return (
      <div className="flex items-center gap-2 px-1">
        <span className="h-1.5 w-1.5 rounded-full bg-gray-600" />
        <span className="text-[11px] text-gray-500">Scanner: primo ciclo non ancora registrato</span>
      </div>
    );
  }

  // Stale: il ciclo si e' fermato, non e' "nessun segnale". Va segnalato come il
  // banner del guardiano segnala il rosso: netto, con role="alert".
  if (status.stale) {
    const daQuando = quantoFa(status.timestamp_utc);
    return (
      <section className="rounded-xl border border-accent-red/50 bg-accent-red/10 px-4 py-3" role="alert">
        <div className="flex items-start gap-2.5">
          <span className="mt-1 h-2.5 w-2.5 flex-shrink-0 animate-pulse rounded-full bg-accent-red" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-accent-red">SCANNER FERMO</p>
            <p className="mt-0.5 text-xs leading-5 text-gray-300">
              Il ciclo di scansione non gira{daQuando ? ` dall'ultimo aggiornamento, ${daQuando}` : ' da un pezzo'}.
              Non e&apos; &quot;nessun segnale&quot;: il bot non sta guardando il mercato.
            </p>
          </div>
        </div>
      </section>
    );
  }

  const spotOk = !status.markets.spot || !marcatoBloccato(status.markets.spot);
  const perpOk = !status.markets.perp || !marcatoBloccato(status.markets.perp);

  // Tutto normale su entrambi i mercati: un chip, come il guardiano in verde.
  // Nei giorni tranquilli lo scanner non deve fare rumore.
  if (spotOk && perpOk) {
    return (
      <div className="flex items-center gap-2 px-1">
        <span className="h-1.5 w-1.5 rounded-full bg-accent-green" />
        <span className="text-[11px] text-gray-500">
          Scanner attivo: in cerca di un segnale{status.age_seconds != null && status.age_seconds < 60 ? ' · ultimo ciclo ora' : ''}
        </span>
      </div>
    );
  }

  return (
    <section className="rounded-xl border border-accent-yellow/50 bg-accent-yellow/10 px-4 py-3 space-y-1">
      <p className="text-sm font-bold text-accent-yellow">SCANNER: FILTRI ATTIVI</p>
      <div className="rounded-lg bg-dark-900/60 px-3 py-1">
        <RigaMercato label="Spot" m={status.markets.spot} />
        <RigaMercato label="Perp" m={status.markets.perp} />
      </div>
    </section>
  );
};
