import * as THREE from 'three';
import { BLOCK, BLOCK_NAMES, BLOCKS, createBlockTextures, createMaterials } from './blocks.js';
import { World, CHUNK_SIZE, CHUNK_HEIGHT, SEA_LEVEL } from './world.js';
import { Player } from './player.js';

class Game {
  constructor() {
    this.canvas = document.getElementById('game-canvas');
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x87ceeb);
    this.scene.fog = new THREE.Fog(0x87ceeb, CHUNK_SIZE * 4, CHUNK_SIZE * 8);

    // Camera
    this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    // Lighting
    this.setupLighting();

    // Block textures and materials
    this.textures = createBlockTextures();
    this.materials = createMaterials(this.textures);

    // Build material array and index map for chunk meshing
    this.buildMaterialArray();

    // World
    this.world = new World(this.scene, this.materials, this.blockMaterialIndex, this.materialArray, Math.floor(Math.random() * 99999));

    // Player
    this.player = new Player(this.camera, this.world);

    // Find spawn point
    this.findSpawn();

    // Hotbar
    this.hotbar = [
      BLOCK.GRASS, BLOCK.DIRT, BLOCK.STONE, BLOCK.WOOD,
      BLOCK.LEAVES, BLOCK.SAND, BLOCK.PLANKS, BLOCK.COBBLESTONE, BLOCK.GLASS
    ];
    this.selectedSlot = 0;

    // Block highlight (wireframe)
    this.highlightMesh = this.createHighlightMesh();
    this.scene.add(this.highlightMesh);

    // Block break particles
    this.particles = [];

    // Game state
    this.paused = true;
    this.locked = false;
    this.fps = 0;
    this.frameCount = 0;
    this.fpsTime = 0;
    this.lastTime = performance.now();

    // Setup everything
    this.setupHotbar();
    this.setupInput();
    this.setupResize();

    // Start animation loop
    this.animate();

    // Show start screen
    document.getElementById('start-screen').classList.remove('hidden');
  }

  setupLighting() {
    // Ambient light
    const ambient = new THREE.AmbientLight(0xffffff, 0.6);
    this.scene.add(ambient);

    // Directional (sun)
    const sun = new THREE.DirectionalLight(0xffffff, 0.8);
    sun.position.set(50, 100, 30);
    this.scene.add(sun);

    // Hemisphere light for nice sky/ground tint
    const hemi = new THREE.HemisphereLight(0x87ceeb, 0x3a5a2a, 0.4);
    this.scene.add(hemi);
  }

  buildMaterialArray() {
    this.materialArray = [];
    this.blockMaterialIndex = {};

    let idx = 0;
    for (const id of Object.keys(BLOCKS)) {
      const blockId = parseInt(id);
      if (blockId === BLOCK.AIR) continue;
      if (!this.materials[blockId]) continue;

      const mats = this.materials[blockId]; // {top, bottom, side}

      this.blockMaterialIndex[`${blockId}_top`] = idx;
      this.materialArray.push(mats.top);
      idx++;

      this.blockMaterialIndex[`${blockId}_bottom`] = idx;
      this.materialArray.push(mats.bottom);
      idx++;

      this.blockMaterialIndex[`${blockId}_side`] = idx;
      this.materialArray.push(mats.side);
      idx++;
    }
  }

  findSpawn() {
    // Generate initial chunks around spawn
    for (let cx = -2; cx <= 2; cx++) {
      for (let cz = -2; cz <= 2; cz++) {
        this.world.generateChunk(cx, cz);
      }
    }

    // Find surface height at 0,0
    let spawnY = CHUNK_HEIGHT;
    for (let y = CHUNK_HEIGHT - 1; y >= 0; y--) {
      const block = this.world.getBlockWorld(0, y, 0);
      if (block !== BLOCK.AIR && block !== BLOCK.WATER) {
        spawnY = y + 1;
        break;
      }
    }
    this.player.position.set(0.5, spawnY + 2, 0.5);
  }

  createHighlightMesh() {
    const geo = new THREE.BoxGeometry(1.001, 1.001, 1.001);
    const edges = new THREE.EdgesGeometry(geo);
    const mat = new THREE.LineBasicMaterial({ color: 0x000000, linewidth: 2, transparent: true, opacity: 0.5 });
    const mesh = new THREE.LineSegments(edges, mat);
    mesh.visible = false;
    return mesh;
  }

  setupHotbar() {
    const slots = document.querySelectorAll('.slot');
    slots.forEach((slot, i) => {
      // Draw block icon
      const iconCanvas = document.createElement('canvas');
      iconCanvas.width = 36;
      iconCanvas.height = 36;
      const ctx = iconCanvas.getContext('2d');

      const blockId = this.hotbar[i];
      const block = BLOCKS[blockId];
      if (block) {
        // Simple isometric-ish block icon
        const color = '#' + block.topColor.toString(16).padStart(6, '0');
        ctx.fillStyle = color;
        ctx.fillRect(4, 4, 28, 28);
        // Darker shade for side
        const sideColor = '#' + block.sideColor.toString(16).padStart(6, '0');
        ctx.fillStyle = sideColor;
        ctx.fillRect(4, 20, 28, 12);
        // Border
        ctx.strokeStyle = 'rgba(0,0,0,0.3)';
        ctx.strokeRect(4, 4, 28, 28);
      }

      const iconContainer = document.getElementById(`slot-${i}`);
      iconContainer.appendChild(iconCanvas);

      slot.addEventListener('click', () => {
        this.selectSlot(i);
      });
    });
    this.updateHotbarSelection();
  }

  selectSlot(index) {
    this.selectedSlot = index;
    this.updateHotbarSelection();
  }

  updateHotbarSelection() {
    const slots = document.querySelectorAll('.slot');
    slots.forEach((slot, i) => {
      slot.classList.toggle('active', i === this.selectedSlot);
    });
  }

  setupInput() {
    // Keyboard
    document.addEventListener('keydown', (e) => {
      this.player.setKey(e.code, true);

      // Number keys for hotbar
      if (e.code.startsWith('Digit')) {
        const num = parseInt(e.code.replace('Digit', ''));
        if (num >= 1 && num <= 9) {
          this.selectSlot(num - 1);
        }
      }

      // Toggle fly
      if (e.code === 'KeyF') {
        const flying = this.player.toggleFly();
        document.getElementById('mode').textContent = `Mode: ${flying ? 'Fly' : 'Survival'}`;
      }

      // Regenerate world
      if (e.code === 'KeyR') {
        this.regenerateWorld();
      }

      // ESC to pause
      if (e.code === 'Escape') {
        this.pause();
      }
    });

    document.addEventListener('keyup', (e) => {
      this.player.setKey(e.code, false);
    });

    // Mouse
    this.canvas.addEventListener('click', () => {
      if (!this.locked) {
        this.lockMouse();
      }
    });

    document.addEventListener('pointerlockchange', () => {
      this.locked = document.pointerLockElement === this.canvas;
      if (!this.locked && !this.paused) {
        this.pause();
      }
    });

    document.addEventListener('mousemove', (e) => {
      if (this.locked) {
        this.player.onMouseMove(e.movementX, e.movementY);
      }
    });

    // Mouse buttons for break/place
    document.addEventListener('mousedown', (e) => {
      if (!this.locked) return;
      if (e.button === 0) {
        // Left click - break
        const broken = this.player.breakBlock();
        if (broken !== null) {
          this.spawnBreakParticles(this.player.targetBlock);
        }
      } else if (e.button === 2) {
        // Right click - place
        const blockId = this.hotbar[this.selectedSlot];
        this.player.placeBlockAt(blockId);
      }
    });

    // Prevent context menu
    document.addEventListener('contextmenu', (e) => e.preventDefault());

    // Mouse wheel to cycle hotbar
    document.addEventListener('wheel', (e) => {
      if (!this.locked) return;
      if (e.deltaY > 0) {
        this.selectSlot((this.selectedSlot + 1) % 9);
      } else {
        this.selectSlot((this.selectedSlot - 1 + 9) % 9);
      }
    });

    // Play button
    document.getElementById('play-button').addEventListener('click', () => {
      this.start();
    });
  }

  lockMouse() {
    this.canvas.requestPointerLock();
  }

  start() {
    document.getElementById('start-screen').classList.add('hidden');
    document.getElementById('loading-screen').style.display = 'none';
    this.paused = false;
    this.lockMouse();
  }

  pause() {
    this.paused = true;
    document.getElementById('start-screen').classList.remove('hidden');
  }

  regenerateWorld() {
    // Dispose all chunks
    for (const [key, chunk] of this.world.chunks) {
      chunk.dispose();
    }
    this.world.chunks.clear();

    // New seed
    this.world.noise = new (this.world.noise.constructor)(Math.floor(Math.random() * 99999));

    // Regenerate spawn area
    for (let cx = -2; cx <= 2; cx++) {
      for (let cz = -2; cz <= 2; cz++) {
        this.world.generateChunk(cx, cz);
      }
    }

    this.findSpawn();
    this.player.velocity.set(0, 0, 0);
  }

  spawnBreakParticles(block) {
    if (!block) return;
    const blockData = BLOCKS[block.blockId];
    if (!blockData) return;

    const color = blockData.topColor;
    const geo = new THREE.BoxGeometry(0.1, 0.1, 0.1);
    const mat = new THREE.MeshLambertMaterial({ color: color });
    const count = 8;

    for (let i = 0; i < count; i++) {
      const particle = new THREE.Mesh(geo, mat.clone());
      particle.position.set(
        block.x + 0.5 + (Math.random() - 0.5) * 0.5,
        block.y + 0.5 + (Math.random() - 0.5) * 0.5,
        block.z + 0.5 + (Math.random() - 0.5) * 0.5
      );
      particle.userData = {
        velocity: new THREE.Vector3(
          (Math.random() - 0.5) * 4,
          Math.random() * 4,
          (Math.random() - 0.5) * 4
        ),
        life: 0.8,
      };
      this.scene.add(particle);
      this.particles.push(particle);
    }
  }

  updateParticles(dt) {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.userData.life -= dt;
      if (p.userData.life <= 0) {
        this.scene.remove(p);
        p.geometry.dispose();
        p.material.dispose();
        this.particles.splice(i, 1);
        continue;
      }
      p.userData.velocity.y -= 15 * dt;
      p.position.x += p.userData.velocity.x * dt;
      p.position.y += p.userData.velocity.y * dt;
      p.position.z += p.userData.velocity.z * dt;
      p.material.opacity = p.userData.life;
      p.material.transparent = true;
    }
  }

  updateHighlight() {
    if (this.player.targetBlock) {
      const b = this.player.targetBlock;
      this.highlightMesh.position.set(b.x + 0.5, b.y + 0.5, b.z + 0.5);
      this.highlightMesh.visible = true;
    } else {
      this.highlightMesh.visible = false;
    }
  }

  setupResize() {
    window.addEventListener('resize', () => {
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(window.innerWidth, window.innerHeight);
    });
  }

  updateDebugInfo() {
    document.getElementById('fps').textContent = `FPS: ${this.fps}`;
    const p = this.player.position;
    document.getElementById('position').textContent = `Pos: ${p.x.toFixed(1)}, ${p.y.toFixed(1)}, ${p.z.toFixed(1)}`;
    document.getElementById('chunks').textContent = `Chunks: ${this.world.getLoadedChunkCount()}`;
    document.getElementById('block-count').textContent = `Blocks: ${this.world.chunks.size * CHUNK_SIZE * CHUNK_SIZE * CHUNK_HEIGHT}`;
  }

  animate() {
    requestAnimationFrame(() => this.animate());

    const now = performance.now();
    const dt = Math.min((now - this.lastTime) / 1000, 0.1);
    this.lastTime = now;

    // FPS counter
    this.frameCount++;
    this.fpsTime += dt;
    if (this.fpsTime >= 0.5) {
      this.fps = Math.round(this.frameCount / this.fpsTime);
      this.frameCount = 0;
      this.fpsTime = 0;
    }

    if (!this.paused) {
      this.player.update(dt);
      this.world.update(this.player.position.x, this.player.position.z);
      this.updateHighlight();
      this.updateParticles(dt);
    }

    this.updateDebugInfo();
    this.renderer.render(this.scene, this.camera);
  }
}

// Start the game when page loads
window.addEventListener('DOMContentLoaded', () => {
  new Game();
});
