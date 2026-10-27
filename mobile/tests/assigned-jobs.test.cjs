const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

const jobsScreenPath = path.join(
  root,
  "app",
  "(app)",
  "jobs.tsx"
);

const source = fs.readFileSync(jobsScreenPath, "utf8");

test("assigned jobs screen uses the existing technician jobs API", () => {
  assert.match(source, /getTechnicianJobs/);
  assert.match(source, /normalizeJobs\(response\)/);
  assert.match(
    source,
    /const serverJobs = normalizeJobs\(response\);\s*setJobs\(serverJobs\)/
  );
});

test("assigned job cards display status and priority", () => {
  assert.match(source, /item\.status/);
  assert.match(source, /item\.priority/);
  assert.match(source, /formatStatus\(item\.status\)/);
  assert.match(source, /item\.priority\.toUpperCase\(\)/);
});

test("assigned job cards display schedule and customer information", () => {
  assert.match(source, /item\.scheduled_at/);
  assert.match(source, /formatSchedule\(item\.scheduled_at\)/);
  assert.match(source, /item\.customer_name/);
  assert.match(source, /item\.address/);
});

test("job cards navigate to the selected job details", () => {
  assert.match(
    source,
    /pathname:\s*["']\/\(app\)\/jobs\/\[jobId\]["']/
  );

  assert.match(
    source,
    /params:\s*\{\s*jobId:\s*String\(item\.id\)\s*\}/
  );
});

test("assigned jobs screen provides loading and error states", () => {
  assert.match(source, /LoadingState/);
  assert.match(source, /ErrorState/);
  assert.match(source, /Couldn't load jobs/);
  assert.match(source, /onRetry=\{\(\) => void loadJobs\(\)\}/);
});

test("assigned jobs screen provides an empty state and refresh", () => {
  assert.match(source, /No jobs assigned/);
  assert.match(source, /Newly assigned jobs will appear here/);
  assert.match(source, /RefreshControl/);
  assert.match(source, /loadJobs\(true\)/);
});

test("assigned jobs screen supports status filters and search", () => {
  assert.match(source, /activeFilter/);
  assert.match(source, /EN_ROUTE/);
  assert.match(source, /IN_PROGRESS/);
  assert.match(source, /COMPLETED/);
  assert.match(source, /searchQuery/);
  assert.match(source, /matchesFilter/);
  assert.match(source, /searchableText/);
});