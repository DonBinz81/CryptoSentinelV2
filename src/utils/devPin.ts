/**
 * PIN che protegge le azioni riservate al proprietario: modalità sviluppatore e
 * comandi che scavalcano una protezione del capitale (es. azzerare il conteggio
 * della perdita giornaliera, NOTE/63).
 *
 * Sta in un file suo perché era già scritto a mano dentro SettingsTab: due costanti
 * uguali in due punti sono due costanti che prima o poi divergono, e qui divergere
 * significherebbe un comando che si sblocca con un PIN che l'utente non conosce più.
 *
 * Non è un segreto crittografico: è un attrito deliberato fra David e un gesto che
 * non va compiuto per sbaglio o d'impulso. La vera autorizzazione resta l'admin
 * token, verificato dal backend.
 */
export const DEV_PIN = '6878';
