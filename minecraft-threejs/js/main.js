// main.js — scene, lighting, UI, render loop.

let renderer, scene, camera, world, player;
let highlight;        // wireframe box around targeted block
let selectedSlot = 0;
let lastTime = performance.now();
let frames = 0, fpsAcc = 0;

function init() {
  const canvas = document.getElementById('game');
  renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x87CEEB);
  scene.fog = new THREE.Fog(0x87CEEB, 40, 110);

  camera = new THREE.PerspectiveCamera(72, window.innerWidth / window.innerHeight, 0.1, 500);

  // lighting: hemisphere + a low sun for soft directional shading
  const hemi = new THREE.HemisphereLight(0xbfdfff, 0x6b5a3a, 0.85);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff3d0, 0.55);
  sun.position.set(60, 120, 40);
  scene.add(sun);
  const amb = new THREE.AmbientLight(0xffffff, 0.25);
  scene.add(amb);

  // build atlas texture from procedural canvas
  const atlasCanvas = Blocks.buildAtlas();
  const atlasTex = new THREE.CanvasTexture(atlasCanvas);
  atlasTex.magFilter = THREE.NearestFilter;
  atlasTex.minFilter = THREE.NearestFilter;
  atlasTex.generateMipmaps = false;
  atlasTex.wrapS = atlasTex.wrapT = THREE.ClampToEdgeWrapping;

  world = new World(scene, atlasTex);

  player = new Player(camera, world, canvas);
  window.onLockChange = (locked) => {
    const ov = document.getElementById('overlay');
    if (locked) ov.classList.add('hidden');
    else { ov.classList.remove('hidden'); document.getElementById('loading').textContent = 'Paused'; }
  };

  buildHotbar();
  bindInputs();

  // wireframe highlight
  const hg = new THREE.BoxGeometry(1.002, 1.002, 1.002);
  highlight = new THREE.LineSegments(
    new THREE.EdgesGeometry(hg),
    new THREE.LineBasicMaterial({ color: 0x000000, transparent: true, opacity: 0.5 })
  );
  highlight.visible = false;
  scene.add(highlight);

  // generate world (sync, small enough)
  const loading = document.getElementById('loading');
  setTimeout(() => {
    world.generateAll();
    player.respawn();
    loading.textContent = 'World ready — click to play!';
    document.getElementById('playbtn').style.display = 'block';
    animate();
  }, 30);
}

function buildHotbar() {
  const bar = document.getElementById('hotbar');
  bar.innerHTML = '';
  const atlasCanvas = Blocks.buildAtlas();
  Blocks.HOTBAR.forEach((id, i) => {
    const slot = document.createElement('div');
    slot.className = 'slot' + (i === 0 ? ' active' : '');
    slot.dataset.idx = i;
    const def = Blocks.BLOCKS[id];
    // mini canvas showing the block's side tile
    const mini = document.createElement('canvas');
    mini.width = mini.height = 16;
    const mctx = mini.getContext('2d');
    mctx.imageSmoothingEnabled = false;
    const tile = def.faces.side;
    const cols = Blocks.ATLAS_COLS;
    const sx = (tile % cols) * 16, sy = Math.floor(tile / cols) * 16;
    mctx.drawImage(atlasCanvas, sx, sy, 16, 16, 0, 0, 16, 16);
    const num = document.createElement('div');
    num.className = 'num'; num.textContent = (i + 1);
    slot.appendChild(mini); slot.appendChild(num);
    slot.title = def.name;
    bar.appendChild(slot);
  });
}

function updateHotbarUI() {
  document.querySelectorAll('.slot').forEach((s, i) => {
    s.classList.toggle('active', i === selectedSlot);
  });
  const id = Blocks.HOTBAR[selectedSlot];
  document.getElementById('selblock').textContent = Blocks.BLOCKS[id].name;
}

function bindInputs() {
  // number keys
  window.addEventListener('keydown', (e) => {
    if (e.code.startsWith('Digit')) {
      const n = parseInt(e.code.slice(5), 10) - 1;
      if (n >= 0 && n < Blocks.HOTBAR.length) { selectedSlot = n; updateHotbarUI(); }
    }
  });
  // scroll wheel
  window.addEventListener('wheel', (e) => {
    if (!player.locked) return;
    const n = Blocks.HOTBAR.length;
    if (e.deltaY > 0) selectedSlot = (selectedSlot + 1) % n;
    else selectedSlot = (selectedSlot - 1 + n) % n;
    updateHotbarUI();
  });
  // mouse buttons: left break, right place
  const canvas = document.getElementById('game');
  canvas.addEventListener('mousedown', (e) => {
    if (!player.locked) return;
    const hit = player.targetBlock();
    if (!hit) return;
    if (e.button === 0) {
      // break — don't allow bedrock
      const id = world.getBlock(hit.x, hit.y, hit.z);
      if (id === 13) return;
      world.setBlock(hit.x, hit.y, hit.z, 0);
      world.remeshDirty();
    } else if (e.button === 2) {
      // place on the adjacent face
      const px = hit.x + hit.nx, py = hit.y + hit.ny, pz = hit.z + hit.nz;
      if (py < 0 || py >= WORLD_CONST.HEIGHT) return;
      if (world.getBlock(px, py, pz) !== 0) return;
      // don't place inside the player
      const pmin = new THREE.Vector3(player.pos.x - 0.3, player.pos.y, player.pos.z - 0.3);
      const pmax = new THREE.Vector3(player.pos.x + 0.3, player.pos.y + 1.8, player.pos.z + 0.3);
      if (px + 1 > pmin.x && px < pmax.x && py + 1 > pmin.y && py < pmax.y && pz + 1 > pmin.z && pz < pmax.z) return;
      world.setBlock(px, py, pz, Blocks.HOTBAR[selectedSlot]);
      world.remeshDirty();
    }
  });
  canvas.addEventListener('contextmenu', (e) => e.preventDefault());

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });
}

function animate() {
  requestAnimationFrame(animate);
  const now = performance.now();
  let dt = (now - lastTime) / 1000;
  lastTime = now;
  if (dt > 0.1) dt = 0.1; // clamp on tab refocus

  if (player.locked) player.update(dt);

  // update highlight
  const hit = player.targetBlock();
  if (hit) {
    highlight.visible = true;
    highlight.position.set(hit.x + 0.5, hit.y + 0.5, hit.z + 0.5);
  } else {
    highlight.visible = false;
  }

  renderer.render(scene, camera);

  // HUD
  frames++; fpsAcc += dt;
  if (fpsAcc >= 0.5) {
    document.getElementById('fps').textContent = Math.round(frames / fpsAcc);
    frames = 0; fpsAcc = 0;
  }
  const p = player.pos;
  document.getElementById('pos').textContent =
    `${p.x.toFixed(1)}, ${p.y.toFixed(1)}, ${p.z.toFixed(1)}`;
}

window.addEventListener('load', init);
