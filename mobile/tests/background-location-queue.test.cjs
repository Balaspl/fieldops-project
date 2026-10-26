const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");

const SERVICE_PATH = path.resolve(
  __dirname,
  "../src/gps/backgroundLocationService.ts"
);

const ACTIVE_CONTEXT_KEY = "fieldops:gps:active-context:v1";
const QUEUE_PREFIX = "fieldops:gps:pending:v1:";

function createGpsTestHarness() {
  // Legacy AsyncStorage used by the service.
  const storage = new Map();

  // Mock encrypted storage independently from legacy storage.
  const offlineRecords = new Map();

  // Mock Expo SecureStore independently from AsyncStorage.
  const secureStorage = new Map();

  const registeredTasks = new Map();
  const events = [];
  const errors = [];

  let batchOnline = false;

  function offlineRecordKey(scope, recordType, recordId) {
    return JSON.stringify([
      String(scope.tenantId),
      String(scope.technicianId),
      recordType,
      String(recordId)
    ]);
  }

  const asyncStorage = {
    async getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },

    async setItem(key, value) {
      storage.set(key, value);
    },

    async removeItem(key) {
      storage.delete(key);
    }
  };

  const secureStore = {
    async isAvailableAsync() {
      return true;
    },

    async getItemAsync(key) {
      return secureStorage.has(key)
        ? secureStorage.get(key)
        : null;
    },

    async setItemAsync(key, value) {
      secureStorage.set(key, value);
    },

    async deleteItemAsync(key) {
      secureStorage.delete(key);
    }
  };

  const offlineStore = {
    async getOfflineRecord(scope, recordType, recordId) {
      const key = offlineRecordKey(
        scope,
        recordType,
        recordId
      );

      const record = offlineRecords.get(key);

      return record ? record.data : null;
    },

    async setOfflineRecord(
      scope,
      recordType,
      recordId,
      data
    ) {
      const key = offlineRecordKey(
        scope,
        recordType,
        recordId
      );

      const mirrorKey =
        recordType === "gps-queue"
          ? queueKey(
              scope.tenantId,
              scope.technicianId,
              String(recordId)
            )
          : null;

      // Copy the payload to keep the mock deterministic.
      const copiedData = JSON.parse(JSON.stringify(data));

      offlineRecords.set(key, {
        data: copiedData,
        mirrorKey
      });
    },

    async deleteOfflineRecord(
      scope,
      recordType,
      recordId
    ) {
      const key = offlineRecordKey(
        scope,
        recordType,
        recordId
      );

      offlineRecords.delete(key);
    }
  };

  // Preserve the existing test assertions while keeping secure
  // storage, encrypted records, and legacy storage separate.
  const inspectedStorage = {
    has(key) {
      const secureAlias =
        `fieldops_secure_v1_${Buffer.from(key, "utf8").toString("hex")}`;

      if (
        secureStorage.has(key) ||
        secureStorage.has(secureAlias) ||
        storage.has(key)
      ) {
        return true;
      }

      return Array.from(offlineRecords.values()).some(
        (record) => record.mirrorKey === key
      );
    },

    get(key) {
      const secureAlias =
        `fieldops_secure_v1_${Buffer.from(key, "utf8").toString("hex")}`;

      if (secureStorage.has(secureAlias)) {
        return secureStorage.get(secureAlias);
      }

      if (secureStorage.has(key)) {
        return secureStorage.get(key);
      }

      if (storage.has(key)) {
        return storage.get(key);
      }

      const offlineRecord = Array.from(
        offlineRecords.values()
      ).find((record) => record.mirrorKey === key);

      if (offlineRecord) {
        return JSON.stringify(offlineRecord.data);
      }

      return undefined;
    }
  };

  const location = {
    Accuracy: {
      Balanced: 3,
      High: 6
    },

    async getForegroundPermissionsAsync() {
      return { status: "granted" };
    },

    async requestForegroundPermissionsAsync() {
      return { status: "granted" };
    },

    async getBackgroundPermissionsAsync() {
      return { status: "granted" };
    },

    async requestBackgroundPermissionsAsync() {
      return { status: "granted" };
    },

    async hasStartedLocationUpdatesAsync() {
      return false;
    },

    async startLocationUpdatesAsync() {},

    async getProviderStatusAsync() {
      return {
        locationServicesEnabled: true,
        gpsAvailable: true,
        networkAvailable: true
      };
    },

    async getCurrentPositionAsync() {
      return {
        timestamp: Date.parse("2026-10-23T10:00:00.000Z"),
        coords: {
          latitude: 13.0827,
          longitude: 80.2707,
          accuracy: 5,
          altitude: 10
        }
      };
    }
  };

  const taskManager = {
    defineTask(name, handler) {
      registeredTasks.set(name, handler);
    },

    isTaskDefined(name) {
      return registeredTasks.has(name);
    },

    async getRegisteredTasksAsync() {
      return Array.from(registeredTasks.keys()).map(
        (taskName) => ({ taskName })
      );
    }
  };

  const apiClient = {
    async post(url, body) {
      assert.equal(url, "/api/v1/gps/batch");

      if (!batchOnline) {
        throw new Error("Simulated backend outage");
      }

      return {
        data: {
          total: body.pings.length,
          succeeded: body.pings.length,
          failed: 0
        }
      };
    }
  };

  const mockedModules = new Map([
    [
      "@react-native-async-storage/async-storage",
      {
        __esModule: true,
        default: asyncStorage
      }
    ],
    ["expo-secure-store", secureStore],
    [
      "expo-crypto",
      {
        CryptoDigestAlgorithm: {
          SHA256: "SHA-256"
        },

        async digestStringAsync(_algorithm, value) {
          // Deterministic test double only; not real cryptography.
          return Buffer.from(value, "utf8").toString("hex");
        }
      }
    ],
    ["expo-location", location],
    ["expo-task-manager", taskManager],
    ["../offline/offlineStore", offlineStore],
    ["../api/client", { apiClient }],
    [
      "./gpsService",
      {
        async sendTechnicianAvailabilityPing() {}
      }
    ],
    [
      "../observability/logger",
      {
        logEvent(name, details) {
          events.push({ name, details });
        },

        logError(name, error) {
          errors.push({ name, error });
        }
      }
    ]
  ]);

  const source = fs.readFileSync(SERVICE_PATH, "utf8");

  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;

  const originalLoad = Module._load;
  let loadedModule;

  try {
    Module._load = function (request, parent, isMain) {
      if (mockedModules.has(request)) {
        return mockedModules.get(request);
      }

      return originalLoad.call(this, request, parent, isMain);
    };

    loadedModule = new Module(SERVICE_PATH, module);
    loadedModule.filename = SERVICE_PATH;
    loadedModule.paths = Module._nodeModulePaths(
      path.dirname(SERVICE_PATH)
    );

    loadedModule._compile(compiled, SERVICE_PATH);
  } finally {
    Module._load = originalLoad;
  }

  return {
    service: loadedModule.exports,
    storage: inspectedStorage,
    events,
    errors,

    setBackendOnline(value) {
      batchOnline = value;
    }
  };
}

function queueKey(tenantId, technicianId, jobId) {
  return (
    `${QUEUE_PREFIX}${encodeURIComponent(tenantId)}:` +
    `${encodeURIComponent(technicianId)}:` +
    `${encodeURIComponent(jobId)}`
  );
}

async function startTechnician(harness) {
  const identity = {
    technicianId: "tech-test-1",
    tenantId: "tenant-test-1"
  };

  await harness.service.setTechnicianLocationConsent(
    identity,
    true
  );

  await harness.service.startTechnicianLocationTracking(identity);

  return identity;
}

test(
  "GPS points remain queued after job completion and sync on retry",
  async () => {
    const harness = createGpsTestHarness();

    const identity = await startTechnician(harness);
    const jobId = "job-test-101";

    const expectedQueueKey = queueKey(
      identity.tenantId,
      identity.technicianId,
      jobId
    );

    await harness.service.setActiveGpsJob(jobId);

    const queuedBeforeCompletion = JSON.parse(
      harness.storage.get(expectedQueueKey)
    );

    assert.equal(queuedBeforeCompletion.length, 1);
    assert.equal(queuedBeforeCompletion[0].job_id, jobId);

    await harness.service.clearActiveGpsJob(jobId);

    const savedContext = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.equal(savedContext.activeJobId, undefined);
    assert.deepEqual(savedContext.pendingJobIds, [jobId]);
    assert.equal(harness.storage.has(expectedQueueKey), true);

    harness.setBackendOnline(true);

    await harness.service.flushPendingGpsPings();

    assert.equal(harness.storage.has(expectedQueueKey), false);

    const recoveredContext = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.equal(recoveredContext.pendingJobIds, undefined);

    assert.equal(
      harness.events.some(
        (event) => event.name === "gps.offline_batch_synced"
      ),
      true
    );
  }
);

test(
  "GPS points from a previous job remain separate and can be retried",
  async () => {
    const harness = createGpsTestHarness();

    const identity = await startTechnician(harness);

    const previousJobId = "job-test-201";
    const activeJobId = "job-test-202";

    const previousQueueKey = queueKey(
      identity.tenantId,
      identity.technicianId,
      previousJobId
    );

    const activeQueueKey = queueKey(
      identity.tenantId,
      identity.technicianId,
      activeJobId
    );

    await harness.service.setActiveGpsJob(previousJobId);

    await harness.service.setActiveGpsJob(activeJobId);

    const savedContext = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.equal(savedContext.activeJobId, activeJobId);
    assert.deepEqual(savedContext.pendingJobIds, [previousJobId]);

    assert.equal(harness.storage.has(previousQueueKey), true);
    assert.equal(harness.storage.has(activeQueueKey), true);

    const previousPoints = JSON.parse(
      harness.storage.get(previousQueueKey)
    );

    const activePoints = JSON.parse(
      harness.storage.get(activeQueueKey)
    );

    assert.ok(previousPoints.every(
      (ping) => ping.job_id === previousJobId
    ));

    assert.ok(activePoints.every(
      (ping) => ping.job_id === activeJobId
    ));

    harness.setBackendOnline(true);

    await harness.service.flushPendingGpsPings();

    assert.equal(harness.storage.has(previousQueueKey), false);
    assert.equal(harness.storage.has(activeQueueKey), false);

    const recoveredContext = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.equal(recoveredContext.activeJobId, activeJobId);
    assert.equal(recoveredContext.pendingJobIds, undefined);
  }
);

test(
  "pending GPS queues survive tracking restart for the same technician and tenant",
  async () => {
    const harness = createGpsTestHarness();
    const identity = await startTechnician(harness);
    const jobId = "job-test-restart-301";

    const expectedQueueKey = queueKey(
      identity.tenantId,
      identity.technicianId,
      jobId
    );

    // Start tracking a job while the simulated backend is offline.
    await harness.service.setActiveGpsJob(jobId);

    // Finish the job while its final GPS points cannot sync.
    await harness.service.clearActiveGpsJob(jobId);

    const beforeRestart = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.deepEqual(beforeRestart.pendingJobIds, [jobId]);
    assert.equal(harness.storage.has(expectedQueueKey), true);

    // Restart tracking under the same authenticated identity.
    await harness.service.startTechnicianLocationTracking(identity);

    const afterRestart = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.deepEqual(afterRestart.pendingJobIds, [jobId]);
    assert.equal(harness.storage.has(expectedQueueKey), true);

    // Restore backend connectivity and retry the retained queue.
    harness.setBackendOnline(true);

    await harness.service.flushPendingGpsPings();

    assert.equal(harness.storage.has(expectedQueueKey), false);

    const recoveredContext = JSON.parse(
      harness.storage.get(ACTIVE_CONTEXT_KEY)
    );

    assert.equal(recoveredContext.pendingJobIds, undefined);

    assert.equal(
      harness.events.some(
        (event) => event.name === "gps.offline_batch_synced"
      ),
      true
    );
  }
);