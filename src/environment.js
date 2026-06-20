import * as THREE from 'three';
import { Reflector } from 'three/addons/objects/Reflector.js';

/**
 * A ring of small ice shards orbiting the hero crystal. Returned as a Group so
 * the caller can rotate it as one object in the render loop.
 */
export function createOrbitRing({ count = 26, radius = 4.2 } = {}) {
  const group = new THREE.Group();
  const geo = new THREE.OctahedronGeometry(0.16, 0);
  const mat = new THREE.MeshStandardMaterial({
    color: 0x9fd8ff,
    emissive: 0x1a3a5a,
    metalness: 0.1,
    roughness: 0.25,
    flatShading: true
  });

  for (let i = 0; i < count; i++) {
    const a = (i / count) * Math.PI * 2;
    const shard = new THREE.Mesh(geo, mat);
    const r = radius + (Math.random() - 0.5) * 0.8;
    shard.position.set(Math.cos(a) * r, (Math.random() - 0.5) * 1.4, Math.sin(a) * r);
    shard.rotation.set(Math.random() * Math.PI, Math.random() * Math.PI, 0);
    const s = 0.6 + Math.random() * 0.9;
    shard.scale.setScalar(s);
    shard.userData.spin = 0.2 + Math.random() * 0.6;
    group.add(shard);
  }
  return group;
}

/**
 * A reflective "frozen lake" plane sitting below the crystal. Uses Three's
 * Reflector so the crystal and shards mirror onto the ground.
 */
export function createFrozenGround({ size = 40 } = {}) {
  const geo = new THREE.PlaneGeometry(size, size);
  const reflector = new Reflector(geo, {
    color: 0x0a141f,
    textureWidth: 1024,
    textureHeight: 1024,
    clipBias: 0.003
  });
  reflector.rotation.x = -Math.PI / 2;
  reflector.position.y = -3.2;
  return reflector;
}
