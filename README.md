# FROST — an igloo.inc-inspired WebGL experience

A scroll-driven, frosted-crystal landing page built the same way [igloo.inc](https://www.igloo.inc/)
was: real-time **WebGL** instead of video, custom **GLSL shaders** for the look, and
**GSAP**-choreographed motion synced to a smooth-scroll engine.

This is a *near-same* recreation of the genre — same architecture and techniques, with
original geometry and shaders (not a copy of their proprietary assets).

## Stack

| Concern | Tool |
| --- | --- |
| 3D rendering | [Three.js](https://threejs.org/) (WebGL) |
| Look / material | Custom fresnel **ice shader** (`src/shaders/ice.js`) |
| Glow | `UnrealBloomPass` post-processing |
| Smooth scroll | [Lenis](https://github.com/darkroomengineering/lenis) |
| Animation | [GSAP](https://gsap.com/) |
| Build tool | [Vite](https://vitejs.dev/) |

## What it does

- A faceted **ice-shard crystal** rendered with a hand-written fresnel + noise shader.
  It loads a Draco-compressed **GLTF model** if you drop one at
  `public/models/crystal.glb`, and otherwise builds a procedural shard cluster so it
  always renders (see `src/crystal.js`).
- A ring of **orbiting ice shards** and a **reflective frozen-lake** ground plane
  (`src/environment.js`).
- A drifting particle snowfield with additive blending + bloom.
- A scroll narrative: the camera moves through keyframes and the palette shifts
  from icy blue toward magenta as you scroll.
- Pointer parallax, an animated loader, and an intro "bloom-in" sequence.

## Adding your own 3D model

Export a `.glb` from Blender, optionally Draco-compress it, and save it as
`public/models/crystal.glb`. See `public/models/README.md` for the exact steps. No
code change needed — the loader auto-centers, scales, and re-skins it with the ice shader.

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # production build into /dist
npm run preview  # serve the production build
```

## Where to customise

- **The look** lives in `src/shaders/ice.js` — change `uColorCore` / `uColorRim` or the
  noise frequency in `src/main.js`.
- **The scroll camera path** is the `camKeyframes` array in `src/main.js`.
- **Copy / sections** are plain HTML in `index.html`.

## How this compares to the real igloo.inc

The real site adds bespoke **Blender/Houdini** 3D models, far more elaborate shaders, and
heavy load-time optimisation (Draco/KTX2 compression, background shader compilation).
This project gives you the same *skeleton* to grow into that — swap the icosahedron for a
loaded `.glb` model and layer on more shader passes.
