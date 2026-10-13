
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { submitJobExpense } from "../../../../src/api/expenses";
import { getApiErrorMessage } from "../../../../src/api/apiError";

export default function JobExpenseScreen() {
  const router = useRouter();
  const { jobId } = useLocalSearchParams<{ jobId: string }>();

  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    const parsedAmount = Number(amount);

    if (!jobId) {
      setError("The job ID is missing.");
      return;
    }

    if (!amount.trim() || !Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      setError("Enter a valid expense amount greater than zero.");
      return;
    }

    if (!category.trim()) {
      setError("Enter an expense category.");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      await submitJobExpense(jobId, {
        amount: parsedAmount,
        currency: "INR",
        category: category.trim(),
        description: description.trim() || undefined
      });

      Alert.alert(
        "Expense submitted",
        "Your expense was submitted successfully.",
        [{ text: "OK", onPress: () => router.back() }]
      );
    } catch (submitError: unknown) {
      setError(
        getApiErrorMessage(
          submitError,
          "Unable to submit this expense. Please try again."
        )
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.keyboard}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
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
          <Text style={styles.backText}>‹  Back to job</Text>
        </Pressable>

        <Text style={styles.title}>Submit Expense</Text>
        <Text style={styles.subtitle}>
          Job ID: {jobId || "Unavailable"}
        </Text>

        <View style={styles.card}>
          <Text style={styles.label}>Amount (INR) *</Text>
          <TextInput
            value={amount}
            onChangeText={setAmount}
            placeholder="0.00"
            placeholderTextColor="#94A3B8"
            keyboardType="decimal-pad"
            editable={!isSubmitting}
            accessibilityLabel="Expense amount in Indian rupees"
            style={styles.input}
          />

          <Text style={styles.label}>Category *</Text>
          <TextInput
            value={category}
            onChangeText={setCategory}
            placeholder="Travel, materials, parking..."
            placeholderTextColor="#94A3B8"
            autoCapitalize="sentences"
            editable={!isSubmitting}
            accessibilityLabel="Expense category"
            style={styles.input}
          />

          <Text style={styles.label}>Description (optional)</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            placeholder="Add details about this expense"
            placeholderTextColor="#94A3B8"
            multiline
            textAlignVertical="top"
            editable={!isSubmitting}
            accessibilityLabel="Expense description"
            style={[styles.input, styles.textArea]}
          />

          {error ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {error}
            </Text>
          ) : null}

          <Pressable
            accessibilityRole="button"
            disabled={isSubmitting}
            onPress={() => void handleSubmit()}
            style={({ pressed }) => [
              styles.submitButton,
              pressed && styles.pressed,
              isSubmitting && styles.disabled
            ]}
          >
            {isSubmitting ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.submitText}>Submit Expense</Text>
            )}
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboard: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  screen: {
    flex: 1
  },
  content: {
    padding: 20,
    paddingTop: 40,
    paddingBottom: 36
  },
  backButton: {
    alignSelf: "flex-start",
    paddingVertical: 10,
    marginBottom: 16
  },
  backText: {
    color: "#1D4ED8",
    fontSize: 15,
    fontWeight: "600"
  },
  title: {
    color: "#0F172A",
    fontSize: 27,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    marginTop: 7,
    marginBottom: 24
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E2E8F0",
    borderWidth: 1,
    borderRadius: 14,
    padding: 18
  },
  label: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "600",
    marginTop: 14,
    marginBottom: 8
  },
  input: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5E1",
    borderWidth: 1,
    borderRadius: 9,
    color: "#0F172A",
    fontSize: 15,
    minHeight: 49,
    paddingHorizontal: 12
  },
  textArea: {
    minHeight: 110,
    paddingTop: 12
  },
  error: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 14
  },
  submitButton: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1D4ED8",
    borderRadius: 10,
    minHeight: 51,
    marginTop: 24,
    paddingHorizontal: 16
  },
  pressed: {
    backgroundColor: "#1E40AF"
  },
  disabled: {
    opacity: 0.6
  },
  submitText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  }
});
