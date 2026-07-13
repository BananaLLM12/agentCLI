// world.js — chunked voxel world: terrain gen, face-culled meshing, raycast.

const CHUNK = 16;
const HEIGHT = 40;
const SEA_LEVEL = 22;
const WORLD_CHUNKS = 6; // WORLD_CHUNKS x WORLD_CHUNKS chunks => 96x96 columns

// face definitions: dir + 4 corner offsets (CCW from outside) + per-corner uv
const FACES = [
  { dir: [ 1, 0, 0], corners: [ [1,1,0],[1,0,0],[1,0,1],[1,1,1] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'side'  },
  { dir: [-1, 0, 0], corners: [ [0,1,1],[0,0,1],[0,0,0],[0,1,0] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'side'  },
  { dir: [ 0, 1, 0], corners: [ [0,1,1],[1,1,1],[1,1,0],[0,1,0] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'top'   },
  { dir: [ 0,-1, 0], corners: [ [0,0,0],[1,0,0],[1,0,1],[0,0,1] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'bottom'},
  { dir: [ 0, 0, 1], corners: [ [1,1,1],[1,0,1],[0,0,1],[0,1,1] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'side'  },
  { dir: [ 0, 0,-1], corners: [ [0,1,0],[0,0,0],[1,0,0],[1,1,0] ], uv: [[0,1],[0,0],[1,0],[1,1]], kind: 'side'  },
];

class Chunk {
  constructor(cx, cz) {
    this.cx = cx; this.cz = cz;
    this.blocks = new Uint8Array(CHUNK * CHUNK * HEIGHT);
    this.opaqueMesh = null;
    this.transMesh = null;
    this.dirty = true;
  }
  idx(x, y, z) { return (y * CHUNK + z) * CHUNK + x; }
  get(x, y, z) {
    if (y < 0 || y >= HEIGHT) return 0;
    return this.blocks[this.idx(x, y, z)];
  }
  set(x, y, z, v) {
    if (y < 0 || y >= HEIGHT) return;
    this.blocks[this.idx(x, y, z)] = v;
  }
}

class World {
  constructor(scene, atlasTexture) {
    this.scene = scene;
    this.atlas = atlasTexture;
    this.noise = new Noise(20240528);
    this.treeNoise = new Noise(777);
    this.chunks = new Map();
    this.seedRand = rng => rng; // placeholder
    // materials
    this.matOpaque = new THREE.MeshLambertMaterial({ map: atlasTexture, alphaTest: 0.5, side: THREE.FrontSide });
    this.matTrans = new THREE.MeshLambertMaterial({ map: atlasTexture, transparent: true, depthWrite: false, side: THREE.DoubleSide, opacity: 0.85 });
  }

  key(cx, cz) { return cx + ',' + cz; }
  getChunk(cx, cz) { return this.chunks.get(this.key(cx, cz)); }

  // world-coord block access (handles chunk lookup)
  getBlock(x, y, z) {
    if (y < 0 || y >= HEIGHT) return 0;
    const cx = Math.floor(x / CHUNK), cz = Math.floor(z / CHUNK);
    const c = this.getChunk(cx, cz);
    if (!c) return 0;
    const lx = x - cx * CHUNK, lz = z - cz * CHUNK;
    return c.get(lx, y, lz);
  }
  setBlock(x, y, z, v) {
    if (y < 0 || y >= HEIGHT) return false;
    const cx = Math.floor(x / CHUNK), cz = Math.floor(z / CHUNK);
    const c = this.getChunk(cx, cz);
    if (!c) return false;
    const lx = x - cx * CHUNK, lz = z - cz * CHUNK;
    c.set(lx, y, lz, v);
    c.dirty = true;
    // mark neighbor chunk dirty if on border
    if (lx === 0)        this._markDirty(cx - 1, cz);
    if (lx === CHUNK - 1) this._markDirty(cx + 1, cz);
    if (lz === 0)        this._markDirty(cx, cz - 1);
    if (lz === CHUNK - 1) this._markDirty(cx, cz + 1);
    return true;
  }
  _markDirty(cx, cz) { const c = this.getChunk(cx, cz); if (c) c.dirty = true; }

  isSolid(x, y, z) {
    const b = this.getBlock(x | 0, y | 0, z | 0);
    const def = Blocks.BLOCKS[b];
    return def && def.solid;
  }

  // ---- terrain generation ----
  columnHeight(wx, wz) {
    const n = this.noise;
    let h = 18
      + n.fbm2(wx * 0.018, wz * 0.018, 5) * 18
      + n.fbm2(wx * 0.08, wz * 0.08, 3) * 4;
    return Math.max(1, Math.min(HEIGHT - 6, Math.floor(h)));
  }

  generateAll() {
    const total = WORLD_CHUNKS * WORLD_CHUNKS;
    for (let cx = 0; cx < WORLD_CHUNKS; cx++)
      for (let cz = 0; cz < WORLD_CHUNKS; cz++)
        this.generateChunk(cx, cz);
    // second pass: mesh now that all data exists (so borders cull correctly)
    for (const c of this.chunks.values()) this.remesh(c);
  }

  generateChunk(cx, cz) {
    const c = new Chunk(cx, cz);
    this.chunks.set(this.key(cx, cz), c);
    for (let lx = 0; lx < CHUNK; lx++) {
      for (let lz = 0; lz < CHUNK; lz++) {
        const wx = cx * CHUNK + lx, wz = cz * CHUNK + lz;
        const h = this.columnHeight(wx, wz);
        for (let y = 0; y <= h; y++) {
          let id = 3; // stone
          if (y === 0) id = 13; // bedrock
          else if (y > h - 4) id = 2; // dirt
          // top block
          if (y === h) {
            if (h <= SEA_LEVEL + 1) id = 5;       // sand near water
            else if (h >= 34) id = 11;            // snow on peaks
            else id = 1;                          // grass
          }
          c.set(lx, y, lz, id);
        }
        // water fill up to sea level
        for (let y = h + 1; y <= SEA_LEVEL; y++) c.set(lx, y, lz, 12);
        // trees on grass tops, above water, not on borders
        if (h > SEA_LEVEL + 1 && h < 33 && lx > 1 && lx < CHUNK - 2 && lz > 1 && lz < CHUNK - 2) {
          const tn = this.treeNoise.noise2(wx * 1.7, wz * 1.7);
          if (tn > 0.86) this.plantTree(c, lx, h + 1, lz);
        }
      }
    }
  }

  plantTree(c, x, baseY, z) {
    const th = 4 + ((this.treeNoise.noise2(x * 9.1, z * 9.1) * 2) | 0); // 4-5 trunk
    for (let y = 0; y < th; y++) c.set(x, baseY + y, z, 6); // log
    const topY = baseY + th - 1;
    // leaf canopy
    for (let dy = -1; dy <= 2; dy++) {
      const r = dy <= 0 ? 2 : 1;
      for (let dx = -r; dx <= r; dx++)
        for (let dz = -r; dz <= r; dz++) {
          if (dx === 0 && dz === 0 && dy < 2) continue; // keep trunk
          if (Math.abs(dx) === r && Math.abs(dz) === r && Math.random() < 0.5) continue;
          const lx = x + dx, ly = topY + dy, lz = z + dz;
          if (lx >= 0 && lx < CHUNK && lz >= 0 && lz < CHUNK && ly < HEIGHT) {
            if (c.get(lx, ly, lz) === 0) c.set(lx, ly, lz, 7);
          }
        }
    }
  }

  // ---- meshing ----
  remesh(c) {
    if (c.opaqueMesh) { this.scene.remove(c.opaqueMesh); c.opaqueMesh.geometry.dispose(); c.opaqueMesh = null; }
    if (c.transMesh)  { this.scene.remove(c.transMesh);  c.transMesh.geometry.dispose();  c.transMesh = null; }

    const op = { pos: [], norm: [], uv: [], idx: [] };
    const tr = { pos: [], norm: [], uv: [], idx: [] };
    const baseX = c.cx * CHUNK, baseZ = c.cz * CHUNK;

    for (let y = 0; y < HEIGHT; y++)
      for (let z = 0; z < CHUNK; z++)
        for (let x = 0; x < CHUNK; x++) {
          const id = c.get(x, y, z);
          if (id === 0) continue;
          const def = Blocks.BLOCKS[id];
          if (!def) continue;
          const wx = baseX + x, wz = baseZ + z;
          // route water+glass to transparent mesh; everything else opaque
          const target = (id === 12 || id === 10) ? tr : op;

          for (let f = 0; f < 6; f++) {
            const face = FACES[f];
            const nx = wx + face.dir[0], ny = y + face.dir[1], nz = wz + face.dir[2];
            const nid = this.getBlock(nx, ny, nz);
            const ndef = Blocks.BLOCKS[nid];
            // draw face if neighbor is air, or neighbor transparent and different type
            if (nid !== 0 && (!ndef.transparent || nid === id)) continue;

            // pick tile
            let tileIdx;
            if (face.kind === 'top') tileIdx = def.faces.top;
            else if (face.kind === 'bottom') tileIdx = def.faces.bottom;
            else tileIdx = def.faces.side;
            const uvRect = Blocks.tileUV(tileIdx);

            const start = target.pos.length / 3;
            for (let i = 0; i < 4; i++) {
              const cor = face.corners[i];
              target.pos.push(wx + cor[0], y + cor[1], wz + cor[2]);
              target.norm.push(face.dir[0], face.dir[1], face.dir[2]);
              const cu = face.uv[i];
              target.uv.push(
                uvRect.u0 + (uvRect.u1 - uvRect.u0) * cu[0],
                uvRect.v0 + (uvRect.v1 - uvRect.v0) * cu[1]
              );
            }
            target.idx.push(start, start + 1, start + 2, start, start + 2, start + 3);
          }
        }

    if (op.idx.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(op.pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(op.norm, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(op.uv, 2));
      g.setIndex(op.idx);
      c.opaqueMesh = new THREE.Mesh(g, this.matOpaque);
      c.opaqueMesh.frustumCulled = true;
      this.scene.add(c.opaqueMesh);
    }
    if (tr.idx.length) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(tr.pos, 3));
      g.setAttribute('normal', new THREE.Float32BufferAttribute(tr.norm, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(tr.uv, 2));
      g.setIndex(tr.idx);
      c.transMesh = new THREE.Mesh(g, this.matTrans);
      c.transMesh.renderOrder = 1;
      this.scene.add(c.transMesh);
    }
    c.dirty = false;
  }

  remeshDirty() {
    for (const c of this.chunks.values()) if (c.dirty) this.remesh(c);
  }

  // ---- voxel raycast (Amanatides & Woo) ----
  // returns { x,y,z, nx,ny,nz } of first solid hit, or null
  raycast(origin, dir, maxDist = 6) {
    let x = Math.floor(origin.x), y = Math.floor(origin.y), z = Math.floor(origin.z);
    const stepX = Math.sign(dir.x), stepY = Math.sign(dir.y), stepZ = Math.sign(dir.z);
    const tDeltaX = dir.x !== 0 ? Math.abs(1 / dir.x) : Infinity;
    const tDeltaY = dir.y !== 0 ? Math.abs(1 / dir.y) : Infinity;
    const tDeltaZ = dir.z !== 0 ? Math.abs(1 / dir.z) : Infinity;
    // initial distances to first boundaries
    let tMaxX = dir.x !== 0
      ? (stepX > 0 ? (x + 1 - origin.x) : (origin.x - x)) * tDeltaX : Infinity;
    let tMaxY = dir.y !== 0
      ? (stepY > 0 ? (y + 1 - origin.y) : (origin.y - y)) * tDeltaY : Infinity;
    let tMaxZ = dir.z !== 0
      ? (stepZ > 0 ? (z + 1 - origin.z) : (origin.z - z)) * tDeltaZ : Infinity;
    let nx = 0, ny = 0, nz = 0;
    let t = 0;
    while (t <= maxDist) {
      const id = this.getBlock(x, y, z);
      const def = Blocks.BLOCKS[id];
      if (def && def.solid) return { x, y, z, nx, ny, nz };
      if (tMaxX < tMaxY && tMaxX < tMaxZ) {
        x += stepX; t = tMaxX; tMaxX += tDeltaX; nx = -stepX; ny = 0; nz = 0;
      } else if (tMaxY < tMaxZ) {
        y += stepY; t = tMaxY; tMaxY += tDeltaY; nx = 0; ny = -stepY; nz = 0;
      } else {
        z += stepZ; t = tMaxZ; tMaxZ += tDeltaZ; nx = 0; ny = 0; nz = -stepZ;
      }
    }
    return null;
  }

  // world bounds for collision/fences
  get minBound() { return 0; }
  get maxBound() { return WORLD_CHUNKS * CHUNK; }
}

window.World = World;
window.WORLD_CONST = { CHUNK, HEIGHT, SEA_LEVEL, WORLD_CHUNKS };
