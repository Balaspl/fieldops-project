import { useMemo, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import {
  useLocalSearchParams,
  useRouter
} from "expo-router";

const GST_PERCENT = 5;

function parseMoneyToPaise(value: string): number | null {
  const normalized = value.trim();

  if (!normalized) {
    return 0;
  }

  if (!/^\d+(?:\.\d{1,2})?$/.test(normalized)) {
    return null;
  }

  const amount = Number(normalized);
  const paise = Math.round(amount * 100);

  if (
    !Number.isFinite(amount) ||
    !Number.isSafeInteger(paise) ||
    paise < 0
  ) {
    return null;
  }

  return paise;
}

function formatINR(paise: number): string {
  return (paise / 100).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

export default function JobExpenseScreen() {
  const router = useRouter();

  const { jobId } = useLocalSearchParams<{
    jobId: string;
  }>();

  const [serviceChargeText, setServiceChargeText] =
    useState("");
  const [materialCostText, setMaterialCostText] =
    useState("");
  const [error, setError] = useState<string | null>(null);

  const costs = useMemo(() => {
    const serviceCharge =
      parseMoneyToPaise(serviceChargeText);

    const materialCost =
      parseMoneyToPaise(materialCostText);

    if (
      serviceCharge === null ||
      materialCost === null
    ) {
      return {
        valid: false,
        serviceCharge: 0,
        materialCost: 0,
        subtotal: 0,
        gst: 0,
        total: 0
      };
    }

    const subtotal =
      serviceCharge + materialCost;

    // Calculate GST in paise to avoid floating-point
    // currency rounding errors.
    const gst = Math.round(
      (subtotal * GST_PERCENT) / 100
    );

    return {
      valid: Number.isSafeInteger(subtotal + gst),
      serviceCharge,
      materialCost,
      subtotal,
      gst,
      total: subtotal + gst
    };
  }, [
    serviceChargeText,
    materialCostText
  ]);

  function handleContinue() {
    const numericJobId = Number(
      String(jobId ?? "").trim()
    );

    if (
      !jobId ||
      !Number.isSafeInteger(numericJobId) ||
      numericJobId <= 0
    ) {
      setError(
        "A valid job ID is required. Please reopen the job."
      );
      return;
    }

    if (!costs.valid) {
      setError(
        "Enter valid amounts with no more than two decimal places."
      );
      return;
    }

    setError(null);

    router.replace({
      pathname: "/(app)/jobs/[jobId]/completion",
      params: {
        jobId: String(numericJobId),
        serviceCharge: (
          costs.serviceCharge / 100
        ).toFixed(2),
        materialCost: (
          costs.materialCost / 100
        ).toFixed(2),
        subtotal: (
          costs.subtotal / 100
        ).toFixed(2),
        gst: (
          costs.gst / 100
        ).toFixed(2),
        total: (
          costs.total / 100
        ).toFixed(2)
      }
    });
  }

  return (
    <KeyboardAvoidingView
      style={styles.keyboard}
      behavior={
        Platform.OS === "ios"
          ? "padding"
          : undefined
      }
    >
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Text style={styles.backText}>
            {"‹  "}Back to job
          </Text>
        </Pressable>

        <Text style={styles.title}>
          Job Expenses
        </Text>

        <Text style={styles.subtitle}>
          Enter the service charge and material cost
          for this job.
        </Text>

        <View style={styles.card}>
          <Text style={styles.label}>
            Service Charge (₹)
          </Text>

          <TextInput
            accessibilityLabel="Service charge in rupees"
            value={serviceChargeText}
            onChangeText={(value) => {
              setServiceChargeText(value);
              setError(null);
            }}
            placeholder="0.00"
            placeholderTextColor="#94A3B8"
            keyboardType="decimal-pad"
            editable
            style={styles.input}
          />

          <Text style={styles.label}>
            Material Cost (₹)
          </Text>

          <TextInput
            accessibilityLabel="Material cost in rupees"
            value={materialCostText}
            onChangeText={(value) => {
              setMaterialCostText(value);
              setError(null);
            }}
            placeholder="0.00"
            placeholderTextColor="#94A3B8"
            keyboardType="decimal-pad"
            editable
            style={styles.input}
          />

          <View style={styles.summary}>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>
                SERVICE CHARGE
              </Text>
              <Text style={styles.amount}>
                {formatINR(costs.serviceCharge)}
              </Text>
            </View>

            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>
                MATERIAL COST
              </Text>
              <Text style={styles.amount}>
                {formatINR(costs.materialCost)}
              </Text>
            </View>

            <View style={styles.dashedDivider} />

            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>
                SUBTOTAL
              </Text>
              <Text style={styles.amount}>
                {formatINR(costs.subtotal)}
              </Text>
            </View>

            <View style={styles.summaryRow}>
              <Text style={styles.summaryLabel}>
                GST ({GST_PERCENT}%)
              </Text>
              <Text style={styles.amount}>
                {formatINR(costs.gst)}
              </Text>
            </View>

            <View style={styles.solidDivider} />

            <View style={styles.summaryRow}>
              <Text style={styles.totalLabel}>
                TOTAL
              </Text>
              <Text style={styles.totalAmount}>
                {formatINR(costs.total)}
              </Text>
            </View>
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
            accessibilityLabel="Continue to job completion"
            onPress={handleContinue}
            style={({ pressed }) => [
              styles.primaryButton,
              pressed && styles.pressed
            ]}
          >
            <Text style={styles.primaryButtonText}>
              Continue to Completion
            </Text>
          </Pressable>

          <Text style={styles.notice}>
            The displayed total is a preview. The
            backend must validate the submitted amounts
            and calculate the authoritative GST and
            invoice total.
          </Text>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboard: {
    flex: 1,
    backgroundColor: "#F4F8F6"
  },
  screen: {
    flex: 1
  },
  content: {
    padding: 20,
    paddingTop: 28,
    paddingBottom: 36
  },
  backButton: {
    alignSelf: "flex-start",
    paddingVertical: 10,
    marginBottom: 16
  },
  backText: {
    color: "#00664F",
    fontSize: 15,
    fontWeight: "600"
  },
  title: {
    color: "#073B30",
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 7,
    marginBottom: 22
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#DDE8E2",
    borderWidth: 1,
    borderRadius: 14,
    padding: 16
  },
  label: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "600",
    marginTop: 12,
    marginBottom: 8
  },
  input: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5E1",
    borderWidth: 1,
    borderRadius: 9,
    color: "#0F172A",
    fontSize: 16,
    minHeight: 48,
    paddingHorizontal: 12
  },
  summary: {
    backgroundColor: "#FAFCFB",
    borderColor: "#DCE6E0",
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    marginTop: 24
  },
  summaryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    minHeight: 30
  },
  summaryLabel: {
    color: "#7B8DA7",
    fontSize: 10,
    fontWeight: "600",
    letterSpacing: 0.7
  },
  amount: {
    color: "#111827",
    fontSize: 12,
    fontWeight: "600",
    fontVariant: ["tabular-nums"]
  },
  dashedDivider: {
    borderBottomWidth: 1,
    borderStyle: "dashed",
    borderColor: "#CBD5E1",
    marginVertical: 7
  },
  solidDivider: {
    borderBottomWidth: 1,
    borderColor: "#D8E1DC",
    marginVertical: 8
  },
  totalLabel: {
    color: "#17633A",
    fontSize: 12,
    fontWeight: "800",
    letterSpacing: 0.5
  },
  totalAmount: {
    color: "#17633A",
    fontSize: 16,
    fontWeight: "800",
    fontVariant: ["tabular-nums"]
  },
  error: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 14
  },
  primaryButton: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#00664F",
    borderRadius: 10,
    minHeight: 52,
    marginTop: 22,
    paddingHorizontal: 16
  },
  pressed: {
    backgroundColor: "#004D3B"
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  },
  notice: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 14
  }
});