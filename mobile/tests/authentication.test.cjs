
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");

function loadTypeScript(relativePath, mocks = {}) {
  const filename = path.join(
    root,
    "__auth_test_runtime__",
    `${relativePath.replace(/[\\/.:]/g, "_")}.cjs`
  );

  const source = fs.readFileSync(
    path.join(root, relativePath),
    "utf8"
  );

  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true
    }
  }).outputText;

  const loadedModule = new Module(filename, module);
  loadedModule.filename = filename;
  loadedModule.paths = Module._nodeModulePaths(root);

  const originalLoad = Module._load;

  Module._load = function (request, parent, isMain) {
    if (
      parent?.filename === filename &&
      Object.hasOwn(mocks, request)
    ) {
      return mocks[request];
    }

    return originalLoad.call(this, request, parent, isMain);
  };

  try {
    loadedModule._compile(compiled, filename);
    return loadedModule.exports;
  } finally {
    Module._load = originalLoad;
  }
}

// Mock platform secure storage so tests never touch real credentials.
const secureValues = new Map();

const secureStoreMock = {
  async setItemAsync(key, value) {
    secureValues.set(key, value);
  },

  async getItemAsync(key) {
    return secureValues.get(key) ?? null;
  },

  async deleteItemAsync(key) {
    secureValues.delete(key);
  }
};


const { mock } = require("node:test");

const secureStoreTestValues = new Map();

mock.module("expo-secure-store", {
  namedExports: {
    AFTER_FIRST_UNLOCK: "AFTER_FIRST_UNLOCK",
    WHEN_UNLOCKED: "WHEN_UNLOCKED",
    getItemAsync: async (key) => secureStoreTestValues.get(key) ?? null,
    setItemAsync: async (key, value) => {
      secureStoreTestValues.set(key, value);
    },
    deleteItemAsync: async (key) => {
      secureStoreTestValues.delete(key);
    },
    isAvailableAsync: async () => true
  }
});


const session = loadTypeScript("src/auth/session.ts", {
  "expo-secure-store": secureStoreMock
});

test("session tokens are trimmed and stored separately", async () => {
  secureValues.clear();

  await session.storeSessionTokens({
    accessToken: " access-token ",
    refreshToken: " refresh-token "
  });

  assert.equal(
    await session.getAccessToken(),
    "access-token"
  );

  assert.equal(
    await session.getRefreshToken(),
    "refresh-token"
  );
});

test("blank access tokens are rejected", async () => {
  secureValues.clear();

  await assert.rejects(
    session.storeSessionTokens({
      accessToken: "   "
    }),
    /access token is required/i
  );

  assert.equal(secureValues.size, 0);
});

test("omitting a refresh token removes the previous refresh token", async () => {
  secureValues.clear();

  await session.storeSessionTokens({
    accessToken: "old-access",
    refreshToken: "old-refresh"
  });

  await session.storeSessionTokens({
    accessToken: "new-access"
  });

  assert.equal(await session.getAccessToken(), "new-access");
  assert.equal(await session.getRefreshToken(), null);
});

test("clearing the session removes both tokens", async () => {
  secureValues.clear();

  await session.storeSessionTokens({
    accessToken: "access",
    refreshToken: "refresh"
  });

  await session.clearSessionTokens();

  assert.equal(await session.getAccessToken(), null);
  assert.equal(await session.getRefreshToken(), null);
});

// Mock the API and storage boundaries to test the MFA service itself.
let mfaResponse;
const mfaCalls = [];
const storedMfaSessions = [];

const mfaService = loadTypeScript("src/auth/mfaService.ts", {
  "../api/client": {
    apiClient: {
      async post(url, payload) {
        mfaCalls.push({ url, payload });
        return { data: mfaResponse };
      }
    }
  },

  "./session": {
    async storeSessionTokens(tokens) {
      storedMfaSessions.push(tokens);
    },

    async clearSessionTokens() {}
  }
});

function validMfaResponse() {
  return {
    status: "VERIFIED",
    mfa_required: true,
    challenge: "challenge-123",
    replay_protected: true,
    access_token: "access-token",
    refresh_token: "refresh-token",
    token_type: "bearer",
    expires_in: 900,
    user: {
      id: "user-1",
      email: "technician@example.com",
      role: "technician",
      tenant_id: "tenant-1"
    }
  };
}

test("MFA verification sends challenge and code, then stores tokens", async () => {
  mfaCalls.length = 0;
  storedMfaSessions.length = 0;
  mfaResponse = validMfaResponse();

  const result = await mfaService.verifyMfa({
    challenge: "challenge-123",
    code: "123456"
  });

  assert.equal(mfaCalls.length, 1);
  assert.equal(mfaCalls[0].url, "/auth/mfa/verify");
  assert.deepEqual(mfaCalls[0].payload, {
    challenge: "challenge-123",
    code: "123456"
  });

  assert.equal(result.access_token, "access-token");
  assert.deepEqual(storedMfaSessions, [{
    accessToken: "access-token",
    refreshToken: "refresh-token"
  }]);
});

test("MFA rejects an invalid verification code before calling the API", async () => {
  mfaCalls.length = 0;

  await assert.rejects(
    mfaService.verifyMfa({
      challenge: "challenge-123",
      code: "123"
    }),
    /six-digit/i
  );

  assert.equal(mfaCalls.length, 0);
});

test("MFA recovery sends challenge and recovery code", async () => {
  mfaCalls.length = 0;
  storedMfaSessions.length = 0;
  mfaResponse = validMfaResponse();

  await mfaService.verifyMfaRecovery({
    challenge: "challenge-123",
    recovery_code: "recovery-code"
  });

  assert.equal(mfaCalls.length, 1);
  assert.equal(mfaCalls[0].url, "/auth/mfa/recovery");
  assert.deepEqual(mfaCalls[0].payload, {
    challenge: "challenge-123",
    recovery_code: "recovery-code"
  });

  assert.equal(storedMfaSessions.length, 1);
});

test("MFA recovery rejects an empty recovery code", async () => {
  mfaCalls.length = 0;

  await assert.rejects(
    mfaService.verifyMfaRecovery({
      challenge: "challenge-123",
      recovery_code: "   "
    }),
    /recovery code/i
  );

  assert.equal(mfaCalls.length, 0);
});

test("MFA refuses to store a session without a refresh token", async () => {
  mfaCalls.length = 0;
  storedMfaSessions.length = 0;

  mfaResponse = {
    ...validMfaResponse(),
    refresh_token: ""
  };

  await assert.rejects(
    mfaService.verifyMfa({
      challenge: "challenge-123",
      code: "123456"
    }),
    /valid session tokens/i
  );

  assert.equal(storedMfaSessions.length, 0);
});

// Verify the app screen actually passes the challenge from its auth store.
test("MFA screen sends the stored challenge for both verification paths", () => {
  const source = fs.readFileSync(
    path.join(root, "app/(auth)/mfa.tsx"),
    "utf8"
  );

  assert.match(source, /state\.mfaChallenge/);
  assert.match(source, /challenge:\s*mfaChallenge/);
  assert.match(source, /clearMfaChallenge/);
});

// Verify that non-technician accounts cannot log in to the technician app.
let roleTestLoginResult;
let roleTestClearCount = 0;

const roleTestModule = loadTypeScript("src/auth/authStore.ts", {
  "./session": {
    async clearSessionTokens() {
      roleTestClearCount += 1;
    }
  },
  "./authService": {
    async login() {
      return roleTestLoginResult;
    },
    async getCurrentUser() {
      throw new Error("Unexpected current-user request");
    },
    async logout() {}
  }
});

const roleTestStore = roleTestModule.useAuthStore;

test("login rejects non-technician accounts and clears session tokens", async () => {
  roleTestLoginResult = {
    access_token: "test-access-token",
    refresh_token: "test-refresh-token",
    user: {
      id: "admin-1",
      email: "admin@example.com",
      role: "admin",
      tenant_id: "tenant-1"
    }
  };

  roleTestClearCount = 0;

  roleTestStore.setState({
    user: null,
    mfaChallenge: null,
    isAuthenticated: false,
    isLoading: false,
    error: null
  });

  await assert.rejects(
    roleTestStore.getState().login({
      email: "admin@example.com",
      password: "test-password"
    }),
    /technician accounts/i
  );

  const state = roleTestStore.getState();

  assert.equal(state.isAuthenticated, false);
  assert.equal(state.user, null);
  assert.equal(state.isLoading, false);
  assert.match(state.error, /technician accounts/i);
  assert.ok(roleTestClearCount > 0);
});

test("session restoration rejects non-technician accounts and clears session tokens", async () => {
  let currentUser = {
    id: "customer-1",
    email: "customer@example.com",
    role: "customer",
    tenant_id: "tenant-1"
  };

  let clearCount = 0;

  const restoreTestModule = loadTypeScript("src/auth/authStore.ts", {
    "./session": {
      async clearSessionTokens() {
        clearCount += 1;
      }
    },
    "./authService": {
      async login() {
        throw new Error("Unexpected login request");
      },
      async getCurrentUser() {
        return currentUser;
      },
      async logout() {}
    }
  });

  const restoreTestStore = restoreTestModule.useAuthStore;

  restoreTestStore.setState({
    user: null,
    mfaChallenge: null,
    isAuthenticated: false,
    isLoading: false,
    error: null
  });

  await restoreTestStore.getState().restoreSession();

  const state = restoreTestStore.getState();

  assert.equal(state.isAuthenticated, false);
  assert.equal(state.user, null);
  assert.equal(state.isLoading, false);
  assert.match(state.error, /technician accounts/i);
  assert.ok(clearCount > 0);
});