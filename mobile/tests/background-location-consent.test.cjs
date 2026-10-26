const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

const gpsSource = fs.readFileSync(
  path.join(root, "src/gps/backgroundLocationService.ts"),
  "utf8"
);

const profileSource = fs.readFileSync(
  path.join(root, "app/(app)/profile.tsx"),
  "utf8"
);

const trackingStart = gpsSource.indexOf(
  "export async function startTechnicianLocationTracking"
);

const activeJobStart = gpsSource.indexOf(
  "export async function setActiveGpsJob"
);

assert.notEqual(trackingStart, -1);
assert.notEqual(activeJobStart, -1);

const trackingStartSource = gpsSource.slice(
  trackingStart,
  activeJobStart
);

test("location consent is scoped to the technician and tenant", () => {
  assert.match(
    gpsSource,
    /const LOCATION_CONSENT_PREFIX = "fieldops:gps:consent:v1:"/
  );

  assert.match(
    gpsSource,
    /encodeURIComponent\(tenantId\)/
  );

  assert.match(
    gpsSource,
    /encodeURIComponent\(technicianId\)/
  );
});

test("location consent defaults to denied", () => {
  assert.match(
    gpsSource,
    /return value === "granted";/
  );
});

test("consent updates persist granted and denied states", () => {
  const secureWriteStart = gpsSource.indexOf(
    "async function writeProtectedValue("
  );

  const secureWriteEnd = gpsSource.indexOf(
    "async function deleteProtectedValue("
  );

  const consentWriteStart = gpsSource.indexOf(
    "export async function setTechnicianLocationConsent("
  );

  const contextReadStart = gpsSource.indexOf(
    "async function readContext("
  );

  assert.notEqual(secureWriteStart, -1);
  assert.notEqual(secureWriteEnd, -1);
  assert.notEqual(consentWriteStart, -1);
  assert.notEqual(contextReadStart, -1);

  const secureWriteSource = gpsSource.slice(
    secureWriteStart,
    secureWriteEnd
  );

  const consentWriteSource = gpsSource.slice(
    consentWriteStart,
    contextReadStart
  );

  // Consent values must be written through secure storage.
  assert.match(
    secureWriteSource,
    /await SecureStore\.setItemAsync\(secureKey, value\);/
  );

  // The consent setter must use the tenant-and-technician scoped key.
  assert.match(
    consentWriteSource,
    /locationConsentKey\(identity\)/
  );

  // Both granted and denied states must be persisted.
  assert.match(
    consentWriteSource,
    /granted\s*\?\s*"granted"\s*:\s*"denied"/
  );

  assert.match(
    consentWriteSource,
    /await writeProtectedValue\(/
  );
});

test("tracking checks consent before reading context or requesting permissions", () => {
  const consentCheck = trackingStartSource.indexOf(
    "hasTechnicianLocationConsent"
  );

  const contextRead = trackingStartSource.indexOf(
    "const existing = await readContext()"
  );

  const permissionCheck = trackingStartSource.indexOf(
    "Location.getForegroundPermissionsAsync"
  );

  assert.notEqual(consentCheck, -1);
  assert.notEqual(contextRead, -1);
  assert.notEqual(permissionCheck, -1);

  assert.ok(consentCheck < contextRead);
  assert.ok(consentCheck < permissionCheck);
});

test("tracking skips startup when consent is not granted", () => {
  assert.match(
    trackingStartSource,
    /if \(!consentGranted\)/
  );

  assert.match(
    trackingStartSource,
    /gps\.tracking_skipped_no_consent/
  );

  assert.match(
    trackingStartSource,
    /if \(!consentGranted\)[\s\S]*?return;/
  );
});

test("profile provides an explicit location-sharing consent action", () => {
  assert.match(
    profileSource,
    /Enable location sharing/
  );

  assert.match(
    profileSource,
    /Allow location sharing/
  );

  assert.match(
    profileSource,
    /Turn off location sharing/
  );

  assert.match(
    profileSource,
    /Withdraw location-sharing consent/
  );
});

test("granting consent starts tracking and rolls back if startup fails", () => {
  assert.match(
    profileSource,
    /setTechnicianLocationConsent\(identity, true\)/
  );

  assert.match(
    profileSource,
    /await startTechnicianLocationTracking\(identity\)/
  );

  assert.match(
    profileSource,
    /setTechnicianLocationConsent\(identity, false\);[\s\S]*?throw error;/
  );
});

test("withdrawing consent persists denial before stopping tracking", () => {
  const withdrawal = profileSource.indexOf(
    "await setTechnicianLocationConsent(identity, false)"
  );

  const stopTracking = profileSource.indexOf(
    "await stopTechnicianLocationTracking()"
  );

  assert.notEqual(withdrawal, -1);
  assert.notEqual(stopTracking, -1);
  assert.ok(withdrawal < stopTracking);
});