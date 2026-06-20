import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { gsap } from 'gsap';
import Lenis from 'lenis';

import { createIceMaterial, loadCrystal } from './crystal.js';
import { createOrbitRing, createFrozenGround } from './environment.js';

/* ------------------------------------------------------------------ *
 * Boilerplate: renderer, scene, camera
 * ------------------------------------------------------------------ */
const canvas = document.querySelector('#webgl');
const sizes = { width: window.innerWidth, height: window.innerHeight };

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x05070d, 0.055);

const camera = new THREE.PerspectiveCamera(45, sizes.width / sizes.height, 0.1, 100);
camera.position.set(0, 0, 6);
scene.add(camera);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setSize(sizes.width, sizes.height);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setClearColor(0x05070d, 1);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;

/* ------------------------------------------------------------------ *
 * The crystal — shared ice material, async geometry (GLTF or procedural)
 * ------------------------------------------------------------------ */
const crystalMat = createIceMaterial();
const crystalUniforms = crystalMat.uniforms;

let crystal = null; // populated once loadCrystal resolves
loadCrystal({ material: crystalMat }).then((mesh) => {
  crystal = mesh;
  scene.add(crystal);
  // Bloom-in once geometry is ready.
  gsap.fromTo(
    crystalUniforms.uDisplace,
    { value: 1.4 },
    { value: 0.35, duration: 2.2, ease: 'expo.out' }
  );
});

// A faint wireframe shell for extra "facet" detail.
const shellGeo = new THREE.IcosahedronGeometry(1.95, 2);
const shellMat = new THREE.MeshBasicMaterial({
  color: 0x7fd4ff,
  wireframe: true,
  transparent: true,
  opacity: 0.12
});
const shell = new THREE.Mesh(shellGeo, shellMat);
scene.add(shell);

/* ------------------------------------------------------------------ *
 * Environment: orbiting shard ring + reflective frozen ground
 * ------------------------------------------------------------------ */
const orbitRing = createOrbitRing();
scene.add(orbitRing);

const ground = createFrozenGround();
scene.add(ground);

/* ------------------------------------------------------------------ *
 * Snowfield — a drifting particle system
 * ------------------------------------------------------------------ */
const PARTICLE_COUNT = 1400;
const positions = new Float32Array(PARTICLE_COUNT * 3);
for (let i = 0; i < PARTICLE_COUNT; i++) {
  positions[i * 3 + 0] = (Math.random() - 0.5) * 22;
  positions[i * 3 + 1] = (Math.random() - 0.5) * 22;
  positions[i * 3 + 2] = (Math.random() - 0.5) * 22;
}
const particleGeo = new THREE.BufferGeometry();
particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const particleMat = new THREE.PointsMaterial({
  color: 0xbfe6ff,
  size: 0.025,
  transparent: true,
  opacity: 0.8,
  depthWrite: false,
  blending: THREE.AdditiveBlending
});
const particles = new THREE.Points(particleGeo, particleMat);
scene.add(particles);

/* ------------------------------------------------------------------ *
 * Lighting (for the lit shards / ground; crystal is an unlit shader)
 * ------------------------------------------------------------------ */
scene.add(new THREE.AmbientLight(0x223355, 1.2));
const keyLight = new THREE.DirectionalLight(0x9fd8ff, 2.0);
keyLight.position.set(3, 4, 5);
scene.add(keyLight);

/* ------------------------------------------------------------------ *
 * Post-processing: bloom for the glowing rim
 * ------------------------------------------------------------------ */
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(
  new THREE.Vector2(sizes.width, sizes.height),
  0.7,
  0.6,
  0.85
);
composer.addPass(bloom);

/* ------------------------------------------------------------------ *
 * Pointer parallax
 * ------------------------------------------------------------------ */
const pointer = { x: 0, y: 0, tx: 0, ty: 0 };
window.addEventListener('pointermove', (e) => {
  pointer.tx = (e.clientX / sizes.width - 0.5) * 2;
  pointer.ty = (e.clientY / sizes.height - 0.5) * 2;
});

/* ------------------------------------------------------------------ *
 * Smooth scroll (Lenis) + scroll-driven camera narrative
 * ------------------------------------------------------------------ */
const lenis = new Lenis({ lerp: 0.08, smoothWheel: true });
let scrollProgress = 0;
const progressBar = document.querySelector('#progressBar');

lenis.on('scroll', ({ scroll, limit }) => {
  scrollProgress = limit > 0 ? scroll / limit : 0;
  if (progressBar) progressBar.style.width = `${scrollProgress * 100}%`;
});

function raf(time) {
  lenis.raf(time);
  requestAnimationFrame(raf);
}
requestAnimationFrame(raf);

const camKeyframes = [
  { x: 0, y: 0, z: 6 },
  { x: -2.2, y: 0.4, z: 5 },
  { x: 2.2, y: -0.4, z: 5 },
  { x: 0, y: 0, z: 4.2 }
];

function sampleCamera(p) {
  const segs = camKeyframes.length - 1;
  const scaled = THREE.MathUtils.clamp(p, 0, 1) * segs;
  const i = Math.min(Math.floor(scaled), segs - 1);
  const t = scaled - i;
  const a = camKeyframes[i];
  const b = camKeyframes[i + 1];
  return {
    x: THREE.MathUtils.lerp(a.x, b.x, t),
    y: THREE.MathUtils.lerp(a.y, b.y, t),
    z: THREE.MathUtils.lerp(a.z, b.z, t)
  };
}

/* ------------------------------------------------------------------ *
 * Animated palette across the scroll
 * ------------------------------------------------------------------ */
const rimColorA = new THREE.Color(0x9fe0ff);
const rimColorB = new THREE.Color(0xff9fd6);
const coreColorA = new THREE.Color(0x0a2a4a);
const coreColorB = new THREE.Color(0x2a0a4a);

/* ------------------------------------------------------------------ *
 * Render loop
 * ------------------------------------------------------------------ */
const clock = new THREE.Clock();

function tick() {
  const elapsed = clock.getElapsedTime();
  crystalUniforms.uTime.value = elapsed;

  if (crystal) {
    crystal.rotation.y = elapsed * 0.15;
    crystal.rotation.x = Math.sin(elapsed * 0.2) * 0.15;
  }
  shell.rotation.y = -elapsed * 0.08;
  shell.rotation.z = elapsed * 0.05;
  particles.rotation.y = elapsed * 0.02;

  // Orbit ring rotates as a whole; each shard tumbles on its own axis.
  orbitRing.rotation.y = elapsed * 0.12;
  for (const shard of orbitRing.children) {
    shard.rotation.x += 0.01 * shard.userData.spin;
    shard.rotation.y += 0.012 * shard.userData.spin;
  }

  // Scroll-driven camera target + smooth pointer parallax
  const target = sampleCamera(scrollProgress);
  pointer.x += (pointer.tx - pointer.x) * 0.05;
  pointer.y += (pointer.ty - pointer.y) * 0.05;

  camera.position.x += (target.x + pointer.x * 0.4 - camera.position.x) * 0.06;
  camera.position.y += (target.y - pointer.y * 0.4 - camera.position.y) * 0.06;
  camera.position.z += (target.z - camera.position.z) * 0.06;
  camera.lookAt(0, 0, 0);

  // Palette shift toward magenta near the end of the scroll
  crystalUniforms.uColorRim.value.copy(rimColorA).lerp(rimColorB, scrollProgress);
  crystalUniforms.uColorCore.value.copy(coreColorA).lerp(coreColorB, scrollProgress);

  composer.render();
  requestAnimationFrame(tick);
}
tick();

/* ------------------------------------------------------------------ *
 * Resize handling
 * ------------------------------------------------------------------ */
window.addEventListener('resize', () => {
  sizes.width = window.innerWidth;
  sizes.height = window.innerHeight;
  camera.aspect = sizes.width / sizes.height;
  camera.updateProjectionMatrix();
  renderer.setSize(sizes.width, sizes.height);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  composer.setSize(sizes.width, sizes.height);
});

/* ------------------------------------------------------------------ *
 * Loader + intro animation
 * ------------------------------------------------------------------ */
const loader = document.querySelector('#loader');
const loaderCount = document.querySelector('#loaderCount');

function runIntro() {
  const counter = { v: 0 };
  gsap.to(counter, {
    v: 100,
    duration: 1.8,
    ease: 'power2.inOut',
    onUpdate: () => {
      if (loaderCount) loaderCount.textContent = Math.round(counter.v);
    },
    onComplete: () => {
      loader.classList.add('is-done');
      gsap.fromTo(
        camera.position,
        { z: 11 },
        { z: 6, duration: 2.4, ease: 'expo.out' }
      );
      gsap.from('.hero__title .line', {
        yPercent: 120,
        opacity: 0,
        duration: 1.2,
        stagger: 0.12,
        ease: 'expo.out',
        delay: 0.2
      });
    }
  });
}

if (document.readyState === 'complete') {
  runIntro();
} else {
  window.addEventListener('load', runIntro);
}
