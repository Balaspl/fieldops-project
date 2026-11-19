/**
 * toastSoundService.ts
 * Web Audio API sound alerts for critical dispatch events.
 * No external library required — same approach as AlertBanner.tsx.
 */

const STORAGE_KEY = 'fieldops_toast_sound_enabled';

let _soundEnabled: boolean = (() => {
  try {
    return localStorage.getItem(STORAGE_KEY) !== 'false';
  } catch {
    return true;
  }
})();

export function isSoundEnabled(): boolean {
  return _soundEnabled;
}

export function setSoundEnabled(enabled: boolean): void {
  _soundEnabled = enabled;
  try {
    localStorage.setItem(STORAGE_KEY, String(enabled));
  } catch {
    // ignore
  }
}

/** Short double-beep for job.rejected */
export function playBeep(): void {
  if (!_soundEnabled) return;
  try {
    const ctx = new AudioContext();
    const times = [0, 0.18];
    times.forEach((t) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime + t);
      gain.gain.setValueAtTime(0.35, ctx.currentTime + t);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.14);
      osc.start(ctx.currentTime + t);
      osc.stop(ctx.currentTime + t + 0.14);
    });
    setTimeout(() => ctx.close(), 600);
  } catch {
    // AudioContext not available (e.g., test environment)
  }
}

/** Descending alarm tone for job.expired */
export function playAlarm(): void {
  if (!_soundEnabled) return;
  try {
    const ctx = new AudioContext();
    const freqs = [960, 800, 640];
    freqs.forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.type = 'sawtooth';
      const t = ctx.currentTime + i * 0.22;
      osc.frequency.setValueAtTime(freq, t);
      gain.gain.setValueAtTime(0.3, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.2);
      osc.start(t);
      osc.stop(t + 0.2);
    });
    setTimeout(() => ctx.close(), 900);
  } catch {
    // AudioContext not available
  }
}
