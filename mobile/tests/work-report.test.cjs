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
  "[jobId]",
  "completion.tsx"
);

const source = fs.readFileSync(screenPath, "utf8");

test("work report screen exposes all structured report fields", () => {
  assert.ok(
    source.includes('accessibilityLabel="Work report summary"')
  );
  assert.ok(
    source.includes('accessibilityLabel="Parts used"')
  );
  assert.ok(
    source.includes(
      'accessibilityLabel="Work duration in minutes"'
    )
  );

  assert.ok(source.includes("setPartsUsedText"));
  assert.ok(source.includes("setDurationMinutes"));
});

test("work report requires a non-empty summary", () => {
  assert.ok(
    source.includes("const reportSummary = notes.trim();")
  );
  assert.ok(source.includes("if (!reportSummary)"));
  assert.ok(
    source.includes(
      "Enter a work summary before completing the job."
    )
  );
});

test("work report validates summary length and plain text", () => {
  assert.ok(source.includes("reportSummary.length > 5000"));
  assert.ok(
    source.includes(
      "The work summary cannot exceed 5000 characters."
    )
  );
  assert.ok(
    source.includes(
      "The work summary must contain plain text, not markup tags."
    )
  );
});

test("parts used are split into individual items and validated", () => {
  assert.ok(
    source.includes("const partsUsed = partsUsedText")
  );
  assert.ok(source.includes(".split(/\\r?\\n/)"));
  assert.ok(source.includes(".filter(Boolean)"));
  assert.ok(
    source.includes("const invalidPart = partsUsed.find(")
  );
  assert.ok(source.includes("part.length > 200"));
  assert.ok(
    source.includes(
      "Each part used must be 200 characters or fewer."
    )
  );
});

test("work duration accepts only a valid non-negative whole number", () => {
  assert.ok(
    source.includes("const trimmedDuration = durationMinutes.trim();")
  );
  assert.ok(
    source.includes("if (!/^\\d+$/.test(trimmedDuration))")
  );
  assert.ok(source.includes("Number.isSafeInteger(parsedDuration)"));
  assert.ok(
    source.includes(
      "Enter a valid non-negative work duration."
    )
  );
  assert.ok(
    source.includes("reportDurationMinutes = parsedDuration;")
  );
});

test("structured work report uses the existing job closure endpoint", () => {
  assert.ok(
    source.includes("`/jobs/${numericJobId}/close`")
  );
  assert.ok(source.includes("work_summary: reportSummary"));
  assert.ok(source.includes("work_report: {"));
  assert.ok(source.includes("summary: reportSummary"));
  assert.ok(source.includes("parts_used: partsUsed"));
  assert.ok(
    source.includes("{ duration_minutes: reportDurationMinutes }")
  );
  assert.ok(source.includes("before_images: beforeImages"));
  assert.ok(source.includes("after_images: afterImages"));
});

test("completion failures are logged and displayed safely", () => {
  assert.ok(
    source.includes('"completion_photo.job_submission_failed"')
  );
  assert.ok(source.includes("getApiErrorMessage("));
  assert.ok(source.includes("setError("));
});

test("completion preserves uploaded-photo retry behavior", () => {
  assert.ok(
    source.includes("uploadCompletionPhoto("),
    "Photos must use the existing upload service."
  );

  assert.ok(
    source.includes("if (photo.document)"),
    "Previously uploaded photos must be skipped during retry."
  );

  assert.ok(
    source.includes("continue;"),
    "The upload loop must skip photos that already have uploaded documents."
  );

  assert.ok(
    source.includes("document: uploadedDocument"),
    "Successful uploads must retain their document references."
  );

  assert.ok(
    source.includes("uploadError: message"),
    "Upload failures must preserve an error message for retry."
  );

  assert.ok(
    source.includes("setPhotos([...workingPhotos])"),
    "Updated photo upload state must be retained after an upload failure."
  );
});