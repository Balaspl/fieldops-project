const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

const screenPath = path.join(
  root,
  "app",
  "(app)",
  "jobs",
  "[jobId].tsx"
);

const source = fs.readFileSync(screenPath, "utf8");

test("job details loads the selected job through the existing API", () => {
  assert.match(source, /getTechnicianJob/);
  assert.match(source, /getTechnicianJob\(requestedJobId\)/);
  assert.match(source, /setJob\(result\)/);
});

test("job details displays backend job information", () => {
  assert.match(source, /getJobStatusLabel\(job\.status\)/);
  assert.match(source, /job\.customer_name/);
  assert.match(source, /job\.address/);
  assert.match(source, /job\.scheduled_at/);
  assert.match(source, /job\.description/);
  assert.match(source, /job\.priority/);
});

test("job details uses the shared job status workflow", () => {
  assert.match(source, /normalizeJobStatus/);
  assert.match(source, /getJobActionOptions\(job\.status\)/);
});

test("job actions are submitted through the existing backend service", () => {
  assert.match(source, /performTechnicianJobAction/);
  assert.match(source, /submitJobAction\(action\)/);
  assert.match(source, /action === "reject"/);
  assert.match(source, /action === "complete"/);
});

test("job rejection requires a reason before submission", () => {
  assert.match(source, /rejectionReason\.trim\(\)/);
  assert.match(source, /reason\.length < 10/);
  assert.match(
    source,
    /submitJobAction\("reject", \{ reason \}\)/
  );
});

test("en-route and on-site actions connect the active job to background GPS tracking", () => {
  assert.match(source, /action === "start" \|\| action === "on-site"/);
  assert.match(source, /setActiveGpsJob/);
  assert.match(source, /await setActiveGpsJob\(job\.id\)/);
  assert.match(source, /user\?\.id == null \|\| user\.tenant_id == null/);
});

test("job details handles loading, missing jobs, and API failures", () => {
  assert.match(source, /LoadingState/);
  assert.match(source, /ErrorState/);
  assert.match(source, /Job details unavailable/);
  assert.match(source, /Job not found/);
  assert.match(source, /onRetry=\{\(\) => void loadJob\(\)\}/);
});

test("job details prevents invalid actions after the acceptance deadline", () => {
  assert.match(source, /acceptanceRemainingSeconds/);
  assert.match(source, /acceptanceExpired/);
  assert.match(
    source,
    /action === "accept" && acceptanceExpired/
  );
});

test("job details has an accessible back action", () => {
  assert.match(source, /accessibilityLabel="Go back"/);
  assert.match(source, /onPress=\{\(\) => router\.back\(\)\}/);
});