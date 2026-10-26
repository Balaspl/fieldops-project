import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View
} from "react-native";
import SignatureCanvas from "react-native-signature-canvas";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  uploadCustomerSignature
} from "../../../../src/api/customerSignature";
import {
  logError,
  logEvent
} from "../../../../src/observability/logger";

const MAX_SIGNATURE_LENGTH = 2_000_000;

export default function CustomerSignatureScreen() {
  const router = useRouter();

  const params = useLocalSearchParams<{
    jobId?: string | string[];
  }>();

  const jobId = Array.isArray(params.jobId)
    ? params.jobId[0]
    : params.jobId;

  const [signatureData, setSignatureData] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleSignatureCaptured(signature: string) {
    if (
      typeof signature !== "string" ||
      !signature.trim()
    ) {
      setSignatureData("");
      setError("Please capture the customer's signature.");
      return;
    }

    if (
      signature.length > MAX_SIGNATURE_LENGTH ||
      !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(
        signature.trim()
      )
    ) {
      setSignatureData("");
      setError(
        "The signature image is invalid or too large. Please clear it and sign again."
      );
      return;
    }

    setSignatureData(signature.trim());
    setError(null);

    logEvent("customer_signature.captured", {});
  }

  async function handleSubmitSignature() {
    const numericJobId = Number(String(jobId ?? "").trim());

    if (
      !jobId ||
      !Number.isSafeInteger(numericJobId) ||
      numericJobId <= 0
    ) {
      setError("A valid job ID is required. Open the job again.");
      return;
    }

    if (!signatureData) {
      setError(
        "Ask the customer to sign in the signature box and select Use signature."
      );
      return;
    }

    if (isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await uploadCustomerSignature(
        numericJobId,
        signatureData
      );

      logEvent("customer_signature.saved", {});

      setSignatureData("");
      router.replace("/(app)/jobs");
    } catch (submissionError: unknown) {
      const message =
        submissionError instanceof Error
          ? submissionError.message
          : "Unable to save the customer's signature. Please try again.";

      // A retry may occur after the server saved the signature
      // but its response did not reach the app.
      if (
        message ===
        "Customer signature already exists for this job"
      ) {
        logEvent("customer_signature.already_saved", {});

        setSignatureData("");
        router.replace("/(app)/jobs");
        return;
      }

      logError(
        "customer_signature.screen_submission_failed",
        submissionError
      );

      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable
        accessibilityRole="button"
        disabled={isSubmitting}
        onPress={() => router.replace("/(app)/jobs")}
        style={styles.backButton}
      >
        <Text style={styles.backText}>
          Back to My Jobs
        </Text>
      </Pressable>

      <Text style={styles.title}>
        Customer Signature
      </Text>

      <Text style={styles.subtitle}>
        Ask the customer to review the completed work and sign
        below to acknowledge it. Only save the signature with
        the customer's consent.
      </Text>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>
          Sign below
        </Text>

        <Text style={styles.helperText}>
          Use a finger or stylus. Select "Use signature" inside
          the canvas when the customer is satisfied.
        </Text>

        <View style={styles.signatureContainer}>
          <SignatureCanvas
            onOK={handleSignatureCaptured}
            onEmpty={() => {
              setSignatureData("");
              setError(
                "The signature is empty. Please ask the customer to sign."
              );
            }}
            onClear={() => {
              setSignatureData("");
              setError(null);
            }}
            onBegin={() => {
              setSignatureData("");
              setError(null);
            }}
            onError={() => {
              setSignatureData("");
              setError(
                "The signature pad encountered a problem. Please try again."
              );
            }}
            descriptionText="Customer signature"
            clearText="Clear"
            confirmText="Use signature"
            imageType="image/png"
            autoClear={false}
            trimWhitespace
            backgroundColor="#FFFFFF"
            penColor="#111827"
            style={styles.signatureCanvas}
            webviewProps={{
              allowFileAccess: false,
              allowFileAccessFromFileURLs: false,
              mixedContentMode: "never"
            }}
          />
        </View>

        {signatureData ? (
          <Text style={styles.signatureReady}>
            Signature captured. Review it before saving.
          </Text>
        ) : (
          <Text style={styles.helperText}>
            No signature captured yet.
          </Text>
        )}
      </View>

      {error ? (
        <Text
          accessibilityRole="alert"
          style={styles.error}
        >
          {error}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Submit customer signature"
        disabled={isSubmitting || !signatureData}
        onPress={() => void handleSubmitSignature()}
        style={[
          styles.primaryButton,
          (isSubmitting || !signatureData) &&
            styles.disabled
        ]}
      >
        {isSubmitting ? (
          <View style={styles.inlineStatus}>
            <ActivityIndicator color="#FFFFFF" />
            <Text style={styles.primaryButtonText}>
              Saving signature...
            </Text>
          </View>
        ) : (
          <Text style={styles.primaryButtonText}>
            Save Customer Signature
          </Text>
        )}
      </Pressable>

      <Text style={styles.notice}>
        The signature is submitted through the authenticated
        FieldOps API. The server verifies technician permissions,
        job assignment, tenant access and job-completion status.
        Signature data is not written to application logs.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  content: {
    padding: 20,
    paddingTop: 42,
    paddingBottom: 36
  },
  backButton: {
    alignSelf: "flex-start",
    paddingVertical: 10,
    marginBottom: 20
  },
  backText: {
    color: "#217346",
    fontSize: 14,
    fontWeight: "700"
  },
  title: {
    color: "#0F172A",
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 8,
    marginBottom: 24
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E2E8F0",
    borderWidth: 1,
    borderRadius: 12,
    padding: 16
  },
  sectionTitle: {
    color: "#0F172A",
    fontSize: 17,
    fontWeight: "700",
    marginBottom: 10
  },
  helperText: {
    color: "#64748B",
    fontSize: 13,
    lineHeight: 19
  },
  signatureContainer: {
    height: 290,
    marginTop: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    borderRadius: 10,
    overflow: "hidden",
    backgroundColor: "#FFFFFF"
  },
  signatureCanvas: {
    flex: 1
  },
  signatureReady: {
    color: "#17633A",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 8
  },
  primaryButton: {
    minHeight: 54,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#217346",
    borderRadius: 10,
    paddingHorizontal: 16,
    marginTop: 18
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center"
  },
  inlineStatus: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  disabled: {
    opacity: 0.5
  },
  error: {
    color: "#B91C1C",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 12
  },
  notice: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 16
  }
});