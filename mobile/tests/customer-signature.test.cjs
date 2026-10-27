const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

const signatureScreenPath = path.join(
  root,
  "app",
  "(app)",
  "jobs",
  "[jobId]",
  "customer-signature.tsx"
);

const signatureApiPath = path.join(
  root,
  "src",
  "api",
  "customerSignature.ts"
);

const completionScreenPath = path.join(
  root,
  "app",
  "(app)",
  "jobs",
  "[jobId]",
  "completion.tsx"
);

const signatureScreen = fs.readFileSync(
  signatureScreenPath,
  "utf8"
);

const signatureApi = fs.readFileSync(
  signatureApiPath,
  "utf8"
);

const completionScreen = fs.readFileSync(
  completionScreenPath,
  "utf8"
);

test("customer signature screen provides a drawing canvas", () => {
  assert.ok(signatureScreen.includes("SignatureCanvas"));
  assert.ok(signatureScreen.includes("onOK={handleSignatureCaptured}"));
  assert.ok(signatureScreen.includes('clearText="Clear"'));
  assert.ok(signatureScreen.includes('confirmText="Use signature"'));
  assert.ok(signatureScreen.includes('imageType="image/png"'));
});

test("customer signature requires a captured signature before saving", () => {
  assert.ok(signatureScreen.includes("if (!signatureData)"));
  assert.ok(
    signatureScreen.includes(
      "Ask the customer to sign in the signature box and select Use signature."
    )
  );
  assert.ok(
    signatureScreen.includes("disabled={isSubmitting || !signatureData}")
  );
});

test("customer signature validates its image data", () => {
  assert.ok(signatureScreen.includes("MAX_SIGNATURE_LENGTH"));
  assert.ok(signatureScreen.includes("signature.length > MAX_SIGNATURE_LENGTH"));
  assert.ok(signatureScreen.includes("data:image\\/png;base64"));
  assert.ok(signatureScreen.includes("setSignatureData(signature.trim())"));
});

test("signature API validates the job identifier", () => {
  assert.ok(signatureApi.includes("Number.isSafeInteger(numericJobId)"));
  assert.ok(signatureApi.includes("numericJobId <= 0"));
  assert.ok(signatureApi.includes("A valid job ID is required."));
});

test("signature API validates PNG or JPEG data URLs and size", () => {
  assert.ok(signatureApi.includes("MAX_SIGNATURE_LENGTH"));
  assert.ok(signatureApi.includes("canonicalSignature.length > MAX_SIGNATURE_LENGTH"));
  assert.ok(signatureApi.includes("data:image\\/"));
  assert.ok(signatureApi.includes("signature_data: canonicalSignature"));
});

test("signature uses the existing authenticated API client and endpoint", () => {
  assert.ok(signatureApi.includes('import { apiClient } from "./client";'));
  assert.ok(
    signatureApi.includes(
      "`/jobs/${numericJobId}/customer-signature`"
    )
  );
  assert.ok(
    signatureApi.includes("apiClient.post<CustomerSignatureResponse>(")
  );
});

test("signature API logs outcomes without logging signature content", () => {
  assert.ok(
    signatureApi.includes('"customer_signature.upload_started"')
  );
  assert.ok(
    signatureApi.includes('"customer_signature.upload_succeeded"')
  );
  assert.ok(
    signatureApi.includes('"customer_signature.upload_failed"')
  );
  assert.ok(signatureApi.includes("logError("));
  assert.ok(!signatureApi.includes("logEvent(signatureData"));
  assert.ok(!signatureApi.includes("logEvent(canonicalSignature"));
});

test("signature failure displays an error and preserves retry capability", () => {
  assert.ok(signatureScreen.includes("catch (submissionError: unknown)"));
  assert.ok(signatureScreen.includes("setError(message)"));
  assert.ok(
    signatureScreen.includes("await uploadCustomerSignature(")
  );
});

test("completion submits customer signature with closure and navigates after success", () => {
  const handleCompleteIndex = completionScreen.indexOf(
    "async function handleComplete()"
  );

  const completionRequestIndex = completionScreen.indexOf(
    "`/jobs/${numericJobId}/close`"
  );

  const signatureValidationIndex = completionScreen.indexOf(
    "if (!signatureData.trim())",
    handleCompleteIndex
  );

  const signaturePayloadIndex = completionScreen.indexOf(
    "signature_data: signatureData.trim()"
  );

  const successNavigationIndex = completionScreen.indexOf(
    'router.replace("/(app)/jobs")'
  );

  assert.ok(
    completionRequestIndex >= 0,
    "The existing job-closure endpoint must be used."
  );

  assert.ok(
    signatureValidationIndex > handleCompleteIndex &&
      signatureValidationIndex < completionRequestIndex,
    "The signature must be validated before submitting job completion."
  );

  assert.ok(
    signaturePayloadIndex > completionRequestIndex,
    "The signature must be included in the job-closure request."
  );

  assert.ok(
    successNavigationIndex > completionRequestIndex,
    "Navigate to My Jobs only after the completion request succeeds."
  );

  assert.ok(completionScreen.includes("if (isSignatureStep)"));

  assert.ok(
    completionScreen.includes("async function handleSaveSignature()")
  );

  assert.ok(
    completionScreen.includes("await handleComplete();"),
    "Saving the signature must submit the combined completion request."
  );

  assert.ok(
    !completionScreen.includes("await uploadCustomerSignature("),
    "The completion flow must not upload the signature separately."
  );
});

test("signature screen reports loading and API failure states accessibly", () => {
  assert.ok(signatureScreen.includes("Saving signature..."));
  assert.ok(signatureScreen.includes('accessibilityRole="alert"'));
  assert.ok(
    signatureScreen.includes("Unable to save the customer's signature.")
  );
});