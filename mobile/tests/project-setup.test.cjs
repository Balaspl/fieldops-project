const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const readJson = (relativePath) => JSON.parse(fs.readFileSync(path.join(root, relativePath), 'utf8'));
const exists = (relativePath) => fs.existsSync(path.join(root, relativePath));
const { validateBuildEnvironment } = require('../scripts/validate-eas-env.cjs');


test('package manifest and lockfile are aligned', () => {
  const pkg = readJson('package.json');
  const lock = readJson('package-lock.json');
  assert.equal(pkg.name, 'fieldops-mobile');
  assert.equal(lock.name, pkg.name);
  assert.equal(lock.version, pkg.version);
  assert.deepEqual(lock.packages[''].dependencies, pkg.dependencies);
  assert.deepEqual(lock.packages[''].devDependencies, pkg.devDependencies);
});

test('project scripts and primary dependencies are declared', () => {
  const pkg = readJson('package.json');
  for (const script of ['start', 'android', 'ios', 'typecheck', 'test']) {
    assert.equal(typeof pkg.scripts[script], 'string', `missing ${script} script`);
  }
  for (const dependency of [
    'expo', 'expo-router', 'react-native', 'expo-secure-store',
    'expo-location', 'expo-camera', 'expo-notifications',
  ]) {
    assert.ok(pkg.dependencies[dependency], `missing ${dependency}`);
  }
});

test('Expo app identity, native plugins, and background-location configuration exist', () => {
  const expo = readJson('app.json').expo;
  assert.equal(expo.name, 'FieldOps');
  assert.equal(expo.android.package, 'com.fieldops.mobile');
  assert.equal(expo.ios.bundleIdentifier, 'com.fieldops.mobile');

  const plugins = new Map(expo.plugins.map((entry) => Array.isArray(entry) ? [entry[0], entry[1]] : [entry, {}]));
  for (const plugin of ['expo-router', 'expo-secure-store', 'expo-location', 'expo-camera', 'expo-notifications']) {
    assert.ok(plugins.has(plugin), `missing ${plugin} plugin`);
  }
  const location = plugins.get('expo-location');
  assert.equal(location.isAndroidBackgroundLocationEnabled, true);
  assert.equal(location.isAndroidForegroundServiceEnabled, true);
  assert.equal(location.isIosBackgroundLocationEnabled, true);
  assert.match(location.locationWhenInUsePermission, /location/i);

  assert.match(location.locationAlwaysAndWhenInUsePermission, /background/i);

});


test('app icon, adaptive icon, and splash-screen branding assets are configured', () => {
  const expo = readJson('app.json').expo;

  const plugins = new Map(
    expo.plugins.map((entry) =>
      Array.isArray(entry) ? [entry[0], entry[1]] : [entry, {}],
    ),
  );

  // Main application icon
  assert.equal(expo.icon, './assets/images/icon.png');
  assert.ok(exists(expo.icon), `missing app icon asset: ${expo.icon}`);

  // Android adaptive icon
  assert.deepEqual(expo.android.adaptiveIcon, {
    foregroundImage: './assets/images/adaptive-icon.png',
    backgroundColor: '#002A20',
  });

  assert.ok(
    exists(expo.android.adaptiveIcon.foregroundImage),
    'missing Android adaptive icon foreground asset',
  );

  // Native splash-screen configuration
  const splash = plugins.get('expo-splash-screen');

  assert.ok(splash, 'missing expo-splash-screen plugin');
  assert.equal(splash.image, './assets/images/fieldops-splash.png');
  assert.equal(splash.imageWidth, 200);
  assert.equal(splash.resizeMode, 'contain');
  assert.equal(splash.backgroundColor, '#002A20');

  // Full-screen branding shown during session restoration
  assert.ok(
    exists('assets/images/fieldops-splash.png'),
    'missing full-screen splash image',
  );

  const indexSource = fs.readFileSync(
    path.join(root, 'app/index.tsx'),
    'utf8',
  );

  assert.match(
    indexSource,
    /require\(["']\.\.\/assets\/images\/fieldops-splash\.png["']\)/,
    'startup screen must reference the full-screen splash image',
  );

  assert.match(
    indexSource,
    /restoreSession/,
    'startup screen must preserve session restoration',
  );
});


test('EAS development, preview, and production profiles exist', () => {
  const eas = readJson('eas.json');
  for (const profile of ['development', 'preview', 'production']) {
    assert.ok(eas.build[profile], `missing ${profile} profile`);
  }
  assert.equal(eas.build.development.developmentClient, true);
});

test('iOS build profiles, permissions, and EAS upload exclusions are configured', () => {
  const expo = readJson('app.json').expo;
  const eas = readJson('eas.json');

  // iOS identity and EAS project linkage
  assert.equal(expo.ios.bundleIdentifier, 'com.fieldops.mobile');
  assert.equal(
    expo.extra.eas.projectId,
    'd4664812-e07b-429c-8f98-8f9e9e0d0b76',
  );

  // iOS camera and microphone permission descriptions
  const plugins = new Map(
    expo.plugins.map((entry) =>
      Array.isArray(entry) ? [entry[0], entry[1]] : [entry, {}],
    ),
  );

  const camera = plugins.get('expo-camera');
  assert.match(camera.cameraPermission, /job evidence/i);
  assert.match(camera.microphonePermission, /video evidence/i);

  // Remote build-number management
  assert.equal(eas.cli.appVersionSource, 'remote');

  // iOS Simulator profile
  assert.equal(eas.build['ios-simulator'].ios.simulator, true);
  assert.equal(eas.build['ios-simulator'].environment, 'development');

  // Physical iOS device profile
  assert.equal(eas.build['ios-device'].ios.simulator, false);
  assert.equal(eas.build['ios-device'].extends, 'preview');

  // Environment-specific configuration
  assert.equal(eas.build.preview.environment, 'preview');
  assert.equal(eas.build.production.environment, 'production');
  assert.equal(eas.build.production.distribution, 'store');
  assert.equal(eas.build.production.autoIncrement, true);
  assert.equal(eas.cli.appVersionSource, 'remote');

  // Root EAS archive exclusions
  const easIgnorePath = path.resolve(root, '..', '.easignore');
  assert.ok(fs.existsSync(easIgnorePath), 'missing root .easignore');

  const easIgnore = fs.readFileSync(easIgnorePath, 'utf8');
  for (const pattern of [
    'backend/',
    '/mobile/android/app/build/',
    '/mobile/.env',
  ]) {
    assert.ok(easIgnore.includes(pattern), `missing EAS exclusion: ${pattern}`);
  }
});

test('required app modules and environment template exist', () => {
  for (const relativePath of [
    'app/_layout.tsx', 'app/(auth)/login.tsx', 'app/(auth)/mfa.tsx',
    'app/(app)/dashboard.tsx', 'app/(app)/jobs.tsx',
    'src/api/client.ts', 'src/auth/session.ts', 'src/gps/gpsTrackingService.ts',
    'src/notifications/notificationService.ts', '.env.example',
  ]) {
    assert.ok(exists(relativePath), `missing ${relativePath}`);
  }
});

test('gitignore excludes local secrets, dependency folders, and Expo state', () => {
  const ignore = fs.readFileSync(path.join(root, '.gitignore'), 'utf8');
  for (const pattern of ['node_modules/', '.expo/', '.env']) {
    assert.ok(ignore.includes(pattern), `missing ignore pattern: ${pattern}`);
  }
});

function loadEnvConfig(values = {}) {
  const keys = [
    'EXPO_PUBLIC_API_BASE_URL',
    'EXPO_PUBLIC_WS_BASE_URL',
  ];

  const previous = Object.fromEntries(
    keys.map((key) => [key, process.env[key]]),
  );

  try {
    for (const key of keys) {
      if (Object.hasOwn(values, key)) {
        process.env[key] = values[key];
      } else {
        delete process.env[key];
      }
    }

    const source = fs.readFileSync(
      path.join(root, 'src/config/env.ts'),
      'utf8',
    );

    const compiled = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2022,
      },
    }).outputText;

    const filename = path.join(root, 'src/config/env.test-runtime.cjs');
    const loadedModule = new Module(filename, module);
    loadedModule.filename = filename;
    loadedModule.paths = module.paths;
    loadedModule._compile(compiled, filename);

    return loadedModule.exports.env;
  } finally {
    for (const key of keys) {
      if (previous[key] === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = previous[key];
      }
    }
  }
}

test('environment configuration validates URLs and derives the WebSocket URL', () => {
  assert.deepEqual(
    loadEnvConfig({
      EXPO_PUBLIC_API_BASE_URL: 'https://api.example.com/',
    }),
    {
      APP_ENV: "development",
      API_BASE_URL: "https://api.example.com",
      WS_BASE_URL: "wss://api.example.com"
    },
  );

  assert.deepEqual(
    loadEnvConfig({
      EXPO_PUBLIC_API_BASE_URL: 'http://localhost:8000',
      EXPO_PUBLIC_WS_BASE_URL: 'ws://localhost:8000',
    }),
    {
      API_BASE_URL: "http://localhost:8000",
      WS_BASE_URL: "ws://localhost:8000",
      APP_ENV: "development"
    },
  );
});

test('environment configuration rejects missing API URLs and incorrect protocols', () => {
  assert.throws(
    () => loadEnvConfig(),
    /EXPO_PUBLIC_API_BASE_URL is missing/,
  );

  assert.throws(
    () => loadEnvConfig({
      EXPO_PUBLIC_API_BASE_URL: 'ws://localhost:8000',
    }),
    /EXPO_PUBLIC_API_BASE_URL must use one of these protocols/,
  );

  assert.throws(
    () => loadEnvConfig({
      EXPO_PUBLIC_API_BASE_URL: 'https://api.example.com',
      EXPO_PUBLIC_WS_BASE_URL: 'https://api.example.com',
    }),
    /EXPO_PUBLIC_WS_BASE_URL must use one of these protocols/,
  );
});

test('mobile source does not hardcode local development endpoints', () => {
  const sourceRoot = path.join(root, 'src');

  function collectSourceFiles(directory) {
    return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
      const fullPath = path.join(directory, entry.name);

      if (entry.isDirectory()) {
        return collectSourceFiles(fullPath);
      }

      return /\.(ts|tsx)$/.test(entry.name) ? [fullPath] : [];
    });
  }

  const localEndpointPattern =
    /192\.168\.1\.84|https?:\/\/localhost|wss?:\/\/localhost|10\.0\.2\.2/i;

  for (const file of collectSourceFiles(sourceRoot)) {
    const source = fs.readFileSync(file, 'utf8');

    assert.doesNotMatch(
      source,
      localEndpointPattern,
      `hardcoded development endpoint found in ${path.relative(root, file)}`,
    );
  }
});

test('EAS pre-install hook is configured', () => {
  const pkg = readJson('package.json');

  assert.equal(
    pkg.scripts['eas-build-pre-install'],
    'node scripts/validate-eas-env.cjs',
  );
  assert.ok(exists('scripts/validate-eas-env.cjs'));
});

test('EAS environment validation protects production builds', () => {
  assert.doesNotThrow(() =>
    validateBuildEnvironment({
      EAS_BUILD_PROFILE: 'preview',
      EXPO_PUBLIC_API_BASE_URL: 'http://192.168.1.84:8000',
      EXPO_PUBLIC_WS_BASE_URL: 'ws://192.168.1.84:8000',
    }),
  );

  assert.throws(
    () => validateBuildEnvironment({ EAS_BUILD_PROFILE: 'production' }),
    /EXPO_PUBLIC_API_BASE_URL is required/,
  );

  assert.throws(
    () =>
      validateBuildEnvironment({
        EAS_BUILD_PROFILE: 'production',
        EXPO_PUBLIC_API_BASE_URL: 'http://192.168.1.84:8000',
        EXPO_PUBLIC_WS_BASE_URL: 'ws://192.168.1.84:8000',
      }),
    /Production requires HTTPS API and WSS/,
  );

  assert.doesNotThrow(() =>
    validateBuildEnvironment({
      EAS_BUILD_PROFILE: 'production',
      EXPO_PUBLIC_API_BASE_URL: 'https://api.example.com',
      EXPO_PUBLIC_WS_BASE_URL: 'wss://api.example.com',
    }),
  );
});