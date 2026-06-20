# Drop a 3D model here

Place a Draco-compressed GLTF named `crystal.glb` in this folder and the app will
load it automatically (see `loadCrystal()` in `src/crystal.js`), re-skinning it with
the custom ice shader.

If no `crystal.glb` is present, the app falls back to a procedurally-generated
ice-shard cluster — so the experience always renders.

## Making a compatible model

1. Model an ice crystal / igloo in **Blender**.
2. Export as glTF Binary (`.glb`).
3. (Recommended) Compress with Draco:
   ```bash
   npx gltf-pipeline -i crystal.glb -o crystal.glb --draco.compressionLevel 7
   ```
4. Save it next to this file as `public/models/crystal.glb`.

The loader auto-centers and normalises scale, so the model just needs to be a single
mesh roughly centred on the origin.
