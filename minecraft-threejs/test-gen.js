// Headless test: stub the browser globals, load the game scripts in order,
// and run world.generateAll() to catch any runtime error.

// ---- browser/Three.js stubs ----
const stubVec = { set(x,y,z){this.x=x;this.y=y;this.z=z;return this;}, clone(){return Object.assign(Object.create(Object.getPrototypeOf(this)),this);}, multiplyScalar(s){this.x*=s;this.y*=s;this.z*=s;return this;}, add(v){this.x+=v.x;this.y+=v.y;this.z+=v.z;return this;}, sub(v){this.x-=v.x;this.y-=v.y;this.z-=v.z;return this;}, lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z;}, normalize(){const l=Math.sqrt(this.lengthSq());if(l>0){this.x/=l;this.y/=l;this.z/=l;}return this;}, applyEuler(){return this;} };
function V3(x=0,y=0,z=0){const v=Object.create(stubVec);v.x=x;v.y=y;v.z=z;return v;}

global.THREE = {
  Vector3: function(x,y,z){return V3(x,y,z);},
  Color: function(){},
  Fog: function(){},
  HemisphereLight: function(){}, DirectionalLight: function(){}, AmbientLight: function(){},
  PerspectiveCamera: function(){this.position=V3();this.rotation={order:'YXZ',x:0,y:0,z:0};this.aspect=1;this.updateProjectionMatrix=()=>{};},
  WebGLRenderer: function(){this.setPixelRatio=()=>{};this.setSize=()=>{};this.render=()=>{};},
  Scene: function(){this.add=()=>{};this.background=null;this.fog=null;},
  CanvasTexture: function(){this.magFilter=0;this.minFilter=0;this.generateMipmaps=false;this.wrapS=0;this.wrapT=0;},
  NearestFilter: 0, ClampToEdgeWrapping: 0,
  MeshLambertMaterial: function(){},
  BufferGeometry: function(){this.setAttribute=()=>{};this.setIndex=()=>{};this.dispose=()=>{};},
  Float32BufferAttribute: function(){},
  BoxGeometry: function(){}, EdgesGeometry: function(){}, LineSegments: function(){this.visible=false;this.position=V3();}, LineBasicMaterial: function(){},
  Mesh: function(){this.frustumCulled=true;},
  FrontSide: 0, DoubleSide: 0,
};
global.document = {
  getElementById: () => ({ style:{}, classList:{add(){},remove(){},toggle(){}}, textContent:'', appendChild(){}, innerHTML:'', dataset:{}, title:'', getContext: () => ({ imageSmoothingEnabled:false, fillRect(){}, fillStyle:'', strokeRect(){}, strokeStyle:'', beginPath(){}, arc(){}, stroke(){}, moveTo(){}, lineTo(){}, clearRect(){} }), width:0, height:0, addEventListener(){}, requestPointerLock(){} }),
  createElement: () => ({ width:16, height:16, getContext: () => ({ imageSmoothingEnabled:false, fillRect(){}, fillStyle:'', strokeRect(){}, strokeStyle:'', beginPath(){}, arc(){}, stroke(){}, moveTo(){}, lineTo(){}, clearRect(){} }), className:'', dataset:{}, appendChild(){}, title:'' }),
  addEventListener(){}, pointerLockElement: null,
};
// In a browser, `window` IS the global object, so `window.Blocks = X`
// makes bare `Blocks` resolve. Mirror that: point window at the global.
global.window = global;
global.innerWidth = 800; global.innerHeight = 600; global.devicePixelRatio = 1;
global.addEventListener = () => {};
global.WORLD_CONST = null; global.Blocks = null; global.World = null; global.Player = null; global.Noise = null;
global.performance = { now: () => Date.now() };
global.requestAnimationFrame = () => {};
global.setTimeout = (fn,ms)=>{return 0;};

// ---- load scripts in order ----
const fs = require('fs');
const vm = require('vm');
const ctx = vm.createContext(global);
for (const f of ['js/noise.js','js/blocks.js','js/world.js','js/player.js','js/main.js']) {
  vm.runInContext(fs.readFileSync(f,'utf8'), ctx, { filename: f });
}

// ---- run the generation path ----
console.log('Blocks:', Object.keys(window.Blocks).join(','));
console.log('World:', !!window.World, 'Player:', !!window.Player, 'Noise:', !!window.Noise);

try {
  const scene = new THREE.Scene();
  const tex = new THREE.CanvasTexture({});
  const world = new window.World(scene, tex);
  console.log('World constructed. chunks map size before gen:', world.chunks.size);
  world.generateAll();
  console.log('generateAll OK. chunks:', world.chunks.size);
  let totalBlocks = 0;
  for (const c of world.chunks.values()) {
    for (let i=0;i<c.blocks.length;i++) if (c.blocks[i]!==0) totalBlocks++;
  }
  console.log('Total non-air blocks:', totalBlocks);
  // test a few block lookups
  console.log('block(48,?,48) column heights:');
  for (let y=39;y>=0;y--){ const b=world.getBlock(48,y,48); if(b){ console.log('  top solid at y='+y+' id='+b+' ('+window.Blocks.BLOCKS[b].name+')'); break; } }
  // test raycast
  const o = V3(48.5, 30, 48.5); const d = V3(0,-1,0);
  const hit = world.raycast(o, d, 50);
  console.log('raycast down from y=30:', JSON.stringify(hit));
  console.log('SUCCESS');
} catch (e) {
  console.error('ERROR during generation:', e.message);
  console.error(e.stack);
  process.exit(1);
}
