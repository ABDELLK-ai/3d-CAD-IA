/**
 * 3D CAD Studio — Three.js WebGL CAD Viewer Module
 * Handles 3D rendering, OrbitControls, materials, lighting, CAD edges, and snapshots.
 */

export class CADViewer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      throw new Error(`Container #${containerId} not found`);
    }

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;

    this.mesh = null;
    this.edgeLines = null;
    this.bboxHelper = null;
    this.grid = null;

    this.maxDim = 100;
    this.materials = {};
    this.currentMaterialKey = 'cad_blue';

    this.init();
  }

  init() {
    const W = this.container.clientWidth || 800;
    const H = this.container.clientHeight || 550;

    // 1. Scene
    this.scene = new THREE.Scene();

    // 2. Camera
    this.camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 10000);
    this.camera.position.set(120, 100, 140);

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      preserveDrawingBuffer: true,
    });
    this.renderer.setSize(W, H);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.container.appendChild(this.renderer.domElement);

    // 4. Controls
    this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.screenSpacePanning = true;

    // 5. Lighting
    const ambientLight = new THREE.HemisphereLight(0xffffff, 0x1a2333, 0.65);
    this.scene.add(ambientLight);

    this.mainLight = new THREE.DirectionalLight(0xffffff, 0.95);
    this.mainLight.position.set(180, 260, 200);
    this.mainLight.castShadow = true;
    this.scene.add(this.mainLight);

    const fillLight = new THREE.DirectionalLight(0x79c0ff, 0.45);
    fillLight.position.set(-180, -60, -180);
    this.scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.35);
    rimLight.position.set(0, 200, -220);
    this.scene.add(rimLight);

    // 6. Materials
    this.materials = {
      cad_blue: new THREE.MeshStandardMaterial({
        color: 0x388bfd,
        metalness: 0.25,
        roughness: 0.28,
        side: THREE.DoubleSide,
      }),
      steel: new THREE.MeshStandardMaterial({
        color: 0xd0d7de,
        metalness: 0.85,
        roughness: 0.18,
        side: THREE.DoubleSide,
      }),
      brass: new THREE.MeshStandardMaterial({
        color: 0xe3b341,
        metalness: 0.72,
        roughness: 0.32,
        side: THREE.DoubleSide,
      }),
      dark: new THREE.MeshStandardMaterial({
        color: 0x21262d,
        metalness: 0.35,
        roughness: 0.45,
        side: THREE.DoubleSide,
      }),
      orange: new THREE.MeshStandardMaterial({
        color: 0xf0883e,
        metalness: 0.2,
        roughness: 0.35,
        side: THREE.DoubleSide,
      }),
    };

    // 7. Initial empty grid
    this.grid = new THREE.GridHelper(200, 20, 0x30363d, 0x161b22);
    this.grid.position.y = -10;
    this.scene.add(this.grid);

    // 8. Resize observer
    if (window.ResizeObserver) {
      new ResizeObserver(() => this.onResize()).observe(this.container);
    } else {
      window.addEventListener('resize', () => this.onResize());
    }

    // 9. Animation loop
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  animate() {
    requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  onResize() {
    const W = this.container.clientWidth;
    const H = this.container.clientHeight;
    if (!W || !H) return;
    this.camera.aspect = W / H;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(W, H);
  }

  /**
   * Load STL geometry from base64 string or ArrayBuffer
   */
  loadSTL(stlData) {
    try {
      let buffer;
      if (typeof stlData === 'string') {
        const binary = atob(stlData);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        buffer = bytes.buffer;
      } else {
        buffer = stlData;
      }

      const loader = new THREE.STLLoader();
      const geometry = loader.parse(buffer);
      geometry.computeVertexNormals();
      geometry.center();

      // Bounding calculation
      geometry.computeBoundingBox();
      const bbox = geometry.boundingBox;
      const dx = bbox.max.x - bbox.min.x;
      const dy = bbox.max.y - bbox.min.y;
      const dz = bbox.max.z - bbox.min.z;
      this.maxDim = Math.max(dx, dy, dz, 10);

      // Clean old mesh
      if (this.mesh) {
        this.scene.remove(this.mesh);
        if (this.mesh.geometry) this.mesh.geometry.dispose();
      }
      if (this.bboxHelper) {
        this.scene.remove(this.bboxHelper);
      }
      if (this.grid) {
        this.scene.remove(this.grid);
      }

      // Create new mesh
      const mat = this.materials[this.currentMaterialKey] || this.materials.cad_blue;
      this.mesh = new THREE.Mesh(geometry, mat);
      this.mesh.castShadow = true;
      this.mesh.receiveShadow = true;

      // CadQuery Z-up coordinate system: rotate -90° around X so CAD Z becomes Three.js Y
      this.mesh.rotation.x = -Math.PI / 2;
      this.scene.add(this.mesh);

      // Mechanical feature edges
      const edgeGeo = new THREE.EdgesGeometry(geometry, 28);
      const edgeMat = new THREE.LineBasicMaterial({ color: 0x091427, linewidth: 1.2 });
      this.edgeLines = new THREE.LineSegments(edgeGeo, edgeMat);
      this.mesh.add(this.edgeLines);

      // Bounding box helper
      this.bboxHelper = new THREE.BoxHelper(this.mesh, 0x58a6ff);
      this.bboxHelper.visible = false;
      this.scene.add(this.bboxHelper);

      // Ground grid positioned underneath
      const gridY = -dz / 2 - (this.maxDim * 0.005);
      this.grid = new THREE.GridHelper(this.maxDim * 2.5, 24, 0x30363d, 0x161b22);
      this.grid.position.y = gridY;
      this.scene.add(this.grid);

      // Position camera
      this.setView('iso');

      // Return stats
      const triCount = geometry.attributes.position.count / 3;
      return {
        triangles: Math.round(triCount),
        bbox: { dx, dy, dz },
      };
    } catch (err) {
      console.error('CADViewer.loadSTL error:', err);
      throw err;
    }
  }

  setView(viewName) {
    this.controls.autoRotate = false;
    const d = this.maxDim * 2.0;

    switch (viewName) {
      case 'top':
        this.camera.position.set(0, d * 1.6, 0.001);
        break;
      case 'front':
        this.camera.position.set(0, 0, d * 1.6);
        break;
      case 'right':
        this.camera.position.set(d * 1.6, 0, 0);
        break;
      case 'iso':
      case 'reset':
      default:
        this.camera.position.set(d * 0.85, d * 0.75, d * 0.95);
        break;
    }

    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  setMaterial(key) {
    if (this.materials[key] && this.mesh) {
      this.currentMaterialKey = key;
      this.mesh.material = this.materials[key];
    }
  }

  toggleEdges(forceState) {
    if (!this.edgeLines) return false;
    this.edgeLines.visible = forceState !== undefined ? forceState : !this.edgeLines.visible;
    return this.edgeLines.visible;
  }

  toggleBBox(forceState) {
    if (!this.bboxHelper) return false;
    this.bboxHelper.visible = forceState !== undefined ? forceState : !this.bboxHelper.visible;
    return this.bboxHelper.visible;
  }

  toggleGrid(forceState) {
    if (!this.grid) return false;
    this.grid.visible = forceState !== undefined ? forceState : !this.grid.visible;
    return this.grid.visible;
  }

  toggleAutoRotate() {
    this.controls.autoRotate = !this.controls.autoRotate;
    this.controls.autoRotateSpeed = 2.0;
    return this.controls.autoRotate;
  }

  takeSnapshot(filename = 'cad_render.png') {
    this.renderer.render(this.scene, this.camera);
    const dataURL = this.renderer.domElement.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = dataURL;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }
}

