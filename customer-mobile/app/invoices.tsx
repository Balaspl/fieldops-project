import { useCallback, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import {
  router,
  useFocusEffect,
  useLocalSearchParams,
} from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import {
  Card,
  EmptyState,
  ErrorState,
  Header,
  LoadingView,
  Screen,
  StatusBadge,
  sharedStyles,
} from "../src/components/ui";
import type { CustomerInvoice, PaymentHistoryItem, PaymentStatus } from "../src/types/api";
import { formatDate, formatMoney } from "../src/utils/format";
import { colors } from "../src/theme";

export default function CustomerInvoicesScreen() {
  const params = useLocalSearchParams<{ jobId?: string | string[] }>();

  const rawJobId = Array.isArray(params.jobId)
    ? params.jobId[0]
    : params.jobId;

  const selectedJobId = rawJobId ? Number(rawJobId) : null;
  const hasJobFilter = rawJobId !== undefined && rawJobId !== "";

  const validSelectedJobId =
    selectedJobId !== null &&
    Number.isSafeInteger(selectedJobId) &&
    selectedJobId > 0;
  const [invoices, setInvoices] = useState<CustomerInvoice[]>([]);
  const [payments, setPayments] = useState<PaymentHistoryItem[]>([]);
  const [details, setDetails] = useState<Record<number, CustomerInvoice>>({});
  const [status, setStatus] = useState<Record<number, PaymentStatus>>({});
  const [busyJob, setBusyJob] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async (pull = false) => {
    if (pull) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError("");

    try {
      const [allInvoices, allPayments] = await Promise.all([
        customerApi.invoices(),
        customerApi.paymentHistory(),
      ]);

      const filteredInvoices = !hasJobFilter
        ? allInvoices
        : validSelectedJobId
          ? allInvoices.filter(
              (invoice) => invoice.job_id === selectedJobId,
            )
          : [];

      const filteredPayments = !hasJobFilter
        ? allPayments
        : validSelectedJobId
          ? allPayments.filter(
              (payment) => payment.job_id === selectedJobId,
            )
          : [];

      setInvoices(filteredInvoices);
      setPayments(filteredPayments);
    } catch (e) {
      setError(
        getApiErrorMessage(e, "Could not load invoices."),
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [hasJobFilter, validSelectedJobId, selectedJobId]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const toggleDetails = async (invoice: CustomerInvoice) => {
    const id = invoice.job_id;
    if (details[id]) { setDetails((old) => { const next = { ...old }; delete next[id]; return next; }); return; }
    setBusyJob(id);
    try {
      const [full, pay] = await Promise.all([customerApi.invoice(id), customerApi.paymentStatus(id).catch(() => null)]);
      setDetails((old) => ({ ...old, [id]: full }));
      if (pay) setStatus((old) => ({ ...old, [id]: pay }));
    } catch (e) { setError(getApiErrorMessage(e, "Could not load invoice details.")); }
    finally { setBusyJob(0); }
  };
  const paymentFor = (jobId: number) => payments.find((item) => item.job_id === jobId)?.payment_status || status[jobId]?.status || "UNAVAILABLE";

  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
    <ScrollView contentContainerStyle={{ padding: 18, gap: 18, paddingBottom: 30 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.brand} />} showsVerticalScrollIndicator={false}>
    <Header
      title={hasJobFilter ? "Invoice details" : "Invoices & payments"}
      subtitle={
        hasJobFilter
          ? `Invoice for Job #${rawJobId}`
          : "View service charges and recorded payment information"
      }
      right={
        <Pressable
          onPress={() => router.back()}
          style={{ padding: 8 }}
        >
          <Ionicons
            name="close"
            color={colors.muted}
            size={22}
          />
        </Pressable>
      }
    />
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <LoadingView message="Loading invoices…" /> : invoices.length === 0 ? <Card><EmptyState title="No invoices available" message="Invoices will appear after a service has generated one." icon="receipt-outline" /></Card> : invoices.map((invoice) => <Card key={`${invoice.job_id}-${invoice.id}`}>
        <View style={sharedStyles.spaceBetween}><View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.text, fontSize: 15, fontWeight: "800" }}>{invoice.service_type || "Service invoice"}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>Invoice {invoice.id} · Job #{invoice.job_id}</Text></View><Text style={{ color: colors.brand, fontWeight: "900", fontSize: 17 }}>{formatMoney(invoice.total_amount)}</Text></View>
        <View style={sharedStyles.spaceBetween}><Text style={{ color: colors.muted, fontSize: 12 }}>Issued {formatDate(invoice.created_at)}</Text><StatusBadge status={paymentFor(invoice.job_id)} /></View>
        <Pressable onPress={() => void toggleDetails(invoice)} style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 9, gap: 7 }}><Ionicons name={details[invoice.job_id] ? "chevron-up" : "receipt-outline"} size={17} color={colors.brandMid} /><Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "800" }}>{busyJob === invoice.job_id ? "Loading details…" : details[invoice.job_id] ? "Hide invoice details" : "View invoice details"}</Text></Pressable>
        {details[invoice.job_id] ? <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, gap: 10 }}>
          <View style={sharedStyles.spaceBetween}><Text style={sharedStyles.body}>Labor</Text><Text style={sharedStyles.strong}>{formatMoney(details[invoice.job_id].labour_cost)}</Text></View>
          <View style={sharedStyles.spaceBetween}><Text style={sharedStyles.body}>Materials</Text><Text style={sharedStyles.strong}>{formatMoney(details[invoice.job_id].material_cost)}</Text></View>
          <View style={sharedStyles.spaceBetween}><Text style={sharedStyles.body}>Subtotal</Text><Text style={sharedStyles.strong}>{formatMoney(details[invoice.job_id].subtotal)}</Text></View>
          <View style={sharedStyles.spaceBetween}><Text style={sharedStyles.body}>GST ({details[invoice.job_id].gst_rate}%)</Text><Text style={sharedStyles.strong}>{formatMoney(details[invoice.job_id].gst_amount)}</Text></View>
          <View style={[sharedStyles.spaceBetween, { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10 }]}><Text style={{ color: colors.text, fontWeight: "900" }}>Total</Text><Text style={sharedStyles.money}>{formatMoney(details[invoice.job_id].total_amount)}</Text></View>
          {details[invoice.job_id].work_summary ? <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>{details[invoice.job_id].work_summary}</Text> : null}
          {details[invoice.job_id].organization_name ? <Text style={{ color: colors.muted, fontSize: 12 }}>Service provider: {details[invoice.job_id].organization_name}</Text> : null}
        </View> : null}
      </Card>)}
    </ScrollView>
  </Screen>;
}
