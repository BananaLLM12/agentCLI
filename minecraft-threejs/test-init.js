// Stricter headless harness: stub Three.js enough to actually BUILD meshes,
// run init() and one animate() frame, catching the real runtime error.

function V3(x=0,y=0,z=0){const v={x,y,z};v.set=function(a,b,c){this.x=a;this.y=b;this.z=c;return this;};v.clone=function(){return V3(this.x,this.y,this.z);};v.multiplyScalar=function(s){this.x*=s;this.y*=s;this.z*=s;return this;};v.add=function(o){this.x+=o.x;this.y+=o.y;this.z+=o.z;return this;};v.sub=function(o){this.x-=o.x;this.y-=o.y;this.z-=o.z;return this;};v.lengthSq=function(){return this.x*this.x+this.y*this.y+this.z*this.z;};v.normalize=function(){const l=Math.sqrt(this.lengthSq());if(l>0){this.x/=l;this.y/=l;this.z/=l;}return this;};v.applyEuler=function(){return this;};return v;}

class BufferGeometry{constructor(){this.attributes={};this.index=null;}setAttribute(n,a){this.attributes[n]=a;return this;}setIndex(i){this.index=Array.isArray(i)?i:Array.from(i);return this;}dispose(){}}
class Float32BufferAttribute{constructor(arr,itemSize){this.array=arr instanceof Float32Array?arr:new Float32Array(arr);this.itemSize=itemSize;}}
class MeshLambertMaterial{constructor(o){Object.assign(this,o);}}
class Mesh{constructor(g,m){this.geometry=g;this.material=m;this.frustumCulled=true;this.position=V3();this.renderOrder=0;this.visible=true;}}
class CanvasTexture{constructor(c){this.image=c;this.magFilter=0;this.minFilter=0;this.generateMipmaps=false;this.wrapS=0;this.wrapT=0;}}
class BoxGeometry{constructor(){}}
class EdgesGeometry{constructor(){}}
class LineSegments{constructor(g,m){this.geometry=g;this.material=m;this.visible=false;this.position=V3();}}
class LineBasicMaterial{constructor(o){Object.assign(this,o);}}
class PerspectiveCamera{constructor(){this.position=V3();this.rotation={order:'YXZ',x:0,y:0,z:0};this.aspect=1;this.updateProjectionMatrix=function(){};}}
class WebGLRenderer{constructor(){this.setPixelRatio=function(){};this.setSize=function(){};this.render=function(){};}}
class Scene{constructor(){this.children=[];this.background=null;this.fog=null;}add(o){this.children.push(o);}}
class Color{constructor(){}}
class Fog{constructor(){}}
class HemisphereLight{}class DirectionalLight{constructor(){this.position=V3();}}class AmbientLight{}

global.THREE={Vector3:function(x,y,z){return V3(x,y,z);},Color,Fog,HemisphereLight,DirectionalLight,AmbientLight,PerspectiveCamera,WebGLRenderer,Scene,CanvasTexture,NearestFilter:0,ClampToEdgeWrapping:0,MeshLambertMaterial,BufferGeometry,Float32BufferAttribute,BoxGeometry,EdgesGeometry,LineSegments,LineBasicMaterial,Mesh,FrontSide:0,DoubleSide:0};

global.window=global;
global.innerWidth=800;global.innerHeight=600;global.devicePixelRatio=1;
global.addEventListener=function(){};
global.WORLD_CONST=null;global.Blocks=null;global.World=null;global.Player=null;global.Noise=null;
global.performance={now:()=>Date.now()};
let rafCount=0;
global.requestAnimationFrame=function(fn){if(rafCount++<2){try{fn();}catch(e){console.error('RAF ERROR:',e.message,e.stack);process.exit(1);}}return rafCount;};

// DOM stub with real-ish canvas
function mkCtx(){return{imageSmoothingEnabled:false,fillRect(){},fillStyle:'',strokeRect(){},strokeStyle:'',beginPath(){},arc(){},stroke(){},moveTo(){},lineTo(){},clearRect(){},drawImage(){},getImageData(){return{data:new Uint8ClampedArray(16*16*4)};},putImageData(){},createImageData(){return{data:new Uint8ClampedArray(16*16*4)};}};}
function mkEl(tag){const el={tagName:tag,width:16,height:16,style:{},classList:{add(){},remove(){},toggle(){},contains(){return false;}},textContent:'',innerHTML:'',dataset:{},title:'',appendChild(){},getContext:()=>mkCtx(),addEventListener(){},requestPointerLock(){},remove(){}};return el;}
global.document={getElementById:()=>mkEl('div'),createElement:mkEl,addEventListener(){},pointerLockElement:null,body:mkEl('body')};

const fs=require('fs'),vm=require('vm');
const ctx=vm.createContext(global);
for(const f of['js/noise.js','js/blocks.js','js/world.js','js/player.js','js/main.js'])vm.runInContext(fs.readFileSync(f,'utf8'),ctx,{filename:f});

console.log('--- running init() ---');
try{
  init();
  console.log('init() returned OK');
  // give the setTimeout(30) a tick
  setTimeout(()=>{console.log('post-timeout OK — init complete, animate started');console.log('SUCCESS');},50);
}catch(e){
  console.error('ERROR in init():',e.message);
  console.error(e.stack);
  process.exit(1);
}
