import { useCallback, useMemo, useState } from "react";
import {
  Alert,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { customerApi } from "../../src/api/customer";
import { getApiErrorMessage } from "../../src/api/client";
import { AppButton, ErrorState, LoadingView, Screen } from "../../src/components/ui";
import type {
  CustomerFeedback,
  CustomerInvoice,
  CustomerJob,
  PaymentStatus,
  ServiceRequest,
} from "../../src/types/api";
import {
  canCancelRequest,
  canEditRequest,
  formatDate,
  formatDateTime,
  formatMoney,
  normalizedStatus,
} from "../../src/utils/format";
import { colors } from "../../src/theme";

type CustomerJobDetails = CustomerJob & {
  accepted_at?: string | null;
  assigned_at?: string | null;
  en_route_at?: string | null;
  preferred_service_date?: string | null;
  preferred_service_time?: string | null;
  issue_description?: string | null;
  organization_name?: string | null;
};

const TERMINAL_STATUSES = ["COMPLETED", "CLOSED", "CANCELLED", "CANCELED"];
const ACCEPTED_OR_LATER = [
  "ACCEPTED",
  "EN_ROUTE",
  "ENROUTE",
  "ON_SITE",
  "ONSITE",
  "IN_PROGRESS",
  "COMPLETED",
  "CLOSED",
];

function initials(name?: string | null): string {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return parts.length > 1
    ? `${parts[0][0]}${parts[1][0]}`.toUpperCase()
    : (parts[0]?.slice(0, 2) || "TE").toUpperCase();
}

function displayStatus(value?: string | null): string {
  const status = normalizedStatus(value);
  const labels: Record<string, string> = {
    CREATED: "BOOKED",
    PENDING: "PENDING",
    UNASSIGNED: "UNASSIGNED",
    ASSIGNED: "ASSIGNED",
    ACCEPTED: "ACCEPTED",
    EN_ROUTE: "EN ROUTE",
    ENROUTE: "EN ROUTE",
    ON_SITE: "ON SITE",
    ONSITE: "ON SITE",
    IN_PROGRESS: "WORK IN PROGRESS",
    COMPLETED: "COMPLETED",
    CLOSED: "COMPLETED",
    CANCELLED: "CANCELLED",
    CANCELED: "CANCELLED",
    REJECTED_BY_TECHNICIAN: "CANCELLED",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function paymentLabel(value?: string | null): string {
  const status = String(value ?? "UNAVAILABLE").trim().toUpperCase();
  if (["SUCCESSFUL", "SUCCEEDED", "PAID", "COMPLETED"].includes(status)) return "PAID";
  if (status === "PENDING") return "PENDING";
  if (status === "FAILED") return "FAILED";
  return "UNAVAILABLE";
}

function elapsedDuration(start?: string | null, end?: string | null): string {
  if (!start || !end) return "Not recorded";
  const startTime = new Date(start).getTime();
  const endTime = new Date(end).getTime();
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) {
    return "Not recorded";
  }
  const totalMinutes = Math.floor((endTime - startTime) / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes} min`;
  if (minutes === 0) return `${hours} hr${hours === 1 ? "" : "s"}`;
  return `${hours} hr${hours === 1 ? "" : "s"} ${minutes} min`;
}

function SectionHeading({ icon, title }: { icon: keyof typeof Ionicons.glyphMap; title: string }) {
  return (
    <View style={styles.sectionHeading}>
      <View style={styles.sectionIcon}>
        <Ionicons name={icon} size={19} color={colors.brandMid} />
      </View>
      <Text style={styles.sectionTitle}>{title}</Text>
    </View>
  );
}

function DetailLine({
  icon,
  label,
  value,
  last = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value?: string | null;
  last?: boolean;
}) {
  return (
    <View style={[styles.detailLine, !last && styles.detailLineBorder]}>
      <View style={styles.detailIcon}>
        <Ionicons name={icon} size={18} color={colors.brandMid} />
      </View>
      <View style={styles.detailTextWrap}>
        <Text style={styles.detailLabel}>{label}</Text>
        <Text style={styles.detailValue}>{value?.trim() || "Not recorded"}</Text>
      </View>
    </View>
  );
}

function TimelineItem({
  icon,
  title,
  timestamp,
  complete,
  last = false,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  timestamp?: string | null;
  complete: boolean;
  last?: boolean;
}) {
  return (
    <View style={styles.timelineRow}>
      <View style={styles.timelineTrack}>
        <View style={[styles.timelineDot, complete ? styles.timelineDotComplete : styles.timelineDotPending]}>
          <Ionicons
            name={complete ? "checkmark" : icon}
            size={14}
            color={complete ? "#FFFFFF" : "#8D9C94"}
          />
        </View>
        {!last ? <View style={[styles.timelineLine, complete && styles.timelineLineComplete]} /> : null}
      </View>
      <View style={styles.timelineContent}>
        <Text style={[styles.timelineTitle, !complete && styles.timelineTitlePending]}>{title}</Text>
        <Text style={styles.timelineTime}>
          {timestamp ? formatDateTime(timestamp) : complete ? "Time not recorded" : "Pending"}
        </Text>
      </View>
    </View>
  );
}

function InvoiceAmountRow({
  label,
  value,
  strong = false,
}: {
  label: string;
  value: string;
  strong?: boolean;
}) {
  return (
    <View style={[styles.invoiceAmountRow, strong && styles.invoiceTotalRow]}>
      <Text style={[styles.invoiceAmountLabel, strong && styles.invoiceTotalLabel]}>{label}</Text>
      <Text style={[styles.invoiceAmountValue, strong && styles.invoiceTotalValue]}>{value}</Text>
    </View>
  );
}

export default function ServiceRequestDetailScreen() {
  const params = useLocalSearchParams<{ requestId: string }>();
  const requestId = Number(params.requestId);

  const [request, setRequest] = useState<ServiceRequest | null>(null);
  const [job, setJob] = useState<CustomerJob | null>(null);
  const [invoice, setInvoice] = useState<CustomerInvoice | null>(null);
  const [payment, setPayment] = useState<PaymentStatus | null>(null);
  const [feedback, setFeedback] = useState<CustomerFeedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (pull = false) => {
    if (pull) setRefreshing(true);
    else setLoading(true);
    setError("");

    try {
      if (!Number.isSafeInteger(requestId) || requestId <= 0) {
        throw new Error("This service request ID is invalid.");
      }

      const loadedRequest = await customerApi.request(requestId);
      setRequest(loadedRequest);

      const linkedJobId = loadedRequest.linked_job_id ?? loadedRequest.created_job?.id;
      if (!linkedJobId) {
        setJob(null);
        setInvoice(null);
        setPayment(null);
        setFeedback(null);
        return;
      }

      const [jobResult, invoiceResult, paymentResult, feedbackResult] = await Promise.all([
        customerApi.job(linkedJobId).catch(() => null),
        customerApi.invoice(linkedJobId).catch(() => null),
        customerApi.paymentStatus(linkedJobId).catch(() => null),
        customerApi.feedback(linkedJobId).catch(() => null),
      ]);

      setJob(jobResult);
      setInvoice(invoiceResult);
      setPayment(paymentResult);
      setFeedback(feedbackResult);
    } catch (e) {
      setError(getApiErrorMessage(e, "Unable to load job and invoice details."));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [requestId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const cancel = useCallback(() => {
    Alert.alert(
      "Cancel service request?",
      "This request can only be cancelled while it remains eligible. The change will be sent to FieldOps.",
      [
        { text: "Keep request", style: "cancel" },
        {
          text: "Cancel request",
          style: "destructive",
          onPress: () => {
            setBusy(true);
            void customerApi.cancelRequest(requestId, "Cancelled by customer")
              .then(() => load())
              .catch((e) => setError(getApiErrorMessage(e, "Could not cancel this request.")))
              .finally(() => setBusy(false));
          },
        },
      ],
    );
  }, [load, requestId]);

  const handleShareReceipt = useCallback(async () => {
    if (!invoice || !request) return;
    const linkedJobId = invoice.job_id;
    const paymentText = paymentLabel(payment?.status);
    const message = [
      "FieldOps — Invoice Receipt",
      `Invoice: ${invoice.id}`,
      `Job: #${linkedJobId}`,
      `Service: ${invoice.service_type || request.service_type || "Service"}`,
      `Address: ${invoice.location || request.location || "Not recorded"}`,
      `Work summary: ${invoice.work_summary || "Not recorded"}`,
      `Labour: ${formatMoney(invoice.labour_cost)}`,
      `Materials: ${formatMoney(invoice.material_cost)}`,
      `Subtotal: ${formatMoney(invoice.subtotal)}`,
      `GST (${invoice.gst_rate}%): ${formatMoney(invoice.gst_amount)}`,
      `Total: ${formatMoney(invoice.total_amount)}`,
      `Payment status: ${paymentText}`,
    ].join("\n");
    try {
      await Share.share({ title: `FieldOps Invoice ${invoice.id}`, message });
    } catch {
      Alert.alert("Unable to share receipt", "Your device could not open the share menu.");
    }
  }, [invoice, payment?.status, request]);

  const resolvedJobId = request?.linked_job_id ?? request?.created_job?.id ?? job?.id;
  const jobDetails = job as CustomerJobDetails | null;
  const status = job?.status ?? request?.status;
  const normalizedJobStatus = normalizedStatus(status);
  const isCompleted = ["COMPLETED", "CLOSED"].includes(normalizedJobStatus);
  const isCancelled = ["CANCELLED", "CANCELED", "REJECTED_BY_TECHNICIAN"].includes(normalizedJobStatus);
  const technicianName =
    job?.assigned_technician_name ||
    request?.assigned_technician_name ||
    null;

  const technicianPhone =
    job?.assigned_technician_phone ||
    request?.assigned_technician_phone ||
    null;

  const organizationName =
    jobDetails?.organization_name?.trim() ||
    invoice?.organization_name?.trim() ||
    null;
  const resolvedPaymentStatus = paymentLabel(payment?.status);
  const workDuration = elapsedDuration(
  job?.work_started_at || job?.on_site_at,
  job?.completed_at || invoice?.completed_at,
);

  const timeline = useMemo(() => {
    const jobStatus = normalizedStatus(job?.status);

    const accepted = ACCEPTED_OR_LATER.includes(jobStatus);

    const enRouteStatuses = [
      "EN_ROUTE",
      "ENROUTE",
      "ON_SITE",
      "ONSITE",
      "IN_PROGRESS",
      "COMPLETED",
      "CLOSED",
    ];

    const onTheWay =
      Boolean(jobDetails?.en_route_at) ||
      enRouteStatuses.includes(jobStatus);

    const arrivedOrStarted =
      Boolean(job?.on_site_at || job?.work_started_at) ||
      ["ON_SITE", "ONSITE", "IN_PROGRESS", "COMPLETED", "CLOSED"].includes(
        jobStatus,
      );

    const completed =
      Boolean(job?.completed_at) ||
      ["COMPLETED", "CLOSED"].includes(jobStatus);

    return [
      {
        icon: "document-text-outline" as const,
        title: "Request created",
        timestamp: request?.created_at,
        complete: Boolean(request?.created_at),
      },
      {
        icon: "checkmark-circle-outline" as const,
        title: "Technician accepted",
        timestamp: jobDetails?.accepted_at,
        complete: accepted,
      },
      {
        icon: "navigate-outline" as const,
        title: "On the way",
        timestamp: jobDetails?.en_route_at,
        complete: onTheWay,
      },
      {
        icon: "location-outline" as const,
        title: "Arrived on site / Work started",
        timestamp: job?.on_site_at ?? job?.work_started_at,
        complete: arrivedOrStarted,
      },
      {
        icon: "checkmark-circle-outline" as const,
        title: "Job completed",
        timestamp: job?.completed_at,
        complete: completed,
      },
    ];
  }, [
    job?.completed_at,
    job?.on_site_at,
    job?.status,
    job?.work_started_at,
    jobDetails?.accepted_at,
    jobDetails?.en_route_at,
    request?.created_at,
  ]);

  if (loading) {
    return <Screen><LoadingView message="Loading job and invoice details…" /></Screen>;
  }

  if (!request) {
    return (
      <Screen>
        <ErrorState message={error || "This service request could not be found."} onRetry={() => void load()} />
        <AppButton title="Back to requests" onPress={() => router.replace("/(tabs)/requests")} kind="secondary" />
      </Screen>
    );
  }

  return (
    <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0, gap: 0 }}>
      <View style={styles.page}>
        <View style={styles.header}>
          <Pressable onPress={() => router.back()} accessibilityRole="button" accessibilityLabel="Go back" style={styles.backButton}>
            <Ionicons name="arrow-back" size={22} color={colors.brand} />
          </Pressable>
          <View style={styles.headerText}>
            <Text style={styles.pageTitle}>Job & Invoice Details</Text>
            <Text style={styles.pageSubtitle}>
              {resolvedJobId ? `Job #${resolvedJobId} · ` : ""}{request.request_number}
            </Text>
          </View>
          <Pressable onPress={() => void load(true)} accessibilityRole="button" accessibilityLabel="Refresh details" style={styles.refreshButton}>
            <Ionicons name="refresh" size={20} color={colors.brand} />
          </Pressable>
        </View>

        {error ? <View style={styles.errorWrap}><ErrorState message={error} onRetry={() => void load()} /></View> : null}

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.brand} />}
          showsVerticalScrollIndicator={false}
        >
          {/* Job summary */}
          <View style={styles.card}>
            <View style={styles.summaryTopRow}>
              <View style={styles.servicePill}>
                <Ionicons name="construct-outline" size={16} color={colors.brandMid} />
                <Text style={styles.servicePillText}>{request.service_type || job?.service_type || "SERVICE"}</Text>
              </View>
              <View style={styles.priorityPill}>
                <Text style={styles.priorityPillText}>{(request.priority || job?.priority || "NORMAL").toUpperCase()} PRIORITY</Text>
              </View>
              <View style={[styles.statusPill, isCompleted ? styles.statusCompleted : isCancelled ? styles.statusCancelled : styles.statusOther]}>
                <Ionicons name={isCompleted ? "checkmark-circle" : isCancelled ? "close-circle" : "time-outline"} size={14} color={isCompleted ? colors.success : isCancelled ? colors.danger : colors.brandMid} />
                <Text style={[styles.statusPillText, { color: isCompleted ? colors.success : isCancelled ? colors.danger : colors.brandMid }]}>{displayStatus(status)}</Text>
              </View>
            </View>

            <Text style={styles.jobTitle}>{request.title}</Text>
            <Text style={styles.jobSubtitle}>{request.request_number}{resolvedJobId ? ` · Job #${resolvedJobId}` : ""}</Text>

            {isCompleted ? (
              <View style={styles.completionBanner}>
                <View style={styles.bannerIcon}><Ionicons name="calendar-outline" size={20} color={colors.brandMid} /></View>
                <View style={styles.bannerCopy}>
                  <Text style={styles.bannerTitle}>Service completed{job?.completed_at ? ` on ${formatDate(job.completed_at)}` : ""}</Text>
                  <Text style={styles.bannerSubtitle}>{invoice?.work_summary || "FieldOps service completion record"}</Text>
                </View>
                <View style={[styles.paymentPill, resolvedPaymentStatus === "PAID" ? styles.paymentPillPaid : styles.paymentPillOther]}>
                  <Text style={[styles.paymentPillText, resolvedPaymentStatus === "PAID" ? styles.paymentPaidText : styles.paymentOtherText]}>{resolvedPaymentStatus}</Text>
                </View>
              </View>
            ) : null}
          </View>

          {/* Service details */}
          <View style={styles.card}>
            <SectionHeading icon="document-text-outline" title="Service details" />
            <DetailLine icon="reader-outline" label="Description" value={request.description || jobDetails?.issue_description} />
            <DetailLine icon="location-outline" label="Service address" value={job?.site_address || request.location || job?.location} />
            <DetailLine
              icon="calendar-outline"
              label="Scheduled visit"
              value={[
                jobDetails?.preferred_service_date || request.preferred_visit_date
                  ? formatDate(jobDetails?.preferred_service_date || request.preferred_visit_date)
                  : null,
                jobDetails?.preferred_service_time,
              ].filter(Boolean).join(" · ") || "No appointment details recorded"}
            />
            <DetailLine icon="call-outline" label="Contact number on file" value={request.contact_number} last />
          </View>

          {/* Technician and job lifecycle */}
          <View style={styles.card}>
            <SectionHeading icon="people-outline" title="Technician & visit" />
            <View style={styles.technicianRow}>
              <View style={styles.technicianAvatar}>
                <Text style={styles.technicianInitials}>{initials(technicianName)}</Text>
              </View>
              <View style={styles.technicianInfo}>
                <Text style={styles.technicianName}>
                  {technicianName || "Technician not assigned"}
                </Text>

                <Text style={styles.technicianOrganization}>
                  {organizationName
                    ? `Organization: ${organizationName}`
                    : "Organization details not available"}
                </Text>

                <Text style={styles.technicianSkills}>
                  {job?.assigned_technician_skills?.length
                    ? job.assigned_technician_skills.join(" · ")
                    : job?.service_type ||
                      request.service_type ||
                      "Field service technician"}
                </Text>
                {job?.assigned_technician_experience ? (
                  <View style={styles.experiencePill}><Text style={styles.experienceText}>{job.assigned_technician_experience} experience</Text></View>
                ) : null}
              </View>
              {resolvedJobId && technicianPhone ? (
                <Pressable
                  onPress={() => void Linking.openURL(`tel:${technicianPhone}`).catch(() => Alert.alert("Unable to call", "Your device could not open the phone dialer."))}
                  style={styles.smallActionButton}
                  accessibilityRole="button"
                  accessibilityLabel="Call technician"
                >
                  <Ionicons name="call-outline" size={19} color={colors.brand} />
                  <Text style={styles.smallActionText}>Call</Text>
                </Pressable>
              ) : null}
              {resolvedJobId && technicianName ? (
                <Pressable
                  onPress={() => router.push({ pathname: "/job-chat/[jobId]", params: { jobId: String(resolvedJobId) } })}
                  style={styles.smallActionButton}
                  accessibilityRole="button"
                  accessibilityLabel="Chat with technician"
                >
                  <Ionicons name="chatbubble-ellipses-outline" size={19} color={colors.brand} />
                  <Text style={styles.smallActionText}>Chat</Text>
                </Pressable>
              ) : null}
            </View>

            <View style={styles.timelineWrap}>
              {timeline.map((item, index) => (
                <TimelineItem
                  key={item.title}
                  icon={item.icon}
                  title={item.title}
                  timestamp={item.timestamp}
                  complete={item.complete}
                  last={index === timeline.length - 1}
                />
              ))}
            </View>
          </View>

          {/* Work report */}
          <View style={styles.card}>
            <SectionHeading icon="construct-outline" title="Work report" />
            <DetailLine icon="alert-circle-outline" label="Issue reported" value={request.description || jobDetails?.issue_description} />
            <DetailLine icon="document-text-outline" label="Work summary" value={invoice?.work_summary} />
            <DetailLine
              icon="cube-outline"
              label="Parts & materials"
              value={invoice ? `Materials total: ${formatMoney(invoice.material_cost)} · See invoice breakdown below` : "Itemized material details are not available yet"}
            />
            <DetailLine
              icon="time-outline"
              label="Work duration"
              value={workDuration}
              last
            />
          </View>

          {/* Invoice */}
          {invoice ? (
            <View style={styles.card}>
              <View style={styles.invoiceHeader}>
                <SectionHeading icon="receipt-outline" title="Invoice breakdown" />
                <View style={[styles.paymentPill, resolvedPaymentStatus === "PAID" ? styles.paymentPillPaid : styles.paymentPillOther]}>
                  <Text style={[styles.paymentPillText, resolvedPaymentStatus === "PAID" ? styles.paymentPaidText : styles.paymentOtherText]}>{resolvedPaymentStatus}</Text>
                </View>
              </View>
              <Text style={styles.invoiceReference}>Invoice #{invoice.id} · Job #{invoice.job_id}</Text>
              {invoice.organization_name ? <Text style={styles.providerName}>Service provider: {invoice.organization_name}</Text> : null}
              <InvoiceAmountRow label="Labour charges" value={formatMoney(invoice.labour_cost)} />
              <InvoiceAmountRow label="Materials" value={formatMoney(invoice.material_cost)} />
              <InvoiceAmountRow label="Subtotal" value={formatMoney(invoice.subtotal)} />
              <InvoiceAmountRow label={`GST (${invoice.gst_rate}%)`} value={formatMoney(invoice.gst_amount)} />
              <InvoiceAmountRow label="Total amount" value={formatMoney(invoice.total_amount)} strong />
              <View style={styles.paymentStatusRow}>
                <View style={styles.paymentStatusCopy}>
                  <Ionicons name="card-outline" size={18} color={colors.brandMid} />
                  <Text style={styles.detailValue}>Payment status</Text>
                </View>
                <Text style={[styles.paymentPillText, resolvedPaymentStatus === "PAID" ? styles.paymentPaidText : styles.paymentOtherText]}>{resolvedPaymentStatus}</Text>
              </View>
              <Text style={styles.invoiceFootnote}>
                {invoice.created_at ? `Issued ${formatDate(invoice.created_at)}` : "Invoice date not recorded"}
                {invoice.completed_at ? ` · Completed ${formatDate(invoice.completed_at)}` : ""}
              </Text>
            </View>
          ) : (
            <View style={styles.card}>
              <SectionHeading icon="receipt-outline" title="Invoice breakdown" />
              <View style={styles.invoiceUnavailable}>
                <View style={styles.invoiceUnavailableIcon}><Ionicons name="document-text-outline" size={22} color={colors.brandMid} /></View>
                <Text style={styles.invoiceUnavailableTitle}>Invoice not available yet</Text>
                <Text style={styles.invoiceUnavailableCopy}>The invoice will appear here after the service has a recorded completion and billing record.</Text>
              </View>
            </View>
          )}

          {feedback?.has_feedback && feedback.feedback ? (
            <View style={styles.card}>
              <SectionHeading icon="star-outline" title="Your feedback" />
              <Text style={styles.feedbackStars}>{"★".repeat(feedback.feedback.rating)}{"☆".repeat(Math.max(0, 5 - feedback.feedback.rating))} <Text style={styles.feedbackRating}>· {feedback.feedback.rating}/5</Text></Text>
              {feedback.feedback.comment ? <Text style={styles.feedbackComment}>{feedback.feedback.comment}</Text> : <Text style={styles.detailLabel}>No written comment was provided.</Text>}
              {feedback.feedback.created_at ? <Text style={styles.invoiceFootnote}>{formatDateTime(feedback.feedback.created_at)}</Text> : null}
            </View>
          ) : null}

          {(canEditRequest(request.status, job?.status, Boolean(resolvedJobId)) || canCancelRequest(request.status, job?.status, Boolean(resolvedJobId))) ? (
            <View style={styles.requestActions}>
              {canEditRequest(request.status, job?.status, Boolean(resolvedJobId)) ? (
                <AppButton title="Edit request" icon="create-outline" kind="secondary" onPress={() => router.push({ pathname: "/requests/edit/[requestId]", params: { requestId: String(request.id) } })} />
              ) : null}
              {canCancelRequest(request.status, job?.status, Boolean(resolvedJobId)) ? (
                <AppButton title="Cancel request" icon="close-circle-outline" kind="danger" onPress={cancel} loading={busy} />
              ) : null}
            </View>
          ) : null}

          {resolvedJobId && !isCompleted && !isCancelled ? (
            <AppButton title="Track this job" icon="navigate-outline" onPress={() => router.push({ pathname: "/jobs/[jobId]", params: { jobId: String(resolvedJobId) } })} />
          ) : null}
          <View style={{ height: 8 }} />
        </ScrollView>

        {/* Persistent actions like the design reference */}
        <View style={styles.footer}>
          <Pressable
            onPress={() => void handleShareReceipt()}
            disabled={!invoice}
            style={({ pressed }) => [styles.footerSecondary, !invoice && styles.footerDisabled, pressed && invoice && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="Share receipt"
          >
            <Ionicons name="receipt-outline" size={18} color={invoice ? colors.brand : colors.muted} />
            <Text style={[styles.footerSecondaryText, !invoice && styles.footerDisabledText]}>Share receipt</Text>
          </Pressable>
          <Pressable
            onPress={() => router.push("/invoices")}
            style={({ pressed }) => [styles.footerPrimary, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel="View all invoices"
          >
            <Ionicons name="list-outline" size={18} color="#FFFFFF" />
            <Text style={styles.footerPrimaryText}>View all invoices</Text>
          </Pressable>
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  page: {
    flex: 1,
    backgroundColor: colors.background,
  },

  header: {
    minHeight: 64,
    paddingHorizontal: 12,
    paddingTop: 4,
    paddingBottom: 8,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    backgroundColor: colors.background,
  },

  backButton: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },

  headerText: {
    flex: 1,
    gap: 2,
  },

  pageTitle: {
    fontSize: 20,
    lineHeight: 24,
    fontWeight: "900",
    color: colors.brand,
    letterSpacing: -0.45,
  },

  pageSubtitle: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 15,
  },

  refreshButton: {
    width: 36,
    height: 36,
    borderRadius: 12,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },

  errorWrap: {
    paddingHorizontal: 12,
    paddingBottom: 6,
  },

  scroll: {
    flex: 1,
  },

  scrollContent: {
    paddingHorizontal: 12,
    paddingTop: 2,
    paddingBottom: 14,
    gap: 9,
  },

  card: {
    backgroundColor: "#FFFFFF",
    borderRadius: 18,
    padding: 12,
    borderWidth: 1,
    borderColor: "#DCEDE4",
    gap: 8,
    shadowColor: "#113D2B",
    shadowOpacity: 0.035,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
    elevation: 1,
  },

  summaryTopRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 6,
  },

  servicePill: {
    flexDirection: "row",
    gap: 4,
    alignItems: "center",
    backgroundColor: "#EAF7EF",
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 8,
  },

  servicePillText: {
    color: colors.brandMid,
    fontWeight: "900",
    fontSize: 9,
    textTransform: "uppercase",
    letterSpacing: 0.2,
  },

  priorityPill: {
    backgroundColor: "#FFF3E6",
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 8,
  },

  priorityPillText: {
    color: "#B45309",
    fontWeight: "900",
    fontSize: 9,
    letterSpacing: 0.2,
  },

  statusPill: {
    marginLeft: "auto",
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    borderWidth: 1,
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 8,
  },

  statusCompleted: {
    backgroundColor: "#E9FBF0",
    borderColor: "#B6F0CC",
  },

  statusCancelled: {
    backgroundColor: "#FEF0EF",
    borderColor: "#F7C8C5",
  },

  statusOther: {
    backgroundColor: "#EEF7F1",
    borderColor: "#D3E9DA",
  },

  statusPillText: {
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 0.15,
  },

  jobTitle: {
    color: "#17253D",
    fontSize: 18,
    lineHeight: 23,
    fontWeight: "900",
    letterSpacing: -0.3,
  },

  jobSubtitle: {
    color: "#7C8B9B",
    fontSize: 10,
    lineHeight: 15,
    fontWeight: "700",
  },

  completionBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 1,
    padding: 9,
    borderRadius: 13,
    backgroundColor: "#F0F9F4",
  },

  bannerIcon: {
    height: 34,
    width: 34,
    borderRadius: 11,
    backgroundColor: "#E1F4E9",
    alignItems: "center",
    justifyContent: "center",
  },

  bannerCopy: {
    flex: 1,
    gap: 2,
  },

  bannerTitle: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "900",
  },

  bannerSubtitle: {
    color: colors.muted,
    fontSize: 10,
    lineHeight: 14,
  },

  paymentPill: {
    borderRadius: 999,
    paddingVertical: 5,
    paddingHorizontal: 8,
    borderWidth: 1,
  },

  paymentPillPaid: {
    backgroundColor: "#E4FBED",
    borderColor: "#B8F2CE",
  },

  paymentPillOther: {
    backgroundColor: "#F0F3F1",
    borderColor: "#E1E7E3",
  },

  paymentPillText: {
    fontSize: 9,
    fontWeight: "900",
    letterSpacing: 0.25,
  },

  paymentPaidText: {
    color: "#16794B",
  },

  paymentOtherText: {
    color: "#6C7972",
  },

  sectionHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 0,
  },

  sectionIcon: {
    width: 32,
    height: 32,
    borderRadius: 11,
    backgroundColor: "#E7F7EE",
    alignItems: "center",
    justifyContent: "center",
  },

  sectionTitle: {
    flex: 1,
    color: "#17231E",
    fontSize: 15,
    lineHeight: 20,
    fontWeight: "900",
    letterSpacing: -0.2,
  },

  detailLine: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 9,
    paddingVertical: 6,
  },

  detailLineBorder: {
    borderBottomWidth: 1,
    borderBottomColor: "#E7EEE9",
  },

  detailIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    backgroundColor: "#EFF8F2",
    alignItems: "center",
    justifyContent: "center",
  },

  detailTextWrap: {
    flex: 1,
    gap: 3,
    paddingTop: 1,
  },

  detailLabel: {
    color: "#718176",
    fontSize: 10,
    fontWeight: "800",
  },

  detailValue: {
    color: "#2C3932",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "500",
  },

  technicianRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    paddingBottom: 7,
    borderBottomWidth: 1,
    borderBottomColor: "#E7EEE9",
  },

  technicianAvatar: {
    height: 48,
    width: 48,
    borderRadius: 24,
    backgroundColor: colors.brand,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#DBF5E5",
  },

  technicianInitials: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "900",
  },

  technicianInfo: {
    flex: 1,
    gap: 3,
    minWidth: 0,
  },

  technicianName: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "900",
  },

  technicianOrganization: {
    color: colors.brandMid,
    fontSize: 10,
    fontWeight: "700",
    lineHeight: 14,
  },

  technicianSkills: {
    color: colors.muted,
    fontSize: 10,
    lineHeight: 14,
  },

  experiencePill: {
    alignSelf: "flex-start",
    backgroundColor: "#E9F9EF",
    borderRadius: 999,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },

  experienceText: {
    color: colors.success,
    fontSize: 9,
    fontWeight: "800",
  },

  smallActionButton: {
    minWidth: 38,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
    paddingVertical: 4,
    paddingHorizontal: 3,
  },

  smallActionText: {
    color: colors.brand,
    fontSize: 9,
    fontWeight: "800",
  },

  timelineWrap: {
    paddingTop: 3,
  },

  timelineRow: {
    flexDirection: "row",
    minHeight: 40,
    gap: 9,
  },

  timelineTrack: {
    width: 24,
    alignItems: "center",
  },

  timelineDot: {
    width: 23,
    height: 23,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1,
  },

  timelineDotComplete: {
    backgroundColor: colors.brandMid,
    borderWidth: 2,
    borderColor: "#D8F4E3",
  },

  timelineDotPending: {
    backgroundColor: "#F3F7F4",
    borderWidth: 1,
    borderColor: "#D4E0D8",
  },

  timelineLine: {
    width: 2,
    flex: 1,
    minHeight: 18,
    backgroundColor: "#DEE7E1",
    marginTop: -1,
  },

  timelineLineComplete: {
    backgroundColor: "#65B88A",
  },

  timelineContent: {
    flex: 1,
    paddingTop: 2,
    paddingBottom: 5,
    gap: 2,
  },

  timelineTitle: {
    color: "#26372D",
    fontSize: 11,
    fontWeight: "800",
  },

  timelineTitlePending: {
    color: "#7B8981",
    fontWeight: "700",
  },

  timelineTime: {
    color: "#809087",
    fontSize: 9,
    lineHeight: 13,
  },

  invoiceHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },

  invoiceReference: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "900",
    marginTop: -1,
  },

  providerName: {
    color: colors.muted,
    fontSize: 10,
    marginTop: -3,
  },

  invoiceAmountRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    paddingVertical: 5,
  },

  invoiceAmountLabel: {
    color: "#59675F",
    fontSize: 11,
    flex: 1,
  },

  invoiceAmountValue: {
    color: "#26372D",
    fontSize: 11,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },

  invoiceTotalRow: {
    marginTop: 1,
    backgroundColor: "#EAF8F0",
    borderRadius: 10,
    paddingHorizontal: 9,
    paddingVertical: 9,
  },

  invoiceTotalLabel: {
    color: colors.brand,
    fontSize: 12,
    fontWeight: "900",
  },

  invoiceTotalValue: {
    color: colors.brand,
    fontSize: 17,
    fontWeight: "900",
  },

  paymentStatusRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderTopWidth: 1,
    borderTopColor: "#E6EEE8",
    paddingTop: 8,
    marginTop: 1,
  },

  paymentStatusCopy: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },

  invoiceFootnote: {
    color: colors.muted,
    fontSize: 9,
    lineHeight: 13,
  },

  invoiceUnavailable: {
    alignItems: "center",
    gap: 7,
    paddingVertical: 12,
    paddingHorizontal: 8,
  },

  invoiceUnavailableIcon: {
    width: 46,
    height: 46,
    borderRadius: 15,
    backgroundColor: colors.brandSoft,
    alignItems: "center",
    justifyContent: "center",
  },

  invoiceUnavailableTitle: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "900",
  },

  invoiceUnavailableCopy: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 16,
    textAlign: "center",
  },

  feedbackStars: {
    color: "#E3A008",
    fontSize: 19,
    fontWeight: "800",
  },

  feedbackRating: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "700",
  },

  feedbackComment: {
    color: colors.text,
    fontSize: 12,
    lineHeight: 18,
  },

  requestActions: {
    gap: 7,
  },

  footer: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 9,
    borderTopWidth: 1,
    borderTopColor: "#E2EAE5",
    backgroundColor: "#FFFFFF",
  },

  footerSecondary: {
    flex: 1,
    minHeight: 43,
    borderWidth: 1.2,
    borderColor: colors.brandMid,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 6,
  },

  footerSecondaryText: {
    color: colors.brand,
    fontSize: 10,
    fontWeight: "900",
  },

  footerPrimary: {
    flex: 1,
    minHeight: 43,
    backgroundColor: colors.brand,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 6,
    paddingHorizontal: 6,
  },

  footerPrimaryText: {
    color: "#FFFFFF",
    fontSize: 10,
    fontWeight: "900",
  },

  footerDisabled: {
    borderColor: "#DCE4DE",
    backgroundColor: "#F7F9F8",
  },

  footerDisabledText: {
    color: colors.muted,
  },

  pressed: {
    opacity: 0.76,
  },
});