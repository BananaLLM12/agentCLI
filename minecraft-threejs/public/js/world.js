import * as THREE from 'three';
import { Noise } from './noise.js';
import { BLOCK, BLOCKS } from './blocks.js';

export const CHUNK_SIZE = 16;
export const CHUNK_HEIGHT = 64;
export const WORLD_HEIGHT = 64;
export const SEA_LEVEL = 24;

export class Chunk {
  constructor(cx, cz, world) {
    this.cx = cx;
    this.cz = cz;
    this.world = world;
    this.data = new Uint8Array(CHUNK_SIZE * CHUNK_HEIGHT * CHUNK_SIZE);
    this.mesh = null;
    this.waterMesh = null;
    this.generated = false;
    this.meshed = false;
  }

  getIndex(x, y, z) {
    return y * CHUNK_SIZE * CHUNK_SIZE + z * CHUNK_SIZE + x;
  }

  getBlock(x, y, z) {
    if (x < 0 || x >= CHUNK_SIZE || y < 0 || y >= CHUNK_HEIGHT || z < 0 || z >= CHUNK_SIZE) {
      return BLOCK.AIR;
    }
    return this.data[this.getIndex(x, y, z)];
  }

  setBlock(x, y, z, blockId) {
    if (x < 0 || x >= CHUNK_SIZE || y < 0 || y >= CHUNK_HEIGHT || z < 0 || z >= CHUNK_SIZE) return;
    this.data[this.getIndex(x, y, z)] = blockId;
    this.meshed = false;
  }

  generate() {
    const noise = this.world.noise;
    const worldX = this.cx * CHUNK_SIZE;
    const worldZ = this.cz * CHUNK_SIZE;

    for (let x = 0; x < CHUNK_SIZE; x++) {
      for (let z = 0; z < CHUNK_SIZE; z++) {
        const wx = worldX + x;
        const wz = worldZ + z;

        // Base terrain height using fractal noise
        const baseHeight = noise.fbm2D(wx * 0.01, wz * 0.01, 4, 0.5, 2.0);
        const detailHeight = noise.fbm2D(wx * 0.05, wz * 0.05, 3, 0.5, 2.0);
        let height = Math.floor(SEA_LEVEL + baseHeight * 20 + detailHeight * 5);
        height = Math.max(1, Math.min(CHUNK_HEIGHT - 10, height));

        // Mountain peaks
        const mountainNoise = noise.fbm2D(wx * 0.008, wz * 0.008, 2, 0.5, 2.0);
        if (mountainNoise > 0.3) {
          height += Math.floor((mountainNoise - 0.3) * 60);
          height = Math.min(CHUNK_HEIGHT - 1, height);
        }

        for (let y = 0; y <= height; y++) {
          let blockId = BLOCK.STONE;

          if (y === 0) {
            blockId = BLOCK.BEDROCK;
          } else if (y < height - 4) {
            blockId = BLOCK.STONE;
          } else if (y < height) {
            blockId = BLOCK.DIRT;
          } else {
            // Top block
            if (height <= SEA_LEVEL + 1) {
              blockId = BLOCK.SAND;
            } else if (height > SEA_LEVEL + 20) {
              blockId = BLOCK.STONE;
            } else {
              blockId = BLOCK.GRASS;
            }
          }

          // Water fill
          if (y > height && y <= SEA_LEVEL) {
            blockId = BLOCK.WATER;
          }

          this.data[this.getIndex(x, y, z)] = blockId;
        }

        // Tree generation
        if (height > SEA_LEVEL + 1 && height < SEA_LEVEL + 20) {
          const treeNoise = noise.noise2D(wx * 7.3, wz * 7.3);
          if (treeNoise > 0.92 && Math.random() < 0.3) {
            this.placeTree(x, height + 1, z);
          }
        }
      }
    }

    this.generated = true;
  }

  placeTree(x, baseY, z) {
    const treeHeight = 4 + Math.floor(Math.random() * 3);

    // Trunk
    for (let i = 0; i < treeHeight; i++) {
      const y = baseY + i;
      if (y < CHUNK_HEIGHT) {
        this.data[this.getIndex(x, y, z)] = BLOCK.WOOD;
      }
    }

    // Leaves - canopy
    const topY = baseY + treeHeight;
    for (let dy = -2; dy <= 1; dy++) {
      const radius = dy <= -1 ? 2 : 1;
      for (let dx = -radius; dx <= radius; dx++) {
        for (let dz = -radius; dz <= radius; dz++) {
          if (dx === 0 && dz === 0 && dy < 1) continue;
          const lx = x + dx;
          const ly = topY + dy;
          const lz = z + dz;
          if (lx >= 0 && lx < CHUNK_SIZE && lz >= 0 && lz < CHUNK_SIZE && ly < CHUNK_HEIGHT) {
            if (this.data[this.getIndex(lx, ly, lz)] === BLOCK.AIR) {
              // Round canopy
              const dist = Math.sqrt(dx * dx + dz * dz + dy * dy);
              if (dist <= radius + 0.5 || Math.random() > 0.3) {
                this.data[this.getIndex(lx, ly, lz)] = BLOCK.LEAVES;
              }
            }
          }
        }
      }
    }
  }

  buildMesh(materials) {
    this.buildPerBlockMesh(materials);
  }

  buildPerBlockMesh(materials) {
    if (this.mesh) {
      this.world.scene.remove(this.mesh);
      this.mesh.geometry.dispose();
    }
    if (this.waterMesh) {
      this.world.scene.remove(this.waterMesh);
      this.waterMesh.geometry.dispose();
    }
    this.mesh = null;
    this.waterMesh = null;

    // Group faces by composite key: "blockId_faceType" (top/bottom/side)
    const faceData = {};

    const worldX = this.cx * CHUNK_SIZE;
    const worldZ = this.cz * CHUNK_SIZE;

    // faceIdx 2 = +Y (top), 3 = -Y (bottom), 0,1,4,5 = sides
    const faces = [
      { dir: [1, 0, 0], corners: [[1,0,0],[1,1,0],[1,1,1],[1,0,1]], normal: [1,0,0], type: 'side' },
      { dir: [-1, 0, 0], corners: [[0,0,1],[0,1,1],[0,1,0],[0,0,0]], normal: [-1,0,0], type: 'side' },
      { dir: [0, 1, 0], corners: [[0,1,1],[1,1,1],[1,1,0],[0,1,0]], normal: [0,1,0], type: 'top' },
      { dir: [0, -1, 0], corners: [[0,0,0],[1,0,0],[1,0,1],[0,0,1]], normal: [0,-1,0], type: 'bottom' },
      { dir: [0, 0, 1], corners: [[1,0,1],[1,1,1],[0,1,1],[0,0,1]], normal: [0,0,1], type: 'side' },
      { dir: [0, 0, -1], corners: [[0,0,0],[0,1,0],[1,1,0],[1,0,0]], normal: [0,0,-1], type: 'side' },
    ];

    const faceUVs = [[0,0],[1,0],[1,1],[0,1]];

    const isExposed = (x, y, z, blockId) => {
      const neighbor = this.world.getBlock(this.cx, this.cz, x, y, z);
      if (neighbor === BLOCK.AIR) return true;
      const neighborBlock = BLOCKS[neighbor];
      if (neighbor === BLOCK.WATER && blockId === BLOCK.WATER) return false;
      if (neighborBlock.transparent && !neighborBlock.liquid && neighbor !== blockId) return true;
      if (neighborBlock.transparent && !neighborBlock.liquid && neighbor === blockId) return false;
      if (neighborBlock.transparent) return true;
      return false;
    };

    for (let y = 0; y < CHUNK_HEIGHT; y++) {
      for (let z = 0; z < CHUNK_SIZE; z++) {
        for (let x = 0; x < CHUNK_SIZE; x++) {
          const blockId = this.data[this.getIndex(x, y, z)];
          if (blockId === BLOCK.AIR) continue;

          const isWater = blockId === BLOCK.WATER;

          for (let f = 0; f < 6; f++) {
            const face = faces[f];
            const nx = x + face.dir[0];
            const ny = y + face.dir[1];
            const nz = z + face.dir[2];

            if (!isExposed(nx, ny, nz, blockId)) continue;
            if (isWater && f !== 2 && this.world.getBlock(this.cx, this.cz, nx, ny, nz) === BLOCK.WATER) continue;

            const key = `${blockId}_${face.type}`;
            if (!faceData[key]) {
              faceData[key] = { positions: [], normals: [], uvs: [], indices: [] };
            }
            const fd = faceData[key];
            const startIndex = fd.positions.length / 3;

            for (let c = 0; c < 4; c++) {
              const corner = face.corners[c];
              fd.positions.push(worldX + x + corner[0], y + corner[1], worldZ + z + corner[2]);
              fd.normals.push(face.normal[0], face.normal[1], face.normal[2]);
              fd.uvs.push(faceUVs[c][0], faceUVs[c][1]);
            }

            fd.indices.push(startIndex, startIndex + 1, startIndex + 2);
            fd.indices.push(startIndex, startIndex + 2, startIndex + 3);
          }
        }
      }
    }

    // Separate water from solid
    const waterKey = `${BLOCK.WATER}_top`;
    const waterKeys = [`${BLOCK.WATER}_top`, `${BLOCK.WATER}_bottom`, `${BLOCK.WATER}_side`];

    // Build water mesh
    let hasWater = false;
    for (const wk of waterKeys) {
      if (faceData[wk] && faceData[wk].positions.length > 0) { hasWater = true; break; }
    }

    if (hasWater) {
      const wPos = [], wNorm = [], wUv = [], wIdx = [];
      let wVertOffset = 0;

      for (const wk of waterKeys) {
        const fd = faceData[wk];
        if (!fd || fd.positions.length === 0) continue;
        wPos.push(...fd.positions);
        wNorm.push(...fd.normals);
        wUv.push(...fd.uvs);
        for (const idx of fd.indices) wIdx.push(idx + wVertOffset);
        wVertOffset += fd.positions.length / 3;
      }

      if (wPos.length > 0) {
        const wGeo = new THREE.BufferGeometry();
        wGeo.setAttribute('position', new THREE.Float32BufferAttribute(wPos, 3));
        wGeo.setAttribute('normal', new THREE.Float32BufferAttribute(wNorm, 3));
        wGeo.setAttribute('uv', new THREE.Float32BufferAttribute(wUv, 2));
        wGeo.setIndex(wIdx);

        const waterMat = this.world.materialArray[this.world.blockMaterialIndex[`${BLOCK.WATER}_side`]];
        this.waterMesh = new THREE.Mesh(wGeo, waterMat);
        this.waterMesh.chunkRef = this;
        this.world.scene.add(this.waterMesh);
      }
    }

    // Build solid mesh with material groups
    const sPos = [], sNorm = [], sUv = [], sIdx = [];
    const solidGroups = [];
    let sVertOffset = 0;
    let sIndexOffset = 0;

    // Sort keys for deterministic ordering
    const sortedKeys = Object.keys(faceData).sort();

    for (const key of sortedKeys) {
      // Skip water
      if (key.startsWith(`${BLOCK.WATER}_`)) continue;

      const fd = faceData[key];
      if (fd.positions.length === 0) continue;

      const matIndex = this.world.blockMaterialIndex[key];
      if (matIndex === undefined) continue;

      const groupStart = sIndexOffset;
      const numIndices = fd.indices.length;

      sPos.push(...fd.positions);
      sNorm.push(...fd.normals);
      sUv.push(...fd.uvs);
      for (const idx of fd.indices) sIdx.push(idx + sVertOffset);
      sVertOffset += fd.positions.length / 3;
      sIndexOffset += numIndices;

      solidGroups.push({ start: groupStart, count: numIndices, materialIndex: matIndex });
    }

    if (sPos.length > 0) {
      const solidGeometry = new THREE.BufferGeometry();
      solidGeometry.setAttribute('position', new THREE.Float32BufferAttribute(sPos, 3));
      solidGeometry.setAttribute('normal', new THREE.Float32BufferAttribute(sNorm, 3));
      solidGeometry.setAttribute('uv', new THREE.Float32BufferAttribute(sUv, 2));
      solidGeometry.setIndex(sIdx);

      for (const group of solidGroups) {
        solidGeometry.addGroup(group.start, group.count, group.materialIndex);
      }

      this.mesh = new THREE.Mesh(solidGeometry, this.world.materialArray);
      this.mesh.chunkRef = this;
      this.world.scene.add(this.mesh);
    }

    this.meshed = true;
  }

  dispose() {
    if (this.mesh) {
      this.world.scene.remove(this.mesh);
      this.mesh.geometry.dispose();
      this.mesh = null;
    }
    if (this.waterMesh) {
      this.world.scene.remove(this.waterMesh);
      this.waterMesh.geometry.dispose();
      this.waterMesh = null;
    }
  }
}

export class World {
  constructor(scene, materials, blockMaterialIndex, materialArray, seed = 12345) {
    this.scene = scene;
    this.materials = materials;
    this.blockMaterialIndex = blockMaterialIndex;
    this.materialArray = materialArray;
    this.noise = new Noise(seed);
    this.chunks = new Map();
    this.renderDistance = 6;
  }

  chunkKey(cx, cz) {
    return `${cx},${cz}`;
  }

  getChunk(cx, cz) {
    return this.chunks.get(this.chunkKey(cx, cz));
  }

  getBlock(cx, cz, x, y, z) {
    // Handle cross-chunk lookups
    if (y < 0 || y >= CHUNK_HEIGHT) return BLOCK.AIR;

    let chunkX = x;
    let chunkZ = z;
    let targetCX = cx;
    let targetCZ = cz;

    if (x < 0) { targetCX = cx - 1; chunkX = CHUNK_SIZE + x; }
    else if (x >= CHUNK_SIZE) { targetCX = cx + 1; chunkX = x - CHUNK_SIZE; }
    if (z < 0) { targetCZ = cz - 1; chunkZ = CHUNK_SIZE + z; }
    else if (z >= CHUNK_SIZE) { targetCZ = cz + 1; chunkZ = z - CHUNK_SIZE; }

    const chunk = this.getChunk(targetCX, targetCZ);
    if (!chunk || !chunk.generated) return BLOCK.AIR;
    return chunk.getBlock(chunkX, y, chunkZ);
  }

  setBlock(wx, wy, wz, blockId) {
    if (wy < 0 || wy >= CHUNK_HEIGHT) return;

    const cx = Math.floor(wx / CHUNK_SIZE);
    const cz = Math.floor(wz / CHUNK_SIZE);
    const lx = ((wx % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;
    const lz = ((wz % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;

    const chunk = this.getChunk(cx, cz);
    if (!chunk) return;

    chunk.setBlock(lx, wy, lz, blockId);
    chunk.buildMesh(this.materials);

    // Rebuild neighbor chunks if on border
    if (lx === 0) {
      const neighbor = this.getChunk(cx - 1, cz);
      if (neighbor) neighbor.buildMesh(this.materials);
    }
    if (lx === CHUNK_SIZE - 1) {
      const neighbor = this.getChunk(cx + 1, cz);
      if (neighbor) neighbor.buildMesh(this.materials);
    }
    if (lz === 0) {
      const neighbor = this.getChunk(cx, cz - 1);
      if (neighbor) neighbor.buildMesh(this.materials);
    }
    if (lz === CHUNK_SIZE - 1) {
      const neighbor = this.getChunk(cx, cz + 1);
      if (neighbor) neighbor.buildMesh(this.materials);
    }
  }

  getBlockWorld(wx, wy, wz) {
    if (wy < 0 || wy >= CHUNK_HEIGHT) return BLOCK.AIR;

    const cx = Math.floor(wx / CHUNK_SIZE);
    const cz = Math.floor(wz / CHUNK_SIZE);
    const lx = ((wx % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;
    const lz = ((wz % CHUNK_SIZE) + CHUNK_SIZE) % CHUNK_SIZE;

    const chunk = this.getChunk(cx, cz);
    if (!chunk || !chunk.generated) return BLOCK.AIR;
    return chunk.getBlock(lx, wy, lz);
  }

  generateChunk(cx, cz) {
    const key = this.chunkKey(cx, cz);
    if (this.chunks.has(key)) return this.chunks.get(key);

    const chunk = new Chunk(cx, cz, this);
    chunk.generate();
    this.chunks.set(key, chunk);
    return chunk;
  }

  update(playerX, playerZ) {
    const pcx = Math.floor(playerX / CHUNK_SIZE);
    const pcz = Math.floor(playerZ / CHUNK_SIZE);

    // Generate and mesh chunks within render distance
    const toGenerate = [];
    for (let dx = -this.renderDistance; dx <= this.renderDistance; dx++) {
      for (let dz = -this.renderDistance; dz <= this.renderDistance; dz++) {
        const cx = pcx + dx;
        const cz = pcz + dz;
        const dist = Math.sqrt(dx * dx + dz * dz);
        if (dist > this.renderDistance) continue;

        const chunk = this.generateChunk(cx, cz);
        if (!chunk.meshed) {
          toGenerate.push({ chunk, dist });
        }
      }
    }

    // Sort by distance and mesh closest first, limit per frame
    toGenerate.sort((a, b) => a.dist - b.dist);
    const maxPerFrame = 2;
    for (let i = 0; i < Math.min(maxPerFrame, toGenerate.length); i++) {
      toGenerate[i].chunk.buildMesh(this.materials);
    }

    // Unload distant chunks
    const unloadDist = this.renderDistance + 2;
    for (const [key, chunk] of this.chunks) {
      const dx = chunk.cx - pcx;
      const dz = chunk.cz - pcz;
      if (Math.sqrt(dx * dx + dz * dz) > unloadDist) {
        chunk.dispose();
        this.chunks.delete(key);
      }
    }
  }

  getLoadedChunkCount() {
    return this.chunks.size;
  }
}
