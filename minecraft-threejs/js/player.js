// player.js — first-person controller: pointer lock, AABB physics, collision.

const EYE = 1.6;          // eye height above feet
const P_W = 0.6, P_H = 1.8; // player AABB (width, full height)
const GRAV = 28, JUMP = 9.2, SPEED = 4.6, SPRINT = 7.2;
const REACH = 6;

class Player {
  constructor(camera, world, dom) {
    this.camera = camera;
    this.world = world;
    this.dom = dom;
    this.pos = new THREE.Vector3(48, 40, 48); // feet position
    this.vel = new THREE.Vector3();
    this.onGround = false;
    this.yaw = 0; this.pitch = 0;
    this.flying = false;
    this.keys = {};
    this.locked = false;

    this._bind();
  }

  _bind() {
    const dom = this.dom;
    // The start/pause overlay sits ON TOP of the canvas and swallows clicks,
    // so a click handler on the canvas alone never fires. Listen on the
    // overlay instead and request pointer lock on the canvas from there.
    const overlay = document.getElementById('overlay');
    const requestLock = () => { if (!this.locked) dom.requestPointerLock(); };
    if (overlay) overlay.addEventListener('click', requestLock);
    dom.addEventListener('click', requestLock); // fallback when overlay is hidden
    document.addEventListener('pointerlockchange', () => {
      this.locked = (document.pointerLockElement === dom);
      if (window.onLockChange) window.onLockChange(this.locked);
    });
    document.addEventListener('mousemove', (e) => {
      if (!this.locked) return;
      const sens = 0.0022;
      this.yaw   -= e.movementX * sens;
      this.pitch -= e.movementY * sens;
      const lim = Math.PI / 2 - 0.01;
      this.pitch = Math.max(-lim, Math.min(lim, this.pitch));
    });
    window.addEventListener('keydown', (e) => {
      this.keys[e.code] = true;
      if (e.code === 'KeyF') this.flying = !this.flying;
      if (e.code === 'Space') e.preventDefault();
    });
    window.addEventListener('keyup', (e) => { this.keys[e.code] = false; });
  }

  _inputDir() {
    const f = new THREE.Vector3();
    const r = new THREE.Vector3();
    f.set(Math.sin(this.yaw), 0, Math.cos(this.yaw)).multiplyScalar(-1); // forward
    r.set(Math.cos(this.yaw), 0, -Math.sin(this.yaw));                   // right
    const dir = new THREE.Vector3();
    if (this.keys['KeyW']) dir.add(f);
    if (this.keys['KeyS']) dir.sub(f);
    if (this.keys['KeyD']) dir.add(r);
    if (this.keys['KeyA']) dir.sub(r);
    if (dir.lengthSq() > 0) dir.normalize();
    return dir;
  }

  // AABB vs voxel collision resolution, axis by axis
  _collide(axis, delta) {
    // move along axis then resolve overlaps
    this.pos[axis] += delta;
    const half = P_W / 2;
    const minX = Math.floor(this.pos.x - half);
    const maxX = Math.floor(this.pos.x + half);
    const minY = Math.floor(this.pos.y);
    const maxY = Math.floor(this.pos.y + P_H);
    const minZ = Math.floor(this.pos.z - half);
    const maxZ = Math.floor(this.pos.z + half);
    for (let x = minX; x <= maxX; x++)
      for (let y = minY; y <= maxY; y++)
        for (let z = minZ; z <= maxZ; z++) {
          if (!this.world.isSolid(x, y, z)) continue;
          // overlap exists; push out along this axis
          if (axis === 'y') {
            if (delta > 0) { this.pos.y = y - P_H - 1e-4; this.vel.y = 0; }
            else { this.pos.y = y + 1 + 1e-4; this.vel.y = 0; this.onGround = true; }
            return;
          } else if (axis === 'x') {
            if (delta > 0) this.pos.x = x - half - 1e-4;
            else this.pos.x = x + 1 + half + 1e-4;
            this.vel.x = 0;
            return;
          } else { // z
            if (delta > 0) this.pos.z = z - half - 1e-4;
            else this.pos.z = z + 1 + half + 1e-4;
            this.vel.z = 0;
            return;
          }
        }
  }

  update(dt) {
    const dir = this._inputDir();
    const sprint = this.keys['ShiftLeft'] || this.keys['ShiftRight'];
    const sp = sprint ? SPRINT : SPEED;

    if (this.flying) {
      this.vel.x = dir.x * sp * 1.6;
      this.vel.z = dir.z * sp * 1.6;
      this.vel.y = 0;
      if (this.keys['Space']) this.vel.y = sp * 1.2;
      if (this.keys['ControlLeft'] || this.keys['KeyC']) this.vel.y = -sp * 1.2;
    } else {
      this.vel.x = dir.x * sp;
      this.vel.z = dir.z * sp;
      this.vel.y -= GRAV * dt;
      if (this.onGround && this.keys['Space']) { this.vel.y = JUMP; this.onGround = false; }
    }

    this.onGround = false;
    // resolve axis by axis
    this._collide('y', this.vel.y * dt);
    this._collide('x', this.vel.x * dt);
    this._collide('z', this.vel.z * dt);

    // keep inside world bounds
    const b0 = this.world.minBound + P_W / 2, b1 = this.world.maxBound - P_W / 2;
    this.pos.x = Math.max(b0, Math.min(b1, this.pos.x));
    this.pos.z = Math.max(b0, Math.min(b1, this.pos.z));
    if (this.pos.y < -10) this.respawn(); // fell into void

    // update camera
    this.camera.position.set(this.pos.x, this.pos.y + EYE, this.pos.z);
    this.camera.rotation.order = 'YXZ';
    this.camera.rotation.y = this.yaw;
    this.camera.rotation.x = this.pitch;
  }

  respawn() {
    // drop onto the column at spawn
    const x = 48, z = 48;
    let y = WORLD_CONST.HEIGHT - 1;
    while (y > 0 && !this.world.isSolid(x, y - 1, z)) y--;
    this.pos.set(x + 0.5, y + 1, z + 0.5);
    this.vel.set(0, 0, 0);
  }

  // ray from camera center; returns world hit + face normal
  targetBlock() {
    const o = this.camera.position.clone();
    const d = new THREE.Vector3(0, 0, -1).applyEuler(this.camera.rotation);
    return this.world.raycast(o, d, REACH);
  }
}

window.Player = Player;
