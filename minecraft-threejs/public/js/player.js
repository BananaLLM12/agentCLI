import * as THREE from 'three';
import { BLOCK, BLOCKS } from './blocks.js';
import { CHUNK_SIZE, CHUNK_HEIGHT } from './world.js';

export class Player {
  constructor(camera, world) {
    this.camera = camera;
    this.world = world;

    // Position and velocity
    this.position = new THREE.Vector3(0, 50, 0);
    this.velocity = new THREE.Vector3(0, 0, 0);

    // Player dimensions (slightly smaller than a block)
    this.width = 0.6;
    this.height = 1.8;
    this.eyeHeight = 1.62;

    // Movement
    this.speed = 4.3;
    this.sprintSpeed = 6.5;
    this.flySpeed = 10;
    this.jumpSpeed = 8.5;
    this.gravity = 28;
    this.flyMode = false;
    this.onGround = false;

    // Look direction
    this.yaw = 0;
    this.pitch = 0;

    // Input
    this.keys = {};
    this.mouseSensitivity = 0.002;

    // Raycasting for block interaction
    this.raycaster = new THREE.Raycaster();
    this.raycaster.far = 6;
    this.targetBlock = null;
    this.placeBlock = null;
  }

  setKey(code, pressed) {
    this.keys[code] = pressed;
  }

  onMouseMove(dx, dy) {
    this.yaw -= dx * this.mouseSensitivity;
    this.pitch -= dy * this.mouseSensitivity;
    this.pitch = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, this.pitch));
  }

  toggleFly() {
    this.flyMode = !this.flyMode;
    this.velocity.set(0, 0, 0);
    return this.flyMode;
  }

  getForwardVector() {
    return new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
  }

  getRightVector() {
    return new THREE.Vector3(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
  }

  getLookVector() {
    return new THREE.Vector3(
      -Math.sin(this.yaw) * Math.cos(this.pitch),
      Math.sin(this.pitch),
      -Math.cos(this.yaw) * Math.cos(this.pitch)
    );
  }

  // Check collision at a given position
  collides(pos) {
    const minX = Math.floor(pos.x - this.width / 2);
    const maxX = Math.floor(pos.x + this.width / 2);
    const minY = Math.floor(pos.y);
    const maxY = Math.floor(pos.y + this.height);
    const minZ = Math.floor(pos.z - this.width / 2);
    const maxZ = Math.floor(pos.z + this.width / 2);

    for (let x = minX; x <= maxX; x++) {
      for (let y = minY; y <= maxY; y++) {
        for (let z = minZ; z <= maxZ; z++) {
          const blockId = this.world.getBlockWorld(x, y, z);
          if (blockId !== BLOCK.AIR) {
            const block = BLOCKS[blockId];
            if (block && block.solid) return true;
          }
        }
      }
    }
    return false;
  }

  update(dt) {
    // Calculate movement direction
    const forward = this.getForwardVector();
    const right = this.getRightVector();

    let moveX = 0, moveZ = 0;
    if (this.keys['KeyW']) { moveX += forward.x; moveZ += forward.z; }
    if (this.keys['KeyS']) { moveX -= forward.x; moveZ -= forward.z; }
    if (this.keys['KeyA']) { moveX -= right.x; moveZ -= right.z; }
    if (this.keys['KeyD']) { moveX += right.x; moveZ += right.z; }

    // Normalize horizontal movement
    const moveLen = Math.sqrt(moveX * moveX + moveZ * moveZ);
    if (moveLen > 0) {
      moveX /= moveLen;
      moveZ /= moveLen;
    }

    const sprinting = this.keys['ShiftLeft'] || this.keys['ShiftRight'];
    const currentSpeed = this.flyMode ? this.flySpeed : (sprinting ? this.sprintSpeed : this.speed);

    if (this.flyMode) {
      // Fly mode - direct velocity
      this.velocity.x = moveX * currentSpeed;
      this.velocity.z = moveZ * currentSpeed;
      if (this.keys['Space']) this.velocity.y = currentSpeed;
      else if (this.keys['ShiftLeft']) this.velocity.y = -currentSpeed;
      else this.velocity.y = 0;
    } else {
      // Walking mode
      this.velocity.x = moveX * currentSpeed;
      this.velocity.z = moveZ * currentSpeed;

      // Gravity
      this.velocity.y -= this.gravity * dt;

      // Jump
      if (this.keys['Space'] && this.onGround) {
        this.velocity.y = this.jumpSpeed;
        this.onGround = false;
      }
    }

    // Apply movement with collision detection (per-axis)
    const newPos = this.position.clone();

    // X axis
    newPos.x += this.velocity.x * dt;
    if (this.collides(newPos)) {
      newPos.x = this.position.x;
      this.velocity.x = 0;
    }

    // Z axis
    newPos.z += this.velocity.z * dt;
    if (this.collides(newPos.clone().set(newPos.x, newPos.y, newPos.z))) {
      newPos.z = this.position.z;
      this.velocity.z = 0;
    }

    // Y axis
    newPos.y += this.velocity.y * dt;
    if (this.collides(newPos)) {
      if (this.velocity.y < 0) {
        this.onGround = true;
      }
      newPos.y = this.position.y;
      this.velocity.y = 0;
    } else {
      this.onGround = false;
    }

    this.position.copy(newPos);

    // Prevent falling through the void
    if (this.position.y < -10) {
      this.position.set(0, 50, 0);
      this.velocity.set(0, 0, 0);
    }

    // Update camera
    this.camera.position.set(
      this.position.x,
      this.position.y + this.eyeHeight,
      this.position.z
    );
    this.camera.rotation.order = 'YXZ';
    this.camera.rotation.y = this.yaw;
    this.camera.rotation.x = this.pitch;

    // Update raycast target
    this.updateRaycast();
  }

  updateRaycast() {
    const lookVec = this.getLookVector();
    const origin = new THREE.Vector3(
      this.position.x,
      this.position.y + this.eyeHeight,
      this.position.z
    );

    // DDA voxel raycast
    const result = this.raycastVoxels(origin, lookVec, 6);
    this.targetBlock = result ? result.block : null;
    this.placeBlock = result ? result.place : null;
  }

  raycastVoxels(origin, direction, maxDist) {
    let x = Math.floor(origin.x);
    let y = Math.floor(origin.y);
    let z = Math.floor(origin.z);

    const stepX = direction.x > 0 ? 1 : -1;
    const stepY = direction.y > 0 ? 1 : -1;
    const stepZ = direction.z > 0 ? 1 : -1;

    const tDeltaX = Math.abs(1 / direction.x);
    const tDeltaY = Math.abs(1 / direction.y);
    const tDeltaZ = Math.abs(1 / direction.z);

    let tMaxX = ((stepX > 0 ? Math.floor(origin.x) + 1 - origin.x : origin.x - Math.floor(origin.x)) || 1) * tDeltaX;
    let tMaxY = ((stepY > 0 ? Math.floor(origin.y) + 1 - origin.y : origin.y - Math.floor(origin.y)) || 1) * tDeltaY;
    let tMaxZ = ((stepZ > 0 ? Math.floor(origin.z) + 1 - origin.z : origin.z - Math.floor(origin.z)) || 1) * tDeltaZ;

    let face = null;
    let t = 0;

    while (t < maxDist) {
      const blockId = this.world.getBlockWorld(x, y, z);
      if (blockId !== BLOCK.AIR && BLOCKS[blockId] && BLOCKS[blockId].solid) {
        // Place position is one step back
        const placeX = x + (face ? face[0] : 0);
        const placeY = y + (face ? face[1] : 0);
        const placeZ = z + (face ? face[2] : 0);
        return {
          block: { x, y, z, blockId },
          place: { x: placeX, y: placeY, z: placeZ },
        };
      }

      if (tMaxX < tMaxY && tMaxX < tMaxZ) {
        x += stepX;
        t = tMaxX;
        tMaxX += tDeltaX;
        face = [-stepX, 0, 0];
      } else if (tMaxY < tMaxZ) {
        y += stepY;
        t = tMaxY;
        tMaxY += tDeltaY;
        face = [0, -stepY, 0];
      } else {
        z += stepZ;
        t = tMaxZ;
        tMaxZ += tDeltaZ;
        face = [0, 0, -stepZ];
      }
    }

    return null;
  }

  breakBlock() {
    if (!this.targetBlock) return null;
    const { x, y, z } = this.targetBlock;
    const blockId = this.world.getBlockWorld(x, y, z);
    if (blockId === BLOCK.BEDROCK) return null; // Can't break bedrock
    this.world.setBlock(x, y, z, BLOCK.AIR);
    return blockId;
  }

  placeBlockAt(blockId) {
    if (!this.placeBlock) return false;
    const { x, y, z } = this.placeBlock;

    // Don't place inside the player
    const playerMinX = this.position.x - this.width / 2;
    const playerMaxX = this.position.x + this.width / 2;
    const playerMinY = this.position.y;
    const playerMaxY = this.position.y + this.height;
    const playerMinZ = this.position.z - this.width / 2;
    const playerMaxZ = this.position.z + this.width / 2;

    if (x + 1 > playerMinX && x < playerMaxX &&
        y + 1 > playerMinY && y < playerMaxY &&
        z + 1 > playerMinZ && z < playerMaxZ) {
      return false;
  }

    this.world.setBlock(x, y, z, blockId);
    return true;
  }
}
