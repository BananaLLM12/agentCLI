import * as THREE from 'three';

// Block type IDs
export const BLOCK = {
  AIR: 0,
  GRASS: 1,
  DIRT: 2,
  STONE: 3,
  WOOD: 4,
  LEAVES: 5,
  SAND: 6,
  WATER: 7,
  BEDROCK: 8,
  PLANKS: 9,
  COBBLESTONE: 10,
  GLASS: 11,
  BRICK: 12,
  GLOWSTONE: 13,
};

export const BLOCK_NAMES = {
  [BLOCK.GRASS]: 'Grass',
  [BLOCK.DIRT]: 'Dirt',
  [BLOCK.STONE]: 'Stone',
  [BLOCK.WOOD]: 'Wood',
  [BLOCK.LEAVES]: 'Leaves',
  [BLOCK.SAND]: 'Sand',
  [BLOCK.WATER]: 'Water',
  [BLOCK.BEDROCK]: 'Bedrock',
  [BLOCK.PLANKS]: 'Planks',
  [BLOCK.COBBLESTONE]: 'Cobblestone',
  [BLOCK.GLASS]: 'Glass',
  [BLOCK.BRICK]: 'Brick',
  [BLOCK.GLOWSTONE]: 'Glowstone',
};

// Block properties
export const BLOCKS = {};

function defineBlock(id, props) {
  BLOCKS[id] = Object.assign({ id, solid: true, transparent: false, liquid: false, light: 0 }, props);
}

defineBlock(BLOCK.AIR, { solid: false, transparent: true });
defineBlock(BLOCK.GRASS, { topColor: 0x4a9d3a, sideColor: 0x8b6a3e, bottomColor: 0x6b4e2e, transparent: false });
defineBlock(BLOCK.DIRT, { topColor: 0x6b4e2e, sideColor: 0x6b4e2e, bottomColor: 0x6b4e2e });
defineBlock(BLOCK.STONE, { topColor: 0x888888, sideColor: 0x888888, bottomColor: 0x888888 });
defineBlock(BLOCK.WOOD, { topColor: 0xb8945a, sideColor: 0x6e5230, bottomColor: 0xb8945a });
defineBlock(BLOCK.LEAVES, { topColor: 0x3a7d2a, sideColor: 0x3a7d2a, bottomColor: 0x3a7d2a, transparent: true });
defineBlock(BLOCK.SAND, { topColor: 0xe6d9a0, sideColor: 0xe6d9a0, bottomColor: 0xe6d9a0 });
defineBlock(BLOCK.WATER, { topColor: 0x3a6ec5, sideColor: 0x3a6ec5, bottomColor: 0x3a6ec5, solid: false, transparent: true, liquid: true });
defineBlock(BLOCK.BEDROCK, { topColor: 0x333333, sideColor: 0x333333, bottomColor: 0x333333 });
defineBlock(BLOCK.PLANKS, { topColor: 0xb8945a, sideColor: 0xa07d45, bottomColor: 0xb8945a });
defineBlock(BLOCK.COBBLESTONE, { topColor: 0x777777, sideColor: 0x777777, bottomColor: 0x777777 });
defineBlock(BLOCK.GLASS, { topColor: 0xaaccff, sideColor: 0xaaccff, bottomColor: 0xaaccff, transparent: true });
defineBlock(BLOCK.BRICK, { topColor: 0x9c4a3a, sideColor: 0x9c4a3a, bottomColor: 0x9c4a3a });
defineBlock(BLOCK.GLOWSTONE, { topColor: 0xffd44a, sideColor: 0xffd44a, bottomColor: 0xffd44a, light: 15 });

// Procedural texture generation
export function createBlockTextures() {
  const textures = {};
  const textureSize = 16;

  function makeTexture(drawFn) {
    const canvas = document.createElement('canvas');
    canvas.width = textureSize;
    canvas.height = textureSize;
    const ctx = canvas.getContext('2d');
    drawFn(ctx, textureSize);

    const texture = new THREE.CanvasTexture(canvas);
    texture.magFilter = THREE.NearestFilter;
    texture.minFilter = THREE.NearestFilter;
    texture.colorSpace = THREE.SRGBColorSpace;
    return texture;
  }

  // Simple noise helper for texture detail
  function texNoise(ctx, baseColor, variance, size) {
    ctx.fillStyle = baseColor;
    ctx.fillRect(0, 0, size, size);
    for (let i = 0; i < size; i++) {
      for (let j = 0; j < size; j++) {
        const r = (Math.random() - 0.5) * variance;
        const pixel = ctx.getImageData(i, j, 1, 1);
        pixel.data[0] = Math.max(0, Math.min(255, pixel.data[0] + r));
        pixel.data[1] = Math.max(0, Math.min(255, pixel.data[1] + r));
        pixel.data[2] = Math.max(0, Math.min(255, pixel.data[2] + r));
        ctx.putImageData(pixel, i, j);
      }
    }
  }

  // Grass top
  textures[BLOCK.GRASS + '_top'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#4a9d3a', 40, s);
  });
  // Grass side (dirt with grass top edge)
  textures[BLOCK.GRASS + '_side'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#6b4e2e', 30, s);
    // green top strip
    for (let x = 0; x < s; x++) {
      for (let y = 0; y < 4; y++) {
        const r = (Math.random() - 0.5) * 40;
        ctx.fillStyle = `rgb(${74 + r}, ${157 + r}, ${58 + r})`;
        ctx.fillRect(x, y, 1, 1);
      }
    }
  });
  textures[BLOCK.GRASS + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#6b4e2e', 30, s);
  });

  // Dirt
  textures[BLOCK.DIRT + '_top'] = textures[BLOCK.DIRT + '_side'] = textures[BLOCK.DIRT + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#6b4e2e', 30, s);
  });

  // Stone
  textures[BLOCK.STONE + '_top'] = textures[BLOCK.STONE + '_side'] = textures[BLOCK.STONE + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#888888', 30, s);
  });

  // Wood (log)
  textures[BLOCK.WOOD + '_top'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#b8945a', 20, s);
    // rings
    ctx.strokeStyle = '#8b6a3e';
    for (let r = 2; r < s / 2; r += 2) {
      ctx.beginPath();
      ctx.arc(s / 2, s / 2, r, 0, Math.PI * 2);
      ctx.stroke();
    }
  });
  textures[BLOCK.WOOD + '_side'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#6e5230', 25, s);
    // vertical bark lines
    ctx.strokeStyle = '#5a4220';
    for (let x = 2; x < s; x += 4) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + (Math.random() - 0.5) * 2, s);
      ctx.stroke();
    }
  });
  textures[BLOCK.WOOD + '_bottom'] = textures[BLOCK.WOOD + '_top'];

  // Leaves
  textures[BLOCK.LEAVES + '_top'] = textures[BLOCK.LEAVES + '_side'] = textures[BLOCK.LEAVES + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#3a7d2a', 50, s);
    // some darker spots
    for (let i = 0; i < 20; i++) {
      ctx.fillStyle = `rgba(20,60,15,${Math.random() * 0.5})`;
      ctx.fillRect(Math.floor(Math.random() * s), Math.floor(Math.random() * s), 1, 1);
    }
  });

  // Sand
  textures[BLOCK.SAND + '_top'] = textures[BLOCK.SAND + '_side'] = textures[BLOCK.SAND + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#e6d9a0', 20, s);
  });

  // Water
  textures[BLOCK.WATER + '_top'] = textures[BLOCK.WATER + '_side'] = textures[BLOCK.WATER + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#3a6ec5', 15, s);
  });

  // Bedrock
  textures[BLOCK.BEDROCK + '_top'] = textures[BLOCK.BEDROCK + '_side'] = textures[BLOCK.BEDROCK + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#333333', 50, s);
    for (let i = 0; i < 10; i++) {
      ctx.fillStyle = `rgb(${20 + Math.random() * 40}, ${20 + Math.random() * 40}, ${20 + Math.random() * 40})`;
      ctx.fillRect(Math.floor(Math.random() * s), Math.floor(Math.random() * s), 2, 2);
    }
  });

  // Planks
  textures[BLOCK.PLANKS + '_top'] = textures[BLOCK.PLANKS + '_side'] = textures[BLOCK.PLANKS + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#b8945a', 15, s);
    // horizontal plank lines
    ctx.strokeStyle = '#8b6a3e';
    for (let y = 4; y < s; y += 4) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(s, y);
      ctx.stroke();
    }
  });

  // Cobblestone
  textures[BLOCK.COBBLESTONE + '_top'] = textures[BLOCK.COBBLESTONE + '_side'] = textures[BLOCK.COBBLESTONE + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#777777', 40, s);
    // cobble pattern
    ctx.strokeStyle = '#555555';
    ctx.lineWidth = 1;
    const stones = [[2,2,5,4],[9,2,5,4],[2,7,4,5],[7,8,6,5],[3,12,5,3],[9,12,5,3]];
    for (const [x,y,w,h] of stones) {
      ctx.strokeRect(x, y, w, h);
    }
  });

  // Glass
  textures[BLOCK.GLASS + '_top'] = textures[BLOCK.GLASS + '_side'] = textures[BLOCK.GLASS + '_bottom'] = makeTexture((ctx, s) => {
    ctx.fillStyle = 'rgba(170,204,255,0.15)';
    ctx.fillRect(0, 0, s, s);
    ctx.strokeStyle = 'rgba(200,230,255,0.6)';
    ctx.strokeRect(0, 0, s, s);
    // a little shine
    ctx.strokeStyle = 'rgba(255,255,255,0.3)';
    ctx.beginPath();
    ctx.moveTo(2, 2); ctx.lineTo(6, 2);
    ctx.moveTo(2, 2); ctx.lineTo(2, 6);
    ctx.stroke();
  });

  // Brick
  textures[BLOCK.BRICK + '_top'] = textures[BLOCK.BRICK + '_side'] = textures[BLOCK.BRICK + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#9c4a3a', 20, s);
    ctx.strokeStyle = '#5a2a20';
    ctx.lineWidth = 1;
    // brick mortar lines
    for (let y = 0; y < s; y += 4) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(s, y); ctx.stroke();
    }
    for (let y = 0; y < s; y += 4) {
      const offset = (y / 4) % 2 === 0 ? 0 : 4;
      for (let x = offset; x < s; x += 8) {
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 4); ctx.stroke();
      }
    }
  });

  // Glowstone
  textures[BLOCK.GLOWSTONE + '_top'] = textures[BLOCK.GLOWSTONE + '_side'] = textures[BLOCK.GLOWSTONE + '_bottom'] = makeTexture((ctx, s) => {
    texNoise(ctx, '#ffd44a', 30, s);
    // glowing spots
    for (let i = 0; i < 15; i++) {
      ctx.fillStyle = `rgba(255,255,200,${Math.random() * 0.6})`;
      ctx.fillRect(Math.floor(Math.random() * s), Math.floor(Math.random() * s), 2, 2);
    }
  });

  return textures;
}

// Build materials for each block type using the textures
export function createMaterials(textures) {
  const materials = {};

  function matFor(texture, transparent = false, opacity = 1, emissive = 0x000000, emissiveIntensity = 0) {
    return new THREE.MeshLambertMaterial({
      map: texture,
      transparent: transparent,
      opacity: opacity,
      emissive: emissive,
      emissiveIntensity: emissiveIntensity,
      side: THREE.FrontSide,
    });
  }

  for (const id of Object.keys(BLOCKS)) {
    const blockId = parseInt(id);
    if (blockId === BLOCK.AIR) continue;

    const block = BLOCKS[blockId];
    const topTex = textures[blockId + '_top'];
    const sideTex = textures[blockId + '_side'];
    const bottomTex = textures[blockId + '_bottom'];

    const isTransparent = block.transparent;
    const opacity = blockId === BLOCK.WATER ? 0.7 : (isTransparent ? 0.8 : 1);

    if (blockId === BLOCK.GLOWSTONE) {
      materials[blockId] = {
        top: matFor(topTex, isTransparent, opacity, 0xffd44a, 0.6),
        bottom: matFor(bottomTex, isTransparent, opacity, 0xffd44a, 0.6),
        side: matFor(sideTex, isTransparent, opacity, 0xffd44a, 0.6),
      };
    } else {
      materials[blockId] = {
        top: matFor(topTex, isTransparent, opacity),
        bottom: matFor(bottomTex, isTransparent, opacity),
        side: matFor(sideTex, isTransparent, opacity),
      };
    }
  }

  return materials;
}
