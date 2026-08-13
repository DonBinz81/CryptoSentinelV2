let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  if (audioCtx?.state === 'closed') audioCtx = null;
  if (!audioCtx) {
    try {
      audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    } catch {
      return null;
    }
  }
  return audioCtx;
}

export function playAlertBeep(): void {
  const ctx = getAudioContext();
  if (!ctx) return;

  const resume = ctx.state === 'suspended' ? ctx.resume() : Promise.resolve();
  resume.then(() => {
    const times = [0, 0.15, 0.3];
    times.forEach((startOffset) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime + startOffset);
      osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + startOffset + 0.1);

      gain.gain.setValueAtTime(0.4, ctx.currentTime + startOffset);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + startOffset + 0.12);

      osc.start(ctx.currentTime + startOffset);
      osc.stop(ctx.currentTime + startOffset + 0.13);
    });
  }).catch(() => {});
}
