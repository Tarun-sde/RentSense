/* eslint-disable @typescript-eslint/no-require-imports */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const path = require('node:path');

// Component effects with controlled React hooks and a Mapbox adapter; no network/WebGL claim.
function harness(file, token = 'pk.test', throws = false) {
  const slots = [], effects = [], maps = [], markers = [], timers = new Map();
  let index = 0, timerId = 0;
  const element = () => ({ children: [], style: {}, listeners: {}, append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); }, setAttribute() {}, addEventListener(name, fn) { this.listeners[name] = fn; } });
  const react = {
    useState(initial) { const i = index++; if (!(i in slots)) slots[i] = initial; return [slots[i], value => { slots[i] = value; }]; },
    useRef(initial) { const i = index++; return slots[i] ??= { current: initial }; },
    useMemo(fn) { return fn(); },
    useEffect(fn, deps) { const i = index++; const old = slots[i];
      if (!old || deps.some((v, n) => v !== old.deps[n])) effects.push(() => {
        old?.cleanup?.(); slots[i] = { deps, cleanup: fn() };
      });
    },
  };
  const mapbox = {
    Map: class { constructor() { if (throws) throw Error('WebGL unavailable'); this.handlers = {}; this.fits = 0; maps.push(this); }
      once(n, fn) { this.handlers[n] = fn; } on(n, fn) { this.handlers[n] = fn; } addControl() {} resize() {}
      remove() { this.removed = true; } fitBounds() { this.fits++; } flyTo() {} easeTo() {}
    },
    Marker: class { constructor({ element }) { this.element = element; markers.push(this); }
      setLngLat(p) { this.position = p; return this; } getLngLat() { return this.position; }
      setPopup(p) { this.popup = p; return this; } addTo() { return this; } remove() { this.removed = true; }
    },
    Popup: class { setDOMContent(node) { this.content = node; return this; } setLngLat() { return this; } addTo() { return this; } remove() {} },
    NavigationControl: class {}, LngLatBounds: class { extend() {} },
  };
  const timersApi = { setTimeout(fn) { timers.set(++timerId, fn); return timerId; }, clearTimeout(id) { timers.delete(id); } };
  const modules = new Map();
  const router = { push(url) { router.last = url; } };
  function load(filename) {
    if (modules.has(filename)) return modules.get(filename);
    const loadedModule = { exports: {} };
    const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true,
    } }).outputText;
    const requireMock = name => {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
      if (name === 'mapbox-gl') return mapbox;
      if (name === 'next/navigation') return { useRouter: () => router };
      if (name === '@/lib/utils') return { cn: (...args) => args.join(' ') };
      if (name.startsWith('@/lib/')) return load(path.resolve(__dirname, '..', name.slice(2) + '.ts'));
      return new Proxy({}, { get: (_, key) => String(key) });
    };
    vm.runInNewContext(code, { module: loadedModule, exports: loadedModule.exports, require: requireMock,
      process: { env: { NEXT_PUBLIC_MAPBOX_TOKEN: token } }, document: { createElement: element },
      window: timersApi, queueMicrotask: fn => effects.push(fn), console });
    modules.set(filename, loadedModule.exports); return loadedModule.exports;
  }
  const component = Object.values(load(path.resolve(__dirname, '../components', file)))[0];
  function walk(node) {
    if (!node || typeof node !== 'object') return;
    if (node.props?.ref && !node.props.ref.current) node.props.ref.current = element();
    const children = node.props?.children;
    for (const child of Array.isArray(children) ? children.flat(Infinity) : [children]) walk(child);
  }
  return { maps, markers, timers, router,
    render(props) { index = 0; const tree = component(props); walk(tree); while (effects.length) effects.shift()(); return tree; },
    stop() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
const site = { id: 'dynamic-site', name: '<img onerror=alert(1)>', latitude: 23, longitude: 72 };
const asset = { id: 'TEST-1', type: 'Excavator', status: 'ACTIVE', site, latest_telemetry: { latitude: 23.1, longitude: 72.1 } };

test('fleet map waits for load, updates/removes markers and cleans up', () => {
  const h = harness('dashboard/FleetMapCard.tsx');
  h.render({ equipmentList: [asset] });
  assert.equal(h.maps.length, 1); assert.equal(h.markers.length, 0);
  h.maps[0].handlers.load(); h.render({ equipmentList: [asset] });
  assert.equal(h.markers.length, 1);
  const marker = h.markers[0];
  assert.equal(marker.popup.content.children[2].textContent, `Site: ${site.name}`);
  h.render({ equipmentList: [{ ...asset, status: 'IDLE', latest_telemetry: { latitude: 24, longitude: 73 } }] });
  assert.equal(h.markers.length, 1); assert.equal(marker.position.join(','), '73,24');
  assert.equal(h.maps[0].fits, 1);
  marker.element.listeners.click(); assert.equal(h.router.last, '/assets/TEST-1');
  h.render({ equipmentList: [] }); assert.equal(marker.removed, true);
  h.stop(); assert.equal(h.maps[0].removed, true); assert.equal(h.timers.size, 0);
});

test('both maps handle missing tokens, construction failure, errors, timeout and early navigation', () => {
  for (const file of ['dashboard/FleetMapCard.tsx', 'assets/MiniMap.tsx']) {
    const props = { equipmentList: [asset], site, latitude: 23, longitude: 72 };
    const missing = harness(file, ''); missing.render(props); assert.equal(missing.maps.length, 0); missing.stop();
    const broken = harness(file, 'pk.test', true); broken.render(props); broken.stop(); assert.equal(broken.timers.size, 0);
    for (const trigger of ['error', 'timeout', 'navigate']) {
      const h = harness(file); h.render(props);
      if (trigger === 'error') h.maps[0].handlers.error();
      if (trigger === 'timeout') [...h.timers.values()][0]();
      h.stop(); assert.equal(h.maps[0].removed, true); assert.equal(h.timers.size, 0);
    }
  }
});

test('detail map uses valid site fallback then moves without reinitializing', () => {
  const h = harness('assets/MiniMap.tsx');
  h.render({ site, latitude: NaN, longitude: 200 });
  h.maps[0].handlers.load(); h.render({ site, latitude: 24, longitude: 73 });
  assert.equal(h.maps.length, 1); assert.equal(h.markers[0].position.join(','), '73,24');
  h.stop(); assert.equal(h.markers[0].removed, true);
});
