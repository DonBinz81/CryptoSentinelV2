import { useEffect, useState, type FC } from 'react';
import {
  setGuardianOverride,
  type GuardianOverrideChoice,
  type GuardianState,
  type GuardianStatus,
} from '../services/agentApi';

// Banner del guardiano di regime. Deve essere impossibile da non vedere quando il bot
// si sta proteggendo, e quasi invisibile quando va tutto bene: in VERDE resta un chip.
//
// I comandi di emergenza stanno DENTRO il banner, non tre tocchi piu' in la': quando
// serve fermare il bot, cercarli nel setup e' esattamente il momento sbagliato.

// Il guardiano e' perp-only per costruzione (record_stop alimentato solo dagli
// stop pieni perp, blocco RED e scaling YELLOW dentro evaluate_perp): letto dal
// pannello Spot, il vecchio testo senza "perp" affermava un blocco che non c'era
// (segnalazione di David, 22/08, girata dalla chat E — NOTE/88).
const TONI = {
  red: {
    bordo: 'border-accent-red/50',
    fondo: 'bg-accent-red/10',
    testo: 'text-accent-red',
    puntino: 'bg-accent-red',
    titolo: 'PROTEZIONE PERP ATTIVA',
    sottotitolo: 'Nessuna nuova posizione PERP finche\' il mercato non si calma',
  },
  yellow: {
    bordo: 'border-accent-yellow/50',
    fondo: 'bg-accent-yellow/10',
    testo: 'text-accent-yellow',
    puntino: 'bg-accent-yellow',
    titolo: 'PRUDENZA PERP',
    sottotitolo: 'Posizioni perp dimezzate: gli stop perp hanno fatto scattare il guardiano',
  },
  green: {
    bordo: 'border-accent-green/30',
    fondo: 'bg-accent-green/5',
    testo: 'text-accent-green',
    puntino: 'bg-accent-green',
    titolo: 'REGIME NORMALE',
    sottotitolo: '',
  },
} as const;

const NOME_LIVELLO: Record<GuardianState, string> = { green: 'VERDE', yellow: 'GIALLO', red: 'ROSSO' };

/** Quanto protegge ciascun livello: decide se una scelta ABBASSA la protezione. */
const PROTEZIONE: Record<GuardianState, number> = { green: 0, yellow: 1, red: 2 };

/**
 * Comandi admin per forzare il regime, o restituirlo all'automatico.
 *
 * "AUTO" non e' "verde": rimuove l'override e fa tornare l'effettivo al livello
 * automatico CORRENTE, che nel frattempo puo' essere cambiato. Per questo la
 * conferma non guarda quale pulsante e' stato premuto ma il livello che ne
 * RISULTA: premere AUTO con override rosso e automatico verde abbassa la
 * protezione quanto scegliere "verde" a mano, e va confermato uguale.
 */
const ControlliOverride: FC<{
  guardian: GuardianStatus;
  adminToken: string;
  onChanged: () => void;
  /** Sostituita solo dal prototipo: la vera fallisce senza backend configurato. */
  overrideFn?: typeof setGuardianOverride;
}> = ({ guardian, adminToken, onChanged, overrideFn = setGuardianOverride }) => {
  const [chiesta, setChiesta] = useState<GuardianOverrideChoice | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState('');

  const automatico = guardian.automatic_level ?? guardian.state;
  const effettivo = guardian.effective_level ?? guardian.state;
  const override = guardian.manual_override?.level ?? null;

  const risultatoDi = (x: GuardianOverrideChoice): GuardianState => (x === 'auto' ? automatico : x);
  const abbassa = (x: GuardianOverrideChoice) => PROTEZIONE[risultatoDi(x)] < PROTEZIONE[effettivo];

  const invia = async (x: GuardianOverrideChoice) => {
    setInCorso(true);
    setErrore('');
    try {
      await overrideFn(x, x === 'auto' ? 'ritorno automatico da app' : `forzato ${x} da app`, adminToken);
      setChiesta(null);
      onChanged();
    } catch (e) {
      setErrore(e instanceof Error ? e.message : 'Comando non riuscito.');
    } finally {
      setInCorso(false);
    }
  };

  const scegli = (x: GuardianOverrideChoice) => {
    if (abbassa(x)) setChiesta(x);
    else void invia(x);
  };

  return (
    <div>
      <p className="mb-1.5 text-[11px] uppercase tracking-wide text-gray-500">Controllo admin</p>
      <div className="grid grid-cols-4 gap-1.5">
        {(['auto', 'green', 'yellow', 'red'] as const).map((x) => {
          const attivo = x === 'auto' ? override === null : override === x;
          return (
            <button
              key={x}
              type="button"
              onClick={() => scegli(x)}
              disabled={!adminToken || inCorso}
              className={`rounded-lg px-2 py-2 text-xs font-bold disabled:opacity-40 ${
                attivo ? 'bg-dark-600 text-white ring-1 ring-white/20' : 'bg-dark-800 text-gray-400'
              }`}
            >
              {x === 'auto' ? 'AUTO' : NOME_LIVELLO[x]}
            </button>
          );
        })}
      </div>
      {errore && <p className="mt-1.5 text-[11px] text-accent-red">{errore}</p>}

      {chiesta && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-5">
          <div className="w-full max-w-sm space-y-3 rounded-2xl border border-dark-600 bg-dark-800 p-4">
            <p className="text-sm font-bold text-white">
              Forzare la Protezione PERP da {NOME_LIVELLO[effettivo]} a {NOME_LIVELLO[risultatoDi(chiesta)]}?
            </p>
            <p className="text-xs leading-5 text-gray-300">
              Le nuove entrate PERP seguiranno immediatamente il regime {NOME_LIVELLO[risultatoDi(chiesta)]}
              {chiesta === 'auto'
                ? ', tornando a seguire l’automatico.'
                : ' finché non torni su AUTO o scegli un altro livello.'}
            </p>
            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={() => setChiesta(null)}
                disabled={inCorso}
                className="flex-1 rounded-lg bg-dark-700 px-3 py-2.5 text-sm font-semibold text-gray-300 disabled:opacity-40"
              >
                Annulla
              </button>
              <button
                type="button"
                onClick={() => void invia(chiesta)}
                disabled={inCorso}
                className="flex-1 rounded-lg bg-accent-red px-3 py-2.5 text-sm font-bold text-white disabled:opacity-40"
              >
                {inCorso ? 'Attendi…' : 'Conferma'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/** Riquadro che tiene a vista l'automatico mentre l'override lo sta scavalcando. */
const RigaAutomatico: FC<{ automatico: GuardianState }> = ({ automatico }) => (
  <div className="rounded-lg border border-dark-600 bg-dark-900/60 px-3 py-2 text-xs">
    <div className="flex items-center justify-between">
      <span className="text-gray-400">Automatico (in corso)</span>
      <span className="font-semibold text-white">{NOME_LIVELLO[automatico]}</span>
    </div>
    <p className="mt-1 text-[11px] text-gray-500">
      Premendo AUTO torni subito a {NOME_LIVELLO[automatico]}. Il motore continua a contare gli stop e ad
      aggiornare i timer.
    </p>
  </div>
);

/** "3 ore fa", "22 minuti fa": piu' leggibile di un orario quando conta il "quanto e' passato". */
const quantoFa = (iso: string | null): string | null => {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return null;
  const min = Math.floor((Date.now() - t) / 60000);
  if (min < 1) return 'ora';
  if (min < 60) return `${min} min fa`;
  const ore = Math.floor(min / 60);
  if (ore < 24) return `${ore} ${ore === 1 ? 'ora' : 'ore'} fa`;
  const gg = Math.floor(ore / 24);
  return `${gg} ${gg === 1 ? 'giorno' : 'giorni'} fa`;
};

/**
 * Prossimo passo di de-escalation (NOTE/95): un passo alla volta, RED->YELLOW poi
 * YELLOW->GREEN, dopo `reentry_hours` ore pulite dall'ancora — la piu' recente fra
 * l'ultimo stop e l'ultimo cambio di stato. Ogni nuovo stop sposta l'ancora avanti:
 * questo e' un CALCOLO LOCALE, non un valore che il backend garantisce — e' una
 * proiezione sul presente, non una promessa sul futuro (David, 25/08).
 */
const prossimoStato = (stato: GuardianState): GuardianState | null =>
  stato === 'red' ? 'yellow' : stato === 'yellow' ? 'green' : null;

const NOME_STATO: Record<GuardianState, string> = { red: 'ROSSO', yellow: 'GIALLO', green: 'VERDE' };

/** "1h 59m" quando resta piu' di un minuto, "42s" sotto — la resa piu' viva vicino
 * allo scatto, che e' anche il momento in cui conta di piu' guardare il telefono. */
const formattaResto = (ms: number): string => {
  const tot = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(tot / 3600);
  const m = Math.floor((tot % 3600) / 60);
  const s = tot % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
};

/**
 * Countdown live verso il prossimo passo di de-escalation. Nullo su GREEN (non c'e'
 * un "prossimo passo") o se mancano i dati per calcolarlo.
 */
const CountdownRiattivazione: FC<{ guardian: GuardianStatus }> = ({ guardian }) => {
  const [ora, setOra] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setOra(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  // Il countdown racconta la macchina AUTOMATICA, che continua a girare anche
  // sotto override: `state` mappa sull'effettivo, quindi con un override verde
  // sparirebbe proprio mentre l'automatico sta ancora scendendo da ROSSO.
  const prossimo = prossimoStato(guardian.automatic_level ?? guardian.state);
  if (!prossimo) return null;
  const ancoraCandidati = [guardian.last_stop_at, guardian.changed_at]
    .map((iso) => (iso ? new Date(iso).getTime() : NaN))
    .filter((t) => !Number.isNaN(t));
  if (ancoraCandidati.length === 0 || !guardian.reentry_hours) return null;
  const ancora = Math.max(...ancoraCandidati);
  const bersaglio = ancora + guardian.reentry_hours * 3600_000;
  const resto = bersaglio - ora;

  return (
    <div className="rounded-lg border border-dark-700 bg-dark-900/40 px-3 py-2">
      <p className="text-xs leading-5 text-gray-300">
        {resto > 0 ? (
          <>{guardian.manual_override ? 'Prossima transizione automatica' : 'Prossimo passo'}:{' '}
            <b className="text-white">{NOME_STATO[prossimo]}</b> tra{' '}
            <b className="text-white">{formattaResto(resto)}</b></>
        ) : (
          <>In attesa che il ciclo registri il passaggio a <b className="text-white">{NOME_STATO[prossimo]}</b>…</>
        )}
      </p>
      <p className="mt-0.5 text-[11px] text-gray-500">
        Si azzera a ogni nuovo stop pieno perp: è una proiezione, non una promessa.
      </p>
    </div>
  );
};

/**
 * La spiegazione vale solo se appartiene alla transizione corrente: se il backend non
 * l'ha ancora scritta, o se e' rimasta indietro rispetto al cambio di stato, si mostrano
 * i dati concreti invece di un testo che racconta un'altra storia.
 */
const spiegazioneValida = (g: GuardianStatus): string | null => {
  const testo = g.explanation?.trim();
  if (!testo) return null;
  if (!g.explained_at || !g.changed_at) return testo;
  const spiegata = new Date(g.explained_at).getTime();
  const cambiata = new Date(g.changed_at).getTime();
  if (Number.isNaN(spiegata) || Number.isNaN(cambiata)) return testo;
  // Tolleranza: il Brain risponde qualche secondo dopo la transizione.
  return spiegata + 120_000 >= cambiata ? testo : null;
};

export const GuardianBanner: FC<{
  guardian: GuardianStatus | null | undefined;
  killSwitch: string | undefined;
  adminToken: string;
  busy: boolean;
  onPause: () => void;
  onCloseAll: () => void;
  /** Ricarica lo stato dopo un cambio di override. */
  onGuardianChanged?: () => void;
  /** Solo per il prototipo: vedi ControlliOverride. */
  overrideFn?: typeof setGuardianOverride;
}> = ({ guardian, killSwitch, adminToken, busy, onPause, onCloseAll, onGuardianChanged, overrideFn }) => {
  if (!guardian || !guardian.enabled) return null;

  const tono = TONI[guardian.state] ?? TONI.green;
  const attivo = killSwitch === 'running';
  const automatico = guardian.automatic_level ?? guardian.state;
  const manuale = guardian.manual_override?.level != null;

  // VERDE: solo un chip. Nei giorni normali il guardiano non deve fare rumore.
  //
  // ⚠️ MA non quando il verde e' FORZATO: li' il chip nasconderebbe proprio la cosa
  // da non dimenticare, cioe' che l'automatico e' su un livello piu' protettivo e
  // che tornando in AUTO ci si ricade. Il banner resta esteso finche' c'e' override.
  if (guardian.state === 'green' && !manuale) {
    return (
      <div className="space-y-2 px-1">
        <div className="flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${tono.puntino}`} />
          <span className="text-[11px] text-gray-500">Regime normale (perp)</span>
        </div>
        {/* I comandi restano raggiungibili anche in verde — servono a provare i
            livelli senza aspettare che il mercato li faccia scattare — ma sotto
            il chip, non dentro: in giornata normale il guardiano resta quieto. */}
        {adminToken && onGuardianChanged && (
          <ControlliOverride guardian={guardian} adminToken={adminToken} onChanged={onGuardianChanged} overrideFn={overrideFn} />
        )}
      </div>
    );
  }

  const spiegazione = spiegazioneValida(guardian);
  const ultimoStop = quantoFa(guardian.last_stop_at);
  const daQuando = quantoFa(guardian.changed_at);
  const rosso = guardian.state === 'red';

  return (
    <section
      className={`rounded-xl border ${tono.bordo} ${tono.fondo} px-4 py-3 space-y-3`}
      role={rosso ? 'alert' : 'status'}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={`mt-1 h-2.5 w-2.5 flex-shrink-0 rounded-full ${tono.puntino} ${rosso ? 'animate-pulse' : ''}`}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <p className={`text-sm font-bold ${tono.testo}`}>{tono.titolo}</p>
            {daQuando && <span className="flex-shrink-0 text-[11px] text-gray-500">da {daQuando}</span>}
          </div>
          <p className="mt-0.5 text-xs leading-5 text-gray-300">{tono.sottotitolo}</p>
          {/* Il banner sta sopra i selettori Spot/Perp/Global, identico su entrambi i
              pannelli: senza questa riga, letto dallo Spot sembra dire che anche
              li' le entrate siano bloccate. Non lo sono mai. */}
          <p className="mt-1 text-[11px] text-gray-500">Lo spot non e&apos; toccato: entra normalmente.</p>
        </div>
        {manuale && (
          <span className="flex-shrink-0 rounded-full bg-sky-500/15 px-2 py-0.5 text-[11px] font-semibold text-sky-400">
            MANUALE
          </span>
        )}
      </div>

      {/* Sotto override l'automatico resta a vista: e' cio' a cui si torna con AUTO. */}
      {manuale && <RigaAutomatico automatico={automatico} />}

      <CountdownRiattivazione guardian={guardian} />

      {/* La spiegazione del Brain se c'e'; altrimenti i fatti concreti, che restano utili. */}
      <div className="rounded-lg bg-dark-900/60 px-3 py-2">
        {spiegazione ? (
          <p className="text-xs leading-5 text-gray-300">{spiegazione}</p>
        ) : (
          <p className="text-xs leading-5 text-gray-400">
            <b className="text-white">{guardian.stops_in_window}</b>{' '}
            {guardian.stops_in_window === 1 ? 'stop pieno' : 'stop pieni'} nelle ultime{' '}
            <b className="text-white">{Math.round(guardian.window_hours)}</b> ore
            {ultimoStop && <> · l&apos;ultimo {ultimoStop}</>}
          </p>
        )}
      </div>

      {/* Comandi di emergenza dentro il banner: quando servono, servono subito. */}
      <div className="flex gap-2">
        <button
          onClick={onCloseAll}
          disabled={!adminToken || busy}
          className="flex-1 rounded-lg bg-accent-red px-3 py-2.5 text-xs font-bold text-white disabled:opacity-40"
        >
          {busy ? 'Attendi…' : '⛔ Chiudi tutto'}
        </button>
        {/* soft_stop: blocca le nuove entrate, non tocca le posizioni gia' aperte. */}
        {attivo && (
          <button
            onClick={onPause}
            disabled={!adminToken || busy}
            className="flex-1 rounded-lg border border-gray-600 bg-dark-800 px-3 py-2.5 text-xs font-semibold text-gray-200 disabled:opacity-40"
          >
            ⏸ Blocca entrate
          </button>
        )}
      </div>
      {adminToken && onGuardianChanged && (
        <ControlliOverride guardian={guardian} adminToken={adminToken} onChanged={onGuardianChanged} overrideFn={overrideFn} />
      )}
      {!adminToken && (
        <p className="text-[11px] text-gray-600">Per usare i comandi serve l&apos;admin token nel setup.</p>
      )}
    </section>
  );
};
