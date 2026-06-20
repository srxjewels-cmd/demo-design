import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

import { iceVertexShader, iceFragmentShader } from './shaders/ice.js';

/**
 * Builds the shared "ice" ShaderMaterial. Exposed so the loaded GLTF model
 * and the procedural fallback render identically.
 */
export function createIceMaterial() {
  return new THREE.ShaderMaterial({
    vertexShader: iceVertexShader,
    fragmentShader: iceFragmentShader,
    uniforms: {
      uTime: { value: 0 },
      uDisplace: { value: 0.35 },
      uColorCore: { value: new THREE.Color(0x0a2a4a) },
      uColorRim: { value: new THREE.Color(0x9fe0ff) }
    }
  });
}

/**
 * Procedural fallback: a cluster of intersecting icosahedra merged into a
 * single geometry so it reads like a faceted ice crystal rather than a ball.
 */
function buildProceduralCluster() {
  const shards = [];
  const shardDefs = [
    { r: 1.5, detail: 48, pos: [0, 0, 0], scale: [1, 1.25, 1] },
    { r: 0.9, detail: 24, pos: [0.9, 0.6, 0.2], scale: [0.8, 1.4, 0.8] },
    { r: 0.8, detail: 24, pos: [-0.8, -0.5, 0.4], scale: [0.7, 1.2, 0.7] },
    { r: 0.6, detail: 16, pos: [0.2, -0.9, -0.6], scale: [0.6, 1.1, 0.6] },
    { r: 0.55, detail: 16, pos: [-0.5, 0.9, -0.4], scale: [0.6, 1.3, 0.6] }
  ];

  for (const def of shardDefs) {
    const g = new THREE.IcosahedronGeometry(def.r, def.detail);
    g.scale(def.scale[0], def.scale[1], def.scale[2]);
    g.rotateX(Math.random() * Math.PI);
    g.rotateY(Math.random() * Math.PI);
    g.translate(def.pos[0], def.pos[1], def.pos[2]);
    shards.push(g);
  }

  const merged = mergeGeometries(shards, false);
  merged.computeVertexNormals();
  merged.center();
  return merged;
}

/**
 * Returns a Promise<THREE.Mesh> for the hero crystal.
 *
 * If a Draco-compressed GLTF exists at `modelUrl` it is loaded and re-skinned
 * with the ice shader; otherwise we fall back to the procedural cluster so the
 * experience always renders, even with no asset present.
 */
export function loadCrystal({ modelUrl = './models/crystal.glb', material } = {}) {
  const iceMat = material ?? createIceMaterial();

  return new Promise((resolve) => {
    const finishProcedural = () => {
      const geo = buildProceduralCluster();
      const mesh = new THREE.Mesh(geo, iceMat);
      mesh.userData.source = 'procedural';
      resolve(mesh);
    };

    const draco = new DRACOLoader();
    draco.setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.6/');

    const loader = new GLTFLoader();
    loader.setDRACOLoader(draco);

    loader.load(
      modelUrl,
      (gltf) => {
        // Collect the first mesh's geometry and re-skin with the ice shader.
        let found = null;
        gltf.scene.traverse((child) => {
          if (!found && child.isMesh) found = child;
        });
        if (!found) {
          finishProcedural();
          return;
        }
        found.material = iceMat;
        found.geometry.center();
        // Normalise scale so any model roughly fills the same volume.
        const box = new THREE.Box3().setFromObject(found);
        const size = new THREE.Vector3();
        box.getSize(size);
        const maxDim = Math.max(size.x, size.y, size.z) || 1;
        found.scale.setScalar(3.2 / maxDim);
        found.userData.source = 'gltf';
        resolve(found);
      },
      undefined,
      () => {
        // No model / failed fetch → procedural fallback (expected by default).
        finishProcedural();
      }
    );
  });
}
