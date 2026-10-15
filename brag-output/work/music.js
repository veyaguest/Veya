// Music + SFX for the VEYA vertical launch film (24 s). Written as one piece in D major:
// every effect is a note of the current chord, placed in the same soft space as the pad.
const fs = require('fs');
const SR = 48000, DUR = 24.0, N = Math.round(SR * DUR);
const L = new Float32Array(N), R = new Float32Array(N); const TAU = Math.PI * 2;
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x)); const seg = (t, a, b) => clamp((t - a) / (b - a));
const n = (m) => 440 * Math.pow(2, (m - 69) / 12);
const CH = [[50, 54, 57, 61, 64], [47, 50, 54, 57, 62], [43, 47, 50, 54, 57], [45, 50, 52, 57, 62]];   // Dmaj9 · Bm7 · Gmaj7 · Asus4
const BPM = 96, BEAT = 60 / BPM, BAR = BEAT * 4;
const chordAt = (t) => CH[Math.floor(t / (BAR * 2)) % 4];
const END = 19.6;
let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 2 - 1;
// pad
for (let i = 0; i < N; i++) { const t = i / SR; const ch = t < END ? chordAt(t) : CH[0];
  const g = .06 * seg(t, 0, 1.4) * (t > END - .25 && t < END + .1 ? .4 : 1) * (1 - seg(t, 23.0, 24));
  let l = 0, r = 0; for (const m of ch) { const f = n(m + 12); l += Math.sin(TAU * f * t + Math.sin(TAU * .2 * t) * .3) / ch.length; r += Math.sin(TAU * f * 1.0025 * t + .7) / ch.length; }
  L[i] += l * g; R[i] += r * g; }
function piano(t0, m, vel = .12, tau = .6, pan = 0) { const f = n(m); for (let i = Math.round(t0 * SR); i < Math.min(N, Math.round((t0 + tau * 6) * SR)); i++) {
  const x = i / SR - t0; const env = Math.min(1, x / .005) * Math.exp(-x / tau);
  const v = vel * env * (Math.sin(TAU * f * x) + .25 * Math.sin(TAU * 2 * f * x) * Math.exp(-x / .25) + .08 * Math.sin(TAU * 3 * f * x) * Math.exp(-x / .12));
  L[i] += v * (1 - pan * .5); R[i] += v * (1 + pan * .5); } }
function kick(t0, g) { for (let i = Math.round(t0 * SR); i < Math.min(N, Math.round((t0 + .32) * SR)); i++) { const x = i / SR - t0; const f = 46 + 38 * Math.exp(-x / .035); const v = g * Math.exp(-x / .12) * Math.sin(TAU * f * x); L[i] += v; R[i] += v; } }
function shaker(t0, g) { let p = 0; for (let i = Math.round(t0 * SR); i < Math.min(N, Math.round((t0 + .07) * SR)); i++) { const x = i / SR - t0, w = rnd(), h = w - p; p = w; const v = g * Math.min(1, x / .01) * Math.exp(-x / .02) * h; L[i] += v * .7; R[i] += v * 1.1; } }
function tick(t0, m, g = .05) { piano(t0, m + 24, g, .07); }                      // a soft, pitched "click" in key
function swell(t0, len, g = .035) { let lp = 0; for (let i = Math.round(t0 * SR); i < Math.min(N, Math.round((t0 + len) * SR)); i++) { const x = (i / SR - t0) / len; lp += (.015 + .2 * x) * (rnd() - lp); const v = g * Math.sin(Math.PI * x) * lp; L[i] += v; R[i] += v; } }
// gentle groove under the product scenes
for (let t = 3.0; t < END - .2; t += BEAT) kick(t, .11 + .05 * seg(t, 3, 17));
for (let t = 3.0 + BEAT / 2; t < END - .2; t += BEAT) shaker(t, .018 + .012 * seg(t, 9, 17));
// piano pulse (chord tones, eighths), sparse in the hook
for (let t = 0.6; t < END - .3; t += BEAT / 2) { const k = Math.round(t / (BEAT / 2)); if (t < 3 && k % 2) continue; const ch = chordAt(t); piano(t, ch[k % ch.length] + 12, (t < 3 ? .045 : .035) + .02 * seg(t, 9, 17), .4, (k % 2 ? .3 : -.3)); }
// story sync (times = film seconds)
swell(3.35, .7, .04); piano(3.88, 69, .07, .9);                               // the paste lands
tick(5.42, 62); piano(5.8, 74, .06, .8);                                      // "פענוח הרשימה" → review
tick(8.3, 62); piano(8.42, 78, .055, .9); piano(8.5, 73, .04, .9);            // import → the list
swell(9.4, .7, .035);
tick(10.57, 66); tick(13.15, 66); piano(13.3, 69, .06, 1); piano(13.38, 74, .05, 1);   // two taps → "נתראה בחתונה"
swell(14.25, .6, .03);
const W = [...Array(9).keys()].map((i) => 15.0 + (i + 1) * .17); const sc = [62, 64, 66, 69, 71, 73, 74, 76, 78];
W.forEach((t, i) => tick(t, sc[i] - 12, .045 + .004 * i));                    // each real wave of answers
piano(16.62, 74, .08, 1.2); piano(16.66, 81, .05, 1.2);                       // 425
swell(17.3, .6, .03);
// end card: one clean chord on the logo
[[19.8, 38, .22, 1.8], [19.8, 50, .12, 1.6], [19.82, 57, .08, 1.5], [19.86, 62, .07, 1.5], [20.25, 66, .06, 1.6], [20.7, 69, .055, 1.8], [21.3, 74, .05, 2.0]].forEach(([t, m, v, tau]) => piano(t, m, v, tau));
// master: gentle saturation, short room, fade, normalize to -1 dBFS
const D = Math.round(SR * .043), D2 = Math.round(SR * .071);
for (let i = N - 1; i >= D2; i--) { L[i] += .16 * R[i - D] + .1 * L[i - D2]; R[i] += .16 * L[i - D] + .1 * R[i - D2]; }
let peak = 0; for (let i = 0; i < N; i++) { const t = i / SR; const fo = 1 - seg(t, 23.2, 24); L[i] = Math.tanh(L[i] * 1.3) * fo; R[i] = Math.tanh(R[i] * 1.3) * fo; peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i])); }
const gain = .89 / peak; const buf = Buffer.alloc(44 + N * 4);
buf.write('RIFF', 0); buf.writeUInt32LE(36 + N * 4, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22);
buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28); buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(N * 4, 40);
for (let i = 0; i < N; i++) { buf.writeInt16LE(Math.round(clamp(L[i] * gain, -1, 1) * 32767), 44 + i * 4); buf.writeInt16LE(Math.round(clamp(R[i] * gain, -1, 1) * 32767), 46 + i * 4); }
fs.writeFileSync(process.argv[2], buf); console.log('wrote', process.argv[2], 'peak', peak.toFixed(3));
