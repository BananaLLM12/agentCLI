// blocks.js — block registry + procedural pixel texture atlas.
// Every texture is drawn on a 16x16 canvas tile, packed into one atlas,
// so there are zero external assets.

const TILE = 16;            // pixels per texture tile
const ATLAS_COLS = 8;       // tiles per row in the atlas

// Tile indices in the atlas (row-major)
const T = {
  GRASS_TOP: 0, GRASS_SIDE: 1, DIRT: 2, STONE: 3, COBBLE: 4,
  SAND: 5, LOG_SIDE: 6, LOG_TOP: 7, LEAVES: 8, PLANKS: 9,
  BRICK: 10, GLASS: 11, SNOW: 12, WATER: 13, BEDROCK: 14, GRAVEL: 15
};

// ---- tiny pixel helpers -------------------------------------------------
function rng(seed) { // mulberry32
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
function shade(hex, amt) { // amt in [-1,1]
  const c = parseInt(hex.slice(1), 16);
  let r = (c >> 16) & 255, g = (c >> 8) & 255, b = c & 255;
  if (amt > 0) { r += (255 - r) * amt; g += (255 - g) * amt; b += (255 - b) * amt; }
  else { r *= (1 + amt); g *= (1 + amt); b *= (1 + amt); }
  return `rgb(${r|0},${g|0},${b|0})`;
}

// fill a tile with a base color + per-pixel noise for texture
function noisy(ctx, ox, oy, base, variance, seed) {
  const r = rng(seed);
  for (let y = 0; y < TILE; y++) for (let x = 0; x < TILE; x++) {
    const v = (r() - 0.5) * 2 * variance;
    ctx.fillStyle = shade(base, v);
    ctx.fillRect(ox + x, oy + y, 1, 1);
  }
}

// grass top: green with sparse darker/lighter blades
function grassTop(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#5fa83a', 0.12, seed);
  const r = rng(seed + 1);
  for (let i = 0; i < 26; i++) {
    const x = (r() * TILE) | 0, y = (r() * TILE) | 0;
    ctx.fillStyle = r() > 0.5 ? shade('#5fa83a', 0.18) : shade('#5fa83a', -0.18);
    ctx.fillRect(ox + x, oy + y, 1, 1);
  }
}

// grass side: dirt with a grassy top band + drips
function grassSide(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#8a6a43', 0.14, seed + 2); // dirt body
  const r = rng(seed + 3);
  for (let x = 0; x < TILE; x++) {
    const h = 3 + ((r() * 3) | 0); // grass overhang height
    for (let y = 0; y < h; y++) {
      ctx.fillStyle = shade('#5fa83a', (r() - 0.5) * 0.2);
      ctx.fillRect(ox + x, oy + y, 1, 1);
    }
  }
}

function logTop(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#b08a52', 0.08, seed + 4);
  ctx.strokeStyle = 'rgba(90,60,30,.7)';
  for (let rad = 2; rad <= 7; rad += 2) {
    ctx.beginPath();
    ctx.arc(ox + 8, oy + 8, rad, 0, Math.PI * 2);
    ctx.stroke();
  }
}
function logSide(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#6e4f2a', 0.10, seed + 5);
  const r = rng(seed + 6);
  for (let x = 0; x < TILE; x += 1) {
    if (r() > 0.7) { ctx.fillStyle = shade('#6e4f2a', -0.2); ctx.fillRect(ox + x, oy + 0, 1, TILE); }
  }
}

function leaves(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#3a7d2c', 0.18, seed + 7);
  const r = rng(seed + 8);
  for (let i = 0; i < 40; i++) {
    const x = (r() * TILE) | 0, y = (r() * TILE) | 0;
    ctx.fillStyle = r() > 0.5 ? shade('#3a7d2c', 0.25) : shade('#3a7d2c', -0.25);
    ctx.fillRect(ox + x, oy + y, 1, 1);
  }
}

function brick(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#9c4b3b', 0.06, seed + 9);
  ctx.fillStyle = 'rgba(40,20,16,.55)';
  // mortar grid, offset rows
  for (let y = 0; y < TILE; y += 4) for (let x = 0; x < TILE; x++) ctx.fillRect(ox + x, oy + y, 1, 1);
  for (let y = 0; y < TILE; y += 8) for (let x = 0; x < TILE; x += 8) ctx.fillRect(ox + x, oy + y + 4, 1, 1);
}

function glass(ctx, ox, oy, seed) {
  ctx.clearRect(ox, oy, TILE, TILE);
  ctx.fillStyle = 'rgba(180,220,235,.18)';
  ctx.fillRect(ox, oy, TILE, TILE);
  ctx.strokeStyle = 'rgba(255,255,255,.6)';
  ctx.strokeRect(ox + 0.5, oy + 0.5, TILE - 1, TILE - 1);
  ctx.strokeStyle = 'rgba(255,255,255,.3)';
  ctx.beginPath(); ctx.moveTo(ox + 3, oy + 3); ctx.lineTo(ox + 11, oy + 9); ctx.stroke();
}

function water(ctx, ox, oy, seed) {
  noisy(ctx, ox, oy, '#2f6fd6', 0.08, seed + 11);
  const r = rng(seed + 12);
  for (let i = 0; i < 10; i++) {
    const y = (r() * TILE) | 0;
    ctx.fillStyle = 'rgba(255,255,255,.18)';
    ctx.fillRect(ox, oy + y, TILE, 1);
  }
}

// Build the atlas canvas once
function buildAtlas() {
  const cols = ATLAS_COLS;
  const rows = Math.ceil(16 / cols);
  const canvas = document.createElement('canvas');
  canvas.width = cols * TILE;
  canvas.height = rows * TILE;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;

  const draw = (idx, fn, base, variance, seed) => {
    const ox = (idx % cols) * TILE;
    const oy = Math.floor(idx / cols) * TILE;
    if (fn) fn(ctx, ox, oy, seed);
    else noisy(ctx, ox, oy, base, variance, seed);
  };

  draw(T.GRASS_TOP, grassTop, null, null, 11);
  draw(T.GRASS_SIDE, grassSide, null, null, 22);
  draw(T.DIRT, null, '#8a6a43', 0.14, 33);
  draw(T.STONE, null, '#888888', 0.10, 44);
  draw(T.COBBLE, null, '#7a7a7a', 0.22, 55);
  draw(T.SAND, null, '#e6d9a0', 0.08, 66);
  draw(T.LOG_SIDE, logSide, null, null, 77);
  draw(T.LOG_TOP, logTop, null, null, 88);
  draw(T.LEAVES, leaves, null, null, 99);
  draw(T.PLANKS, null, '#b5853d', 0.10, 110);
  draw(T.BRICK, brick, null, null, 121);
  draw(T.GLASS, glass, null, null, 132);
  draw(T.SNOW, null, '#f4f6fa', 0.05, 143);
  draw(T.WATER, water, null, null, 154);
  draw(T.BEDROCK, null, '#2b2b2b', 0.30, 165);
  draw(T.GRAVEL, null, '#7d7368', 0.20, 176);

  return canvas;
}

// Block registry: id -> { name, solid, transparent, faces: {top,side,bottom} tile indices }
const BLOCKS = {
  0: { name: 'air',    solid: false, transparent: true },
  1: { name: 'grass',  solid: true,  transparent: false, faces: { top: T.GRASS_TOP, side: T.GRASS_SIDE, bottom: T.DIRT } },
  2: { name: 'dirt',   solid: true,  transparent: false, faces: { top: T.DIRT, side: T.DIRT, bottom: T.DIRT } },
  3: { name: 'stone',  solid: true,  transparent: false, faces: { top: T.STONE, side: T.STONE, bottom: T.STONE } },
  4: { name: 'cobble', solid: true,  transparent: false, faces: { top: T.COBBLE, side: T.COBBLE, bottom: T.COBBLE } },
  5: { name: 'sand',   solid: true,  transparent: false, faces: { top: T.SAND, side: T.SAND, bottom: T.SAND } },
  6: { name: 'log',    solid: true,  transparent: false, faces: { top: T.LOG_TOP, side: T.LOG_SIDE, bottom: T.LOG_TOP } },
  7: { name: 'leaves', solid: true,  transparent: true,  faces: { top: T.LEAVES, side: T.LEAVES, bottom: T.LEAVES } },
  8: { name: 'planks', solid: true,  transparent: false, faces: { top: T.PLANKS, side: T.PLANKS, bottom: T.PLANKS } },
  9: { name: 'brick',  solid: true,  transparent: false, faces: { top: T.BRICK, side: T.BRICK, bottom: T.BRICK } },
  10:{ name: 'glass',  solid: true,  transparent: true,  faces: { top: T.GLASS, side: T.GLASS, bottom: T.GLASS } },
  11:{ name: 'snow',   solid: true,  transparent: false, faces: { top: T.SNOW, side: T.SNOW, bottom: T.DIRT } },
  12:{ name: 'water',  solid: false, transparent: true,  faces: { top: T.WATER, side: T.WATER, bottom: T.WATER } },
  13:{ name: 'bedrock',solid: true,  transparent: false, faces: { top: T.BEDROCK, side: T.BEDROCK, bottom: T.BEDROCK } },
  14:{ name: 'gravel', solid: true,  transparent: false, faces: { top: T.GRAVEL, side: T.GRAVEL, bottom: T.GRAVEL } },
};

// Hotbar selection (ids)
const HOTBAR = [1, 2, 3, 4, 5, 6, 7, 8, 9]; // grass, dirt, stone, cobble, sand, log, leaves, planks, brick

// UV rect for a tile index, in atlas fractions
function tileUV(idx) {
  const cols = ATLAS_COLS;
  const x = (idx % cols);
  const y = Math.floor(idx / cols);
  const colsPx = cols * TILE;
  const rowsPx = Math.ceil(16 / cols) * TILE;
  // small inset to avoid bleeding
  const inset = 0.5 / colsPx;
  return {
    u0: (x * TILE) / colsPx + inset,
    u1: ((x + 1) * TILE) / colsPx - inset,
    v0: 1 - ((y + 1) * TILE) / rowsPx + inset,
    v1: 1 - (y * TILE) / rowsPx - inset,
  };
}

window.Blocks = { BLOCKS, HOTBAR, buildAtlas, tileUV, TILE, ATLAS_COLS, T };
