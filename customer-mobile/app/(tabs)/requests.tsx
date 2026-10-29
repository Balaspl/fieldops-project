import { useCallback, useMemo, useState } from "react";
import {
  Alert,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { customerApi } from "../../src/api/customer";
import { getApiErrorMessage } from "../../src/api/client";
import {
  AppButton,
  Card,
  EmptyState,
  ErrorState,
  LoadingView,
  Screen,
  StatusBadge,
} from "../../src/components/ui";
import type { CustomerJob, ServiceRequest } from "../../src/types/api";
import { formatDate, normalizedStatus } from "../../src/utils/format";
import { colors } from "../../src/theme";

/**
 * The backend's ServiceRequestResponse exposes these technician fields.
 * Keep them optional because a request may not have an assigned technician.
 */
type RequestWithTechnician = ServiceRequest & {
  assigned_technician_id?: number | null;
  assigned_technician_name?: string | null;
  assigned_technician_phone?: string | null;
  linked_job_id?: number | null;
  preferred_visit_date?: string | null;
};

const filters = [
  "ALL",
  "UNASSIGNED",
  "ASSIGNED",
  "ACTIVE",
  "COMPLETED",
  "CANCELLED",
] as const;

type RequestFilter = (typeof filters)[number];

function getStatus(request: ServiceRequest): string {
  return normalizedStatus(request.status);
}

function matches(request: ServiceRequest, filter: RequestFilter) {
  const status = getStatus(request);

  const cancelledStatuses = [
    "CANCELLED",
    "REJECTED",
    "REJECTED_BY_TECHNICIAN",
  ];

  const completedStatuses = ["COMPLETED", "CLOSED"];

  const activeStatuses = [
    "EN_ROUTE",
    "ENROUTE",
    "ON_SITE",
    "ONSITE",
    "IN_PROGRESS",
    "IN PROGRESS",
  ];

  const assignedStatuses = [
    "ASSIGNED",
    "ACCEPTED",
  ];

  const unassignedStatuses = [
    "CREATED",
    "PENDING",
    "UNASSIGNED",
    "QUEUED",
    "AWAITING_ACCEPTANCE",
  ];

  switch (filter) {
    case "ALL":
      return true;

    case "UNASSIGNED":
      return unassignedStatuses.includes(status);

    case "ASSIGNED":
      return assignedStatuses.includes(status);

    case "ACTIVE":
      return activeStatuses.includes(status);

    case "COMPLETED":
      return completedStatuses.includes(status);

    case "CANCELLED":
      return cancelledStatuses.includes(status);

    default:
      return true;
  }
}

type Metric = {
  key: RequestFilter;
  label: string;
  value: number;
  icon: keyof typeof Ionicons.glyphMap;
  tone: string;
  iconBackground: string;
  wave: string;
};

function CountMetric({ metric }: { metric: Metric }) {
  return (
    <View style={styles.metricCard}>
      <View
        style={[
          styles.metricIcon,
          { backgroundColor: metric.iconBackground },
        ]}
      >
        <Ionicons
          name={metric.icon}
          size={19}
          color={metric.tone}
        />
      </View>

      <Text style={styles.metricLabel}>
        {metric.label}
      </Text>

      <Text
        style={[
          styles.metricValue,
          { color: metric.tone },
        ]}
      >
        {metric.value}
      </Text>

      <View
        pointerEvents="none"
        style={[
          styles.metricWaveBack,
          { backgroundColor: metric.wave },
        ]}
      />

      <View
        pointerEvents="none"
        style={[
          styles.metricWaveFront,
          { backgroundColor: metric.wave },
        ]}
      />
    </View>
  );
}

async function callTechnician(phone?: string | null) {
  const rawPhone = phone?.trim();

  if (!rawPhone) {
    Alert.alert(
      "Phone number unavailable",
      "A technician phone number has not been provided for this request.",
    );
    return;
  }

  // Preserve a leading + for international numbers and remove formatting.
  const phoneNumber = rawPhone.replace(/[^\d+]/g, "");

  if (!phoneNumber || !/\d/.test(phoneNumber)) {
    Alert.alert(
      "Invalid phone number",
      "The technician phone number returned by the server is invalid.",
    );
    return;
  }

  try {
    await Linking.openURL(`tel:${phoneNumber}`);
  } catch {
    Alert.alert(
      "Unable to open phone",
      "Your device could not open the phone dialer.",
    );
  }
}

function getInitials(name?: string | null): string {
  if (!name) return "TE";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export default function CustomerRequestsScreen() {
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [filter, setFilter] = useState<RequestFilter>("ALL");
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
      // Preserve the existing customer-scoped backend request and sync live job details.
      const [fetchedRequests, fetchedJobs] = await Promise.all([
        customerApi.requests(),
        customerApi.jobs().catch(() => [] as CustomerJob[]),
      ]);
      setRequests(fetchedRequests);
      setJobs(fetchedJobs);
    } catch (e) {
      setError(
        getApiErrorMessage(
          e,
          "Could not load service requests.",
        ),
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void load();
    }, [load]),
  );

  const shown = useMemo(
    () => requests.filter((item) => matches(item, filter)),
    [requests, filter],
  );

  const metrics = useMemo<Metric[]>(() => {
    const count = (key: RequestFilter) =>
      requests.filter((request) => matches(request, key)).length;

    return [
      {
        key: "ALL",
        label: "Total Requests",
        value: requests.length,
        icon: "document-text-outline",
        tone: "#008A63",
        iconBackground: "#D9FBE9",
        wave: "#B5F2DB",
      },
      {
        key: "UNASSIGNED",
        label: "Unassigned Jobs",
        value: count("UNASSIGNED"),
        icon: "time-outline",
        tone: "#B45309",
        iconBackground: "#FFF1C5",
        wave: "#FFE58A",
      },
      {
        key: "ASSIGNED",
        label: "Assigned Jobs",
        value: count("ASSIGNED"),
        icon: "people-outline",
        tone: "#245AC8",
        iconBackground: "#DCEAFF",
        wave: "#B7D5FF",
      },
      {
        key: "ACTIVE",
        label: "Active Jobs",
        value: count("ACTIVE"),
        icon: "briefcase-outline",
        tone: "#8438C7",
        iconBackground: "#F1E2FF",
        wave: "#DFC2FF",
      },
      {
        key: "COMPLETED",
        label: "Completed Jobs",
        value: count("COMPLETED"),
        icon: "checkmark-circle-outline",
        tone: "#067653",
        iconBackground: "#D9FBE9",
        wave: "#A9EED3",
      },
      {
        key: "CANCELLED",
        label: "Cancelled Jobs",
        value: count("CANCELLED"),
        icon: "close-circle-outline",
        tone: "#B42330",
        iconBackground: "#FFE1E3",
        wave: "#FFB8BE",
      },
    ];
  }, [requests]);

  const filterLabels: Record<RequestFilter, string> = {
    ALL: "All Requests",
    UNASSIGNED: "Unassigned",
    ASSIGNED: "Assigned",
    ACTIVE: "In Progress",
    COMPLETED: "Completed",
    CANCELLED: "Cancelled",
  };

  return (
    <Screen
      scroll={false}
      contentStyle={{
        paddingHorizontal: 0,
        paddingTop: 0,
        paddingBottom: 0,
      }}
    >
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => void load(true)}
            tintColor={colors.brand}
          />
        }
        showsVerticalScrollIndicator={false}
      >
        {/* Page title and new-request action */}
        <View style={styles.pageHeader}>
          <View style={styles.pageHeading}>
            <View style={styles.headingIcon}>
              <Ionicons
                name="document-text-outline"
                size={23}
                color="#15956C"
              />
            </View>

            <View style={styles.pageTitleText}>
              <Text style={styles.pageTitle}>
                My Requests
              </Text>

              <Text style={styles.subtitle}>
                View and manage your service bookings
              </Text>
            </View>
          </View>

          <Pressable
            onPress={() => router.push("/requests/new")}
            style={({ pressed }) => [
              styles.newRequestButton,
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel="Create a new service request"
          >
            <Ionicons
              name="add-circle-outline"
              size={19}
              color="#FFFFFF"
            />
            <Text style={styles.newRequestText}>
              New Request
            </Text>
          </Pressable>
        </View>

        {/* Six authoritative counts, derived from loaded requests */}
        {!error && (
          <View style={styles.metricGrid}>
            {metrics.map((metric) => (
              <CountMetric
                key={metric.key}
                metric={metric}
              />
            ))}
          </View>
        )}

        {/* Horizontally scrolling filters */}
        <View style={styles.filterSection}>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.filterRow}
          >
            {filters.map((item) => {
              const selected = filter === item;

              return (
                <Pressable
                  key={item}
                  onPress={() => setFilter(item)}
                  style={[
                    styles.filterChip,
                    selected && styles.filterChipSelected,
                  ]}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                >
                  <Text
                    style={[
                      styles.filterText,
                      selected && styles.filterTextSelected,
                    ]}
                  >
                    {filterLabels[item]}
                    {item !== "ALL"
                      ? ` (${metrics.find((m) => m.key === item)?.value ?? 0})`
                      : ""}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
        </View>

        {error ? (
          <ErrorState
            message={error}
            onRetry={() => void load()}
          />
        ) : loading ? (
          <LoadingView message="Loading service requests…" />
        ) : shown.length === 0 ? (
          <Card>
            <EmptyState
              title="No requests found"
              message={
                filter === "ALL"
                  ? "Book a service and your request will appear here."
                  : `There are no ${filterLabels[filter].toLowerCase()} to show.`
              }
              icon="documents-outline"
              action={
                <AppButton
                  title="Book a service"
                  onPress={() => router.push("/requests/new")}
                />
              }
            />
          </Card>
        ) : (
          <View style={styles.requestList}>
            {shown.map((request) => {
              const details = request as RequestWithTechnician;
              const technicianName = details.assigned_technician_name?.trim();
              const technicianPhone = details.assigned_technician_phone?.trim();

              const isActive = matches(request, "ACTIVE");
              const isCompleted = matches(request, "COMPLETED");
              const isAssigned = matches(request, "ASSIGNED");
              const isCancelled = matches(request, "CANCELLED");

              // Only use the job explicitly linked to this request. Matching by service type
              // can accidentally display another customer's/job's technician.
              const targetJobId = details.linked_job_id ?? details.created_job?.id;
              const matchedJob = targetJobId
                ? jobs.find((job) => job.id === targetJobId)
                : undefined;

              const resolvedJobId = targetJobId ?? matchedJob?.id;
              const effectiveTechPhone =
                technicianPhone || matchedJob?.assigned_technician_phone?.trim();
              const effectiveTechName =
                technicianName || matchedJob?.assigned_technician_name?.trim();
              const hasTechnician = Boolean(
                effectiveTechName ||
                effectiveTechPhone ||
                details.assigned_technician_id ||
                matchedJob?.assigned_technician_id,
              );

              // Never invent an ETA or distance. Show them only when returned for an en-route job.
              const rawMinutes = matchedJob?.eta_duration_minutes;
              const rawDistance = matchedJob?.eta_distance_km;
              const jobStatus = normalizedStatus(matchedJob?.status);
              const isEnRoute = ["EN_ROUTE", "ENROUTE"].includes(jobStatus);
              const hasValidEta =
                isEnRoute && rawMinutes != null && rawMinutes > 0 && rawMinutes <= 180;
              const hasValidDistance =
                rawDistance != null &&
                Number.isFinite(rawDistance) &&
                rawDistance >= 0 &&
                rawDistance <= 500;

              const showTrackActions = !isCompleted && !isCancelled;

              return (
                <View key={request.id} style={styles.jobCard}>
                  {/* Top Category & Status Header */}
                  <View style={styles.cardHeaderRow}>
                    <View style={styles.categoryWrap}>
                      <Text style={styles.categoryBadge}>
                        {request.service_type || "HVAC REPAIR"}
                      </Text>
                      <Text style={styles.priorityBullet}>•</Text>
                      <Text style={styles.priorityText}>
                        {(request.priority || "MEDIUM").toUpperCase()} PRIORITY
                      </Text>
                    </View>

                    {/* Status Pill matching Image 2 */}
                    <View
                      style={[
                        styles.statusPill,
                        isCompleted
                          ? styles.statusPillCompleted
                          : isCancelled
                          ? styles.statusPillCancelled
                          : styles.statusPillActive,
                      ]}
                    >
                      {isCompleted ? (
                        <Ionicons
                          name="checkmark"
                          size={12}
                          color="#065F46"
                          style={{ marginRight: 4 }}
                        />
                      ) : (
                        <View style={styles.activePillDot} />
                      )}
                      <Text
                        style={[
                          styles.statusPillText,
                          isCompleted
                            ? styles.statusPillTextCompleted
                            : isCancelled
                            ? styles.statusPillTextCancelled
                            : styles.statusPillTextActive,
                        ]}
                      >
                        {isCompleted
                          ? "Completed"
                          : isCancelled
                          ? ["REJECTED", "REJECTED_BY_TECHNICIAN"].includes(getStatus(request))
                            ? "Rejected"
                            : "Cancelled"
                          : isActive
                          ? "In Progress"
                          : isAssigned
                          ? "Assigned"
                          : ["CREATED", "PENDING", "UNASSIGNED", "QUEUED", "AWAITING_ACCEPTANCE"].includes(getStatus(request))
                          ? "Pending"
                          : getStatus(request).replace(/_/g, " ") || "Pending"}
                      </Text>
                    </View>
                  </View>

                  {/* Title and Request Number */}
                  <Text style={styles.jobCardTitle}>{request.title}</Text>
                  <Text style={styles.jobCardSubtitle}>
                    {request.request_number}
                    {resolvedJobId ? ` • Job #${resolvedJobId}` : ""}
                  </Text>

                  {/* Show technician information only when the backend actually provides it. */}
                  {!isCompleted && !isCancelled ? (
                    <View style={styles.techStrip}>
                      <View style={styles.techAvatarWrapper}>
                        <View style={styles.techAvatar}>
                          <Text style={styles.techAvatarInitials}>
                            {getInitials(effectiveTechName || "Technician")}
                          </Text>
                        </View>
                      </View>

                      <View style={styles.techInfoWrap}>
                        <Text style={styles.techNameText}>
                          {effectiveTechName ||
                            (hasTechnician
                              ? "Technician assigned"
                              : "Technician details pending")}
                        </Text>
                        {hasValidEta ? (
                          <Text style={styles.techStatusValue}>
                            En route to site · {Math.round(rawMinutes!)} min
                            {hasValidDistance ? ` (${rawDistance!.toFixed(1)} km)` : ""}
                          </Text>
                        ) : (
                          <Text style={styles.techStatusValue}>
                            {hasTechnician
                              ? "Assignment confirmed"
                              : "We’ll show technician details after assignment."}
                          </Text>
                        )}
                      </View>
                    </View>
                  ) : isCompleted ? (
                    <View style={styles.completedNoticeBox}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.completedNoticeTitle}>
                          Service completed on{" "}
                          {formatDate(request.updated_at || request.created_at)}
                        </Text>
                        <Text style={styles.completedNoticeSub}>
                          FieldOps Certified Resolution
                        </Text>
                      </View>
                      <View style={styles.paidChip}>
                        <Text style={styles.paidChipText}>Paid</Text>
                      </View>
                    </View>
                  ) : null}

                  {/* Address and Scheduled Visit */}
                  <View style={styles.cardDetailsBox}>
                    <View style={styles.detailRow}>
                      <Ionicons
                        name="location-outline"
                        size={16}
                        color="#94A3B8"
                      />
                      <Text
                        style={styles.detailAddressText}
                        numberOfLines={2}
                      >
                        {request.location || "Location not provided"}
                      </Text>
                    </View>

                    <View style={styles.detailRow}>
                      <Ionicons
                        name="calendar-outline"
                        size={16}
                        color="#94A3B8"
                      />
                      <Text style={styles.detailDateText}>
                        Scheduled Visit:{" "}
                        <Text style={styles.detailDateTextBold}>
                          {details.preferred_visit_date
                            ? formatDate(details.preferred_visit_date)
                            : "Not scheduled"}
                        </Text>
                      </Text>
                    </View>
                  </View>

                  {/* Action Buttons Row (Image 2 style) */}
                  <View style={styles.cardFooterActions}>
                    {showTrackActions ? (
                      <>
                        <View style={styles.leftBtnGroup}>
                          {/* Only show calling when a real phone number was returned by the API. */}
                          {effectiveTechPhone ? (
                            <Pressable
                              onPress={() => void callTechnician(effectiveTechPhone)}
                              style={({ pressed }) => [
                                styles.callIconBtn,
                                pressed && styles.pressed,
                              ]}
                              accessibilityLabel="Call technician"
                            >
                              <Ionicons
                                name="call-outline"
                                size={18}
                                color="#0F172A"
                              />
                            </Pressable>
                          ) : null}

                          <Pressable
                            onPress={() => {
                              if (resolvedJobId) {
                                router.push({
                                  pathname: "/jobs/[jobId]",
                                  params: { jobId: String(resolvedJobId) },
                                });
                              } else {
                                router.push({
                                  pathname: "/requests/[requestId]",
                                  params: { requestId: String(request.id) },
                                });
                              }
                            }}
                            style={({ pressed }) => [
                              styles.chatActionBtn,
                              pressed && styles.pressed,
                            ]}
                            accessibilityLabel="Chat with technician"
                          >
                            <Ionicons
                              name="chatbubble-outline"
                              size={17}
                              color="#0F172A"
                            />
                            <Text style={styles.chatActionText}>Chat</Text>
                          </Pressable>
                        </View>

                        {/* Track on Map Button */}
                        <Pressable
                          onPress={() => {
                            if (resolvedJobId) {
                              router.push({
                                pathname: "/jobs/[jobId]",
                                params: { jobId: String(resolvedJobId) },
                              });
                            } else {
                              router.push({
                                pathname: "/requests/[requestId]",
                                params: { requestId: String(request.id) },
                              });
                            }
                          }}
                          style={({ pressed }) => [
                            styles.trackOnMapBtn,
                            pressed && styles.pressed,
                          ]}
                          accessibilityLabel="Track on map"
                        >
                          <Ionicons
                            name="map-outline"
                            size={18}
                            color="#6EE7B7"
                          />
                          <Text style={styles.trackOnMapText}>
                            Track on Map
                          </Text>
                        </Pressable>
                      </>
                    ) : isCompleted ? (
                      <>
                        <View style={styles.starsWrapper}>
                          <Text style={styles.starsIconText}>★★★★★</Text>
                          <Text style={styles.starsScoreText}>(5.0)</Text>
                        </View>

                        <Pressable
                          onPress={() =>
                            router.push({
                              pathname: "/requests/[requestId]",
                              params: { requestId: String(request.id) },
                            })
                          }
                          style={({ pressed }) => [
                            styles.receiptActionBtn,
                            pressed && styles.pressed,
                          ]}
                        >
                          <Ionicons
                            name="receipt-outline"
                            size={16}
                            color="#334155"
                          />
                          <Text style={styles.receiptActionText}>
                            View Receipt
                          </Text>
                        </Pressable>
                      </>
                    ) : (
                      <>
                        <Text style={styles.cardCreatedDateText}>
                          Created {formatDate(request.created_at)}
                        </Text>

                        <Pressable
                          onPress={() =>
                            router.push({
                              pathname: "/requests/[requestId]",
                              params: { requestId: String(request.id) },
                            })
                          }
                          style={({ pressed }) => [
                            styles.normalDetailsBtn,
                            pressed && styles.pressed,
                          ]}
                        >
                          <Text style={styles.normalDetailsText}>
                            View Details
                          </Text>
                          <Ionicons
                            name="chevron-forward"
                            size={14}
                            color="#00885F"
                          />
                        </Pressable>
                      </>
                    )}
                  </View>
                </View>
              );
            })}
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F0F5F2",
  },

  content: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 32,
  },

  pageHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    marginBottom: 18,
  },

  pageHeading: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    minWidth: 0,
  },

  headingIcon: {
    width: 35,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },

  pageTitleText: {
    flex: 1,
    minWidth: 0,
  },

  pageTitle: {
    color: "#10243F",
    fontSize: 23,
    fontWeight: "900",
    letterSpacing: -0.7,
  },

  subtitle: {
    color: "#77867E",
    fontSize: 10,
    lineHeight: 15,
    marginTop: 3,
  },

  newRequestButton: {
    minHeight: 43,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    paddingHorizontal: 11,
    borderRadius: 11,
    backgroundColor: "#00885F",
    elevation: 3,
    shadowColor: "#00885F",
    shadowOpacity: 0.17,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 3 },
  },

  newRequestText: {
    color: "#FFFFFF",
    fontWeight: "800",
    fontSize: 11,
  },

  metricGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: 9,
    marginBottom: 19,
  },

  metricCard: {
    width: "48.5%",
    height: 105,
    overflow: "hidden",
    position: "relative",
    padding: 11,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E2EAE5",
    backgroundColor: "#FFFFFF",
    elevation: 2,
    shadowColor: "#244735",
    shadowOpacity: 0.045,
    shadowRadius: 5,
    shadowOffset: { width: 0, height: 2 },
  },

  metricIcon: {
    width: 31,
    height: 31,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
  },

  metricLabel: {
    color: "#53665C",
    fontSize: 10,
    fontWeight: "600",
    marginTop: 7,
    zIndex: 2,
  },

  metricValue: {
    fontSize: 25,
    lineHeight: 29,
    fontWeight: "900",
    zIndex: 2,
  },

  metricWaveBack: {
    position: "absolute",
    width: 100,
    height: 32,
    bottom: -13,
    right: -20,
    borderRadius: 35,
    transform: [{ rotate: "-25deg" }],
    opacity: 0.40,
  },

  metricWaveFront: {
    position: "absolute",
    width: 75,
    height: 22,
    bottom: -12,
    right: 11,
    borderRadius: 30,
    transform: [{ rotate: "-20deg" }],
    opacity: 0.30,
  },

  filterSection: {
    marginBottom: 13,
  },

  filterRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    paddingVertical: 2,
    paddingRight: 8,
  },

  filterChip: {
    borderRadius: 25,
    borderWidth: 1,
    borderColor: "#DEE7E1",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 12,
    paddingVertical: 9,
  },

  filterChipSelected: {
    backgroundColor: "#003F31",
    borderColor: "#003F31",
  },

  filterText: {
    color: "#65766C",
    fontSize: 10,
    fontWeight: "800",
  },

  filterTextSelected: {
    color: "#FFFFFF",
  },

  requestList: {
    gap: 13,
  },

  jobCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 24,
    borderWidth: 1.5,
    borderColor: "#A7F3D0",
    padding: 18,
    shadowColor: "#059669",
    shadowOpacity: 0.06,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
    marginBottom: 16,
  },

  cardHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 6,
  },

  categoryWrap: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    paddingRight: 6,
  },

  categoryBadge: {
    color: "#059669",
    fontSize: 12,
    fontWeight: "800",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },

  priorityBullet: {
    color: "#94A3B8",
    marginHorizontal: 4,
    fontSize: 12,
  },

  priorityText: {
    color: "#94A3B8",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.3,
  },

  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 22,
    borderWidth: 1.5,
  },

  statusPillActive: {
    backgroundColor: "#FEF9C3",
    borderColor: "#FDE047",
  },

  statusPillCompleted: {
    backgroundColor: "#ECFDF5",
    borderColor: "#A7F3D0",
  },

  statusPillCancelled: {
    backgroundColor: "#FEF2F2",
    borderColor: "#FECACA",
  },

  activePillDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: "#D97706",
    marginRight: 6,
  },

  statusPillText: {
    fontSize: 11,
    fontWeight: "800",
  },

  statusPillTextActive: {
    color: "#92400E",
  },

  statusPillTextCompleted: {
    color: "#065F46",
  },

  statusPillTextCancelled: {
    color: "#991B1B",
  },

  jobCardTitle: {
    color: "#0F172A",
    fontSize: 18,
    fontWeight: "900",
    lineHeight: 24,
    marginTop: 4,
  },

  jobCardSubtitle: {
    color: "#94A3B8",
    fontSize: 11,
    fontWeight: "600",
    marginTop: 3,
    marginBottom: 14,
  },

  techStrip: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#F0FDF9",
    borderWidth: 1.2,
    borderColor: "#CCFBF1",
    borderRadius: 16,
    padding: 12,
    marginBottom: 14,
  },

  techAvatarWrapper: {
    position: "relative",
  },

  techAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#064E3B",
    alignItems: "center",
    justifyContent: "center",
  },

  techAvatarInitials: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "900",
  },

  techOnlineDot: {
    position: "absolute",
    bottom: -1,
    right: -1,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: "#10B981",
    borderWidth: 2,
    borderColor: "#FFFFFF",
  },

  techInfoWrap: {
    flex: 1,
    marginLeft: 10,
    minWidth: 0,
  },

  techNameRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  techNameText: {
    color: "#0F172A",
    fontSize: 13,
    fontWeight: "800",
  },

  techRatingBadge: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 6,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },

  techRatingText: {
    color: "#334155",
    fontSize: 10,
    fontWeight: "700",
  },

  techStatusRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 3,
  },

  techStatusPrefix: {
    color: "#0D9488",
    fontSize: 11,
    fontWeight: "700",
  },

  techStatusValue: {
    color: "#042F2E",
    fontSize: 11,
    fontWeight: "800",
  },

  completedNoticeBox: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#F8FAFC",
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: "#F1F5F9",
    marginBottom: 14,
  },

  completedNoticeTitle: {
    color: "#334155",
    fontSize: 11,
    fontWeight: "700",
  },

  completedNoticeSub: {
    color: "#94A3B8",
    fontSize: 10,
    marginTop: 2,
  },

  paidChip: {
    backgroundColor: "#ECFDF5",
    borderColor: "#A7F3D0",
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },

  paidChipText: {
    color: "#065F46",
    fontSize: 10,
    fontWeight: "800",
    textTransform: "uppercase",
  },

  cardDetailsBox: {
    gap: 8,
    marginBottom: 16,
  },

  detailRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },

  detailAddressText: {
    flex: 1,
    color: "#334155",
    fontSize: 12,
    fontWeight: "500",
    lineHeight: 18,
  },

  detailDateText: {
    color: "#64748B",
    fontSize: 12,
    fontWeight: "500",
  },

  detailDateTextBold: {
    color: "#0F172A",
    fontWeight: "700",
  },

  cardFooterActions: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 4,
  },

  leftBtnGroup: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },

  callIconBtn: {
    width: 44,
    height: 44,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: "#E2E8F0",
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },

  chatActionBtn: {
    height: 44,
    paddingHorizontal: 14,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: "#E2E8F0",
    backgroundColor: "#FFFFFF",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  chatActionText: {
    color: "#0F172A",
    fontSize: 13,
    fontWeight: "700",
  },

  chatBadgeCircle: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: "#064E3B",
    alignItems: "center",
    justifyContent: "center",
  },

  chatBadgeText: {
    color: "#FFFFFF",
    fontSize: 10,
    fontWeight: "900",
  },

  trackOnMapBtn: {
    height: 44,
    paddingHorizontal: 16,
    borderRadius: 14,
    backgroundColor: "#064E3B",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },

  trackOnMapText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "800",
  },

  starsWrapper: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },

  starsIconText: {
    color: "#F59E0B",
    fontSize: 14,
    letterSpacing: 1,
  },

  starsScoreText: {
    color: "#64748B",
    fontSize: 12,
    fontWeight: "700",
    marginLeft: 2,
  },

  receiptActionBtn: {
    height: 42,
    paddingHorizontal: 14,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: "#E2E8F0",
    backgroundColor: "#FFFFFF",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },

  receiptActionText: {
    color: "#334155",
    fontSize: 12,
    fontWeight: "700",
  },

  cardCreatedDateText: {
    color: "#94A3B8",
    fontSize: 11,
    fontWeight: "500",
  },

  normalDetailsBtn: {
    height: 40,
    paddingHorizontal: 14,
    borderRadius: 12,
    backgroundColor: "#F0FDF4",
    borderWidth: 1,
    borderColor: "#DCFCE7",
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
  },

  normalDetailsText: {
    color: "#065F46",
    fontSize: 12,
    fontWeight: "800",
  },

  pressed: {
    opacity: 0.78,
  },
});