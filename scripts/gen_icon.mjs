import { createCanvas } from 'canvas';
import fs from 'fs';
import path from 'path';

const SIZES = [
  { dir: 'mipmap-mdpi',    size: 48  },
  { dir: 'mipmap-hdpi',    size: 72  },
  { dir: 'mipmap-xhdpi',   size: 96  },
  { dir: 'mipmap-xxhdpi',  size: 144 },
  { dir: 'mipmap-xxxhdpi', size: 192 },
];

function drawIcon(ctx, S) {
  const cx = S / 2;

  // ── Background deep navy ───────────────────────────────────────────────────
  const bg = ctx.createRadialGradient(cx, S * 0.45, 0, cx, S * 0.45, S * 0.85);
  bg.addColorStop(0,   '#0d2155');
  bg.addColorStop(0.5, '#081535');
  bg.addColorStop(1,   '#030a18');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, S, S);

  // ── Stars ──────────────────────────────────────────────────────────────────
  const starData = [
    [.10,.08,.6],[.82,.06,.5],[.22,.14,.7],[.70,.10,.5],
    [.45,.05,.8],[.88,.20,.4],[.06,.25,.5],[.58,.15,.6],
    [.76,.07,.5],[.33,.22,.6],[.92,.35,.4],[.15,.40,.3],
    [.65,.30,.4],[.05,.55,.3],[.95,.18,.4],
  ];
  for (const [sx, sy, a] of starData) {
    ctx.fillStyle = `rgba(200,220,255,${a})`;
    ctx.beginPath();
    ctx.arc(sx * S, sy * S, S * 0.007, 0, Math.PI * 2);
    ctx.fill();
  }

  // ── Background circle ring (halo) ─────────────────────────────────────────
  ctx.strokeStyle = 'rgba(100,150,220,0.18)';
  ctx.lineWidth = S * 0.025;
  ctx.beginPath();
  ctx.arc(cx, S * 0.45, S * 0.44, 0, Math.PI * 2);
  ctx.stroke();
  ctx.strokeStyle = 'rgba(100,150,220,0.10)';
  ctx.lineWidth = S * 0.012;
  ctx.beginPath();
  ctx.arc(cx, S * 0.45, S * 0.48, 0, Math.PI * 2);
  ctx.stroke();

  // ── Light beam (diagonal top-right) ───────────────────────────────────────
  const beamCX = cx;
  const beamCY = S * 0.265;
  ctx.save();
  // Wide beam
  const beamGrad = ctx.createConicalGradient
    ? null
    : null;

  // Beam using radial + clip trick: draw filled sector
  const beamAngle = -Math.PI * 0.38; // pointing upper-right
  const spread = 0.13;
  for (let pass = 0; pass < 3; pass++) {
    const alphas = [0.12, 0.22, 0.35];
    const spreads = [spread * 2.2, spread * 1.3, spread * 0.5];
    const len = S * 0.9;
    const bG = ctx.createRadialGradient(beamCX, beamCY, 0, beamCX, beamCY, len);
    bG.addColorStop(0,   `rgba(180,210,255,${alphas[pass]})`);
    bG.addColorStop(0.5, `rgba(140,185,255,${alphas[pass] * 0.5})`);
    bG.addColorStop(1,   'rgba(100,160,255,0)');
    ctx.fillStyle = bG;
    ctx.beginPath();
    ctx.moveTo(beamCX, beamCY);
    ctx.arc(beamCX, beamCY, len, beamAngle - spreads[pass], beamAngle + spreads[pass]);
    ctx.closePath();
    ctx.fill();
  }
  ctx.restore();

  // ── Ground glow ────────────────────────────────────────────────────────────
  const groundY = S * 0.88;
  const gGlow = ctx.createRadialGradient(cx, groundY, 0, cx, groundY, S * 0.4);
  gGlow.addColorStop(0,   'rgba(30,80,180,0.4)');
  gGlow.addColorStop(0.6, 'rgba(15,40,100,0.15)');
  gGlow.addColorStop(1,   'rgba(0,0,0,0)');
  ctx.fillStyle = gGlow;
  ctx.fillRect(0, groundY - S * 0.1, S, S * 0.22);

  // ── Rocky base / platform ──────────────────────────────────────────────────
  // Outer dark mound
  ctx.fillStyle = '#0a1a38';
  ctx.beginPath();
  ctx.ellipse(cx, groundY + S * 0.04, S * 0.38, S * 0.10, 0, 0, Math.PI * 2);
  ctx.fill();

  // Platform top slab
  const platW = S * 0.42;
  const platH = S * 0.055;
  const platY = groundY - platH * 0.3;
  const platX = cx - platW / 2;

  const platGrad = ctx.createLinearGradient(platX, platY, platX + platW, platY + platH);
  platGrad.addColorStop(0, '#1a3060');
  platGrad.addColorStop(0.5, '#243870');
  platGrad.addColorStop(1, '#101f48');
  ctx.fillStyle = platGrad;
  roundRect(ctx, platX, platY, platW, platH, S * 0.015);
  ctx.fill();

  // Platform edge highlight
  ctx.strokeStyle = 'rgba(120,160,220,0.3)';
  ctx.lineWidth = S * 0.008;
  ctx.beginPath();
  ctx.moveTo(platX + S * 0.02, platY);
  ctx.lineTo(platX + platW - S * 0.02, platY);
  ctx.stroke();

  // ── AI text on platform ────────────────────────────────────────────────────
  const aiFontSize = platH * 0.65;
  ctx.font = `700 ${aiFontSize}px "Arial Black", Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = 'rgba(255,255,255,0.90)';
  ctx.fillText('AI', cx, platY + platH * 0.52);

  // ── Tower body ─────────────────────────────────────────────────────────────
  const towerTopY  = S * 0.30;
  const towerBotY  = platY;
  const towerTopW  = S * 0.155;
  const towerBotW  = S * 0.24;
  const towerTopX  = cx - towerTopW / 2;
  const towerBotX  = cx - towerBotW / 2;

  // Tower shadow/glow from beacon
  const tShadow = ctx.createRadialGradient(cx, towerTopY, 0, cx, towerTopY, S * 0.5);
  tShadow.addColorStop(0,   'rgba(80,140,255,0.20)');
  tShadow.addColorStop(0.4, 'rgba(40,80,180,0.08)');
  tShadow.addColorStop(1,   'rgba(0,0,0,0)');
  ctx.fillStyle = tShadow;
  ctx.beginPath();
  ctx.moveTo(towerBotX - S * 0.05, towerBotY + S * 0.01);
  ctx.lineTo(towerBotX + towerBotW + S * 0.05, towerBotY + S * 0.01);
  ctx.lineTo(towerTopX + towerTopW + S * 0.08, towerTopY);
  ctx.lineTo(towerTopX - S * 0.08, towerTopY);
  ctx.closePath();
  ctx.fill();

  // Blue stripes (background fill of tower = blue-gray)
  const numStripes = 5;
  const stripeH = (towerBotY - towerTopY) / numStripes;
  for (let i = 0; i < numStripes; i++) {
    const sy1 = towerTopY + i * stripeH;
    const sy2 = sy1 + stripeH;
    const r1 = (sy1 - towerTopY) / (towerBotY - towerTopY);
    const r2 = (sy2 - towerTopY) / (towerBotY - towerTopY);
    const x1L = towerTopX + r1 * (towerBotX - towerTopX);
    const x1R = towerTopX + towerTopW + r1 * (towerBotX + towerBotW - towerTopX - towerTopW);
    const x2L = towerTopX + r2 * (towerBotX - towerTopX);
    const x2R = towerTopX + towerTopW + r2 * (towerBotX + towerBotW - towerTopX - towerTopW);
    const isWhite = i % 2 === 0;

    if (isWhite) {
      const wG = ctx.createLinearGradient(x1L, 0, x1R, 0);
      wG.addColorStop(0,    '#c0cfe6');
      wG.addColorStop(0.3,  '#dde8f8');
      wG.addColorStop(0.5,  '#e8f2ff');
      wG.addColorStop(0.7,  '#d5e3f5');
      wG.addColorStop(1,    '#b0c2de');
      ctx.fillStyle = wG;
    } else {
      const bG = ctx.createLinearGradient(x1L, 0, x1R, 0);
      bG.addColorStop(0,   '#1a3470');
      bG.addColorStop(0.4, '#213d82');
      bG.addColorStop(0.6, '#1e3878');
      bG.addColorStop(1,   '#152a60');
      ctx.fillStyle = bG;
    }
    ctx.beginPath();
    ctx.moveTo(x1L, sy1);
    ctx.lineTo(x1R, sy1);
    ctx.lineTo(x2R, sy2);
    ctx.lineTo(x2L, sy2);
    ctx.closePath();
    ctx.fill();
  }

  // Small windows on tower body
  const winW2 = towerBotW * 0.12;
  const winH2 = stripeH * 0.40;
  for (const frac of [0.38, 0.68]) {
    const wy = towerTopY + (towerBotY - towerTopY) * frac - winH2 / 2;
    const rFrac = frac;
    const wx = cx - (towerTopW / 2 + rFrac * (towerBotW / 2 - towerTopW / 2)) * 0.15 - winW2 / 2;
    ctx.fillStyle = '#0a1830';
    roundRect(ctx, cx - winW2 / 2, wy, winW2, winH2, winW2 * 0.3);
    ctx.fill();
    ctx.strokeStyle = 'rgba(180,210,255,0.4)';
    ctx.lineWidth = S * 0.005;
    roundRect(ctx, cx - winW2 / 2, wy, winW2, winH2, winW2 * 0.3);
    ctx.stroke();
  }

  // Tower outline
  ctx.strokeStyle = 'rgba(80,120,200,0.25)';
  ctx.lineWidth = S * 0.008;
  ctx.beginPath();
  ctx.moveTo(towerBotX, towerBotY);
  ctx.lineTo(towerBotX + towerBotW, towerBotY);
  ctx.lineTo(towerTopX + towerTopW, towerTopY);
  ctx.lineTo(towerTopX, towerTopY);
  ctx.closePath();
  ctx.stroke();

  // ── Balcony / decorative ring near top ────────────────────────────────────
  const balcY  = towerTopY + stripeH * 0.5;
  const balcW  = towerTopW * 1.25;
  const balcH  = S * 0.025;
  ctx.fillStyle = '#c8d8f0';
  roundRect(ctx, cx - balcW / 2, balcY - balcH / 2, balcW, balcH, balcH / 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(100,140,200,0.4)';
  ctx.lineWidth = S * 0.007;
  roundRect(ctx, cx - balcW / 2, balcY - balcH / 2, balcW, balcH, balcH / 2);
  ctx.stroke();

  // ── Lantern room (dark box with bars) ─────────────────────────────────────
  const lrW = towerTopW * 1.1;
  const lrH = S * 0.09;
  const lrX = cx - lrW / 2;
  const lrY = towerTopY - lrH;

  // Dark box background
  ctx.fillStyle = '#080f22';
  roundRect(ctx, lrX, lrY, lrW, lrH, S * 0.01);
  ctx.fill();

  // Bars/grid on lantern room
  const barCount = 3;
  ctx.strokeStyle = 'rgba(100,140,200,0.55)';
  ctx.lineWidth = S * 0.008;
  for (let i = 1; i <= barCount; i++) {
    const bx = lrX + (lrW * i) / (barCount + 1);
    ctx.beginPath();
    ctx.moveTo(bx, lrY + S * 0.008);
    ctx.lineTo(bx, lrY + lrH - S * 0.008);
    ctx.stroke();
  }
  // Horizontal bar
  ctx.beginPath();
  ctx.moveTo(lrX + S * 0.008, lrY + lrH / 2);
  ctx.lineTo(lrX + lrW - S * 0.008, lrY + lrH / 2);
  ctx.stroke();
  // Border
  ctx.strokeStyle = 'rgba(140,180,240,0.5)';
  ctx.lineWidth = S * 0.010;
  roundRect(ctx, lrX, lrY, lrW, lrH, S * 0.01);
  ctx.stroke();

  // ── Dome / roof ────────────────────────────────────────────────────────────
  const domeBaseY = lrY;
  ctx.fillStyle = '#1a3060';
  ctx.beginPath();
  ctx.moveTo(lrX - S * 0.01, domeBaseY);
  ctx.quadraticCurveTo(cx, domeBaseY - S * 0.06, lrX + lrW + S * 0.01, domeBaseY);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = 'rgba(140,180,240,0.3)';
  ctx.lineWidth = S * 0.007;
  ctx.beginPath();
  ctx.moveTo(lrX - S * 0.01, domeBaseY);
  ctx.quadraticCurveTo(cx, domeBaseY - S * 0.06, lrX + lrW + S * 0.01, domeBaseY);
  ctx.stroke();

  // Spire
  const spireTopY = domeBaseY - S * 0.06;
  ctx.strokeStyle = 'rgba(200,220,255,0.7)';
  ctx.lineWidth = S * 0.010;
  ctx.beginPath();
  ctx.moveTo(cx, spireTopY);
  ctx.lineTo(cx, spireTopY - S * 0.07);
  ctx.stroke();
  // Ball on spire
  ctx.fillStyle = '#c8deff';
  ctx.beginPath();
  ctx.arc(cx, spireTopY - S * 0.075, S * 0.013, 0, Math.PI * 2);
  ctx.fill();

  // ── Beacon sphere (glowing blue ball) ─────────────────────────────────────
  const beaconX = cx;
  const beaconY2 = lrY + lrH * 0.45;
  const sphereR = lrH * 0.36;

  // Outer glow layers
  for (const [r, a] of [[sphereR * 3.5, 0.06], [sphereR * 2.2, 0.12], [sphereR * 1.5, 0.22]]) {
    const g = ctx.createRadialGradient(beaconX, beaconY2, 0, beaconX, beaconY2, r);
    g.addColorStop(0,   `rgba(120,180,255,${a})`);
    g.addColorStop(0.5, `rgba(80,140,255,${a * 0.5})`);
    g.addColorStop(1,   'rgba(60,100,220,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(beaconX, beaconY2, r, 0, Math.PI * 2);
    ctx.fill();
  }

  // Sphere
  const sGrad = ctx.createRadialGradient(
    beaconX - sphereR * 0.3, beaconY2 - sphereR * 0.3, sphereR * 0.05,
    beaconX, beaconY2, sphereR
  );
  sGrad.addColorStop(0,   '#ffffff');
  sGrad.addColorStop(0.25, '#c0e0ff');
  sGrad.addColorStop(0.6,  '#5baeff');
  sGrad.addColorStop(1,    '#2060cc');
  ctx.fillStyle = sGrad;
  ctx.beginPath();
  ctx.arc(beaconX, beaconY2, sphereR, 0, Math.PI * 2);
  ctx.fill();

  // Specular highlight
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  ctx.beginPath();
  ctx.arc(beaconX - sphereR * 0.28, beaconY2 - sphereR * 0.28, sphereR * 0.25, 0, Math.PI * 2);
  ctx.fill();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
}

const RES_DIR = path.resolve('android/app/src/main/res');

for (const { dir, size } of SIZES) {
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext('2d');
  drawIcon(ctx, size);
  const buf = canvas.toBuffer('image/png');
  const outDir = path.join(RES_DIR, dir);
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'ic_launcher.png'), buf);
  fs.writeFileSync(path.join(outDir, 'ic_launcher_round.png'), buf);
  console.log(`✓ ${dir}  ${size}x${size}`);
}
console.log('Done!');
