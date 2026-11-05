import { useEffect, useRef, useState } from "react";
import { AppState, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Location from "expo-location";

import { getTechnicianJobs, type TechnicianJob } from "../api/technician";
import { performTechnicianJobAction } from "../api/jobActions";
import { useAuthStore } from "../auth/authStore";
import { getTechnicianAvailabilityLocation } from "../gps/gpsService";

const ACCEPTANCE_WINDOW_MS = 5 * 60 * 1000;
const REFRESH_INTERVAL_MS = 12_000;
const DISTANCE_LOOKUP_TIMEOUT_MS = 5_000;

function isAwaitingAcceptance(job: TechnicianJob): boolean {
  return ["ASSIGNED", "ACTIVE", "PENDING", "AWAITING_ACCEPTANCE"].includes(
    job.status.trim().toUpperCase().replace(/[ -]+/g, "_")
  );
}

function getDeadline(job: TechnicianJob): number | null {
  const explicitDeadline = job.acceptance_expires_at;
  if (typeof explicitDeadline === "string") {
    const timestamp = Date.parse(explicitDeadline);
    if (Number.isFinite(timestamp)) return timestamp;
  }
  if (!job.assigned_at) return null;
  const assignedAt = Date.parse(job.assigned_at);
  return Number.isFinite(assignedAt) ? assignedAt + ACCEPTANCE_WINDOW_MS : null;
}

function formatCountdown(seconds: number | null): string {
  if (seconds === null) return "—:—";
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}

function haversineDistanceKm(
  first: { latitude: number; longitude: number },
  second: { latitude: number; longitude: number }
): number {
  const radians = (degrees: number) => degrees * (Math.PI / 180);
  const latitudeDelta = radians(second.latitude - first.latitude);
  const longitudeDelta = radians(second.longitude - first.longitude);
  const value = Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(radians(first.latitude)) * Math.cos(radians(second.latitude)) *
    Math.sin(longitudeDelta / 2) ** 2;
  return 6371 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
}

function getPreferredDateTime(job: TechnicianJob): string {
  const date = job.preferred_service_date;
  const time = job.preferred_service_time;
  if (typeof date === "string" && typeof time === "string" && time.trim()) {
    return `${date} · ${time}`;
  }
  if (typeof job.scheduled_at === "string") {
    const timestamp = Date.parse(job.scheduled_at);
    if (Number.isFinite(timestamp)) {
      const scheduled = new Date(timestamp);
      if (typeof date === "string" && date.trim()) {
        return `${date} · ${typeof time === "string" && time.trim() ? time : scheduled.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
      }
      return scheduled.toLocaleString([], {
        month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit"
      });
    }
  }
  if (typeof date === "string" && date.trim()) return date;
  if (typeof time === "string" && time.trim()) return time;
  return "Not provided";
}

export function TechnicianJobAssignmentOffer() {
  const user = useAuthStore((state) => state.user);
  const router = useRouter();
  const [offer, setOffer] = useState<TechnicianJob | null>(null);
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState<"accept" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [technicianLocation, setTechnicianLocation] = useState<{ latitude: number; longitude: number } | null>(null);
  const [customerCoordinates, setCustomerCoordinates] = useState<{ latitude: number; longitude: number } | null>(null);
  const [distanceLoading, setDistanceLoading] = useState(false);
  const handledOfferIds = useRef(new Set<string>());

  useEffect(() => {
    handledOfferIds.current.clear();
    setOffer(null);
  }, [user?.id, user?.tenant_id]);

  useEffect(() => {
    if (!user || user.role.toLowerCase() !== "technician") return;
    let active = true;
    let requestInFlight = false;

    const checkForOffer = async () => {
      if (!active || requestInFlight || AppState.currentState !== "active") return;
      requestInFlight = true;
      try {
        const jobs = await getTechnicianJobs();
        if (!active) return;
        setOffer((current) => {
          if (current && isAwaitingAcceptance(current)) {
            const latest = jobs.find((job) => String(job.id) === String(current.id));
            if (latest && isAwaitingAcceptance(latest)) return latest;
            return null;
          }
          const nextOffer = jobs.find((job) =>
            isAwaitingAcceptance(job) && !handledOfferIds.current.has(String(job.id))
          );
          return nextOffer ?? null;
        });
      } catch {
        // Network failures should not interrupt the technician's current screen.
      } finally {
        requestInFlight = false;
      }
    };

    void checkForOffer();
    const interval = setInterval(() => void checkForOffer(), REFRESH_INTERVAL_MS);
    const appStateSubscription = AppState.addEventListener("change", (state) => {
      if (state === "active") void checkForOffer();
    });

    return () => {
      active = false;
      clearInterval(interval);
      appStateSubscription.remove();
    };
  }, [user?.id, user?.tenant_id, user?.role]);

  useEffect(() => {
    if (!offer) return;
    setNow(Date.now());
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [offer?.id]);

  useEffect(() => {
    let active = true;
    setTechnicianLocation(null);
    setCustomerCoordinates(null);
    setDistanceLoading(Boolean(offer));
    if (!offer) return () => { active = false; };
    const timeout = setTimeout(() => {
      if (active) setDistanceLoading(false);
    }, DISTANCE_LOOKUP_TIMEOUT_MS);
    const refreshServerFix = async () => {
      if (user?.tenant_id == null) return;
      try {
        const location = await getTechnicianAvailabilityLocation(user.tenant_id);
        const timestamp = typeof location.timestamp === "string" ? Date.parse(location.timestamp) : Number.NaN;
        const age = Date.now() - timestamp;
        if (
          active && location.status !== "unavailable" &&
          typeof location.latitude === "number" && Number.isFinite(location.latitude) &&
          typeof location.longitude === "number" && Number.isFinite(location.longitude) &&
          Number.isFinite(age) && age >= -30_000 && age <= 120_000
        ) {
          setTechnicianLocation({ latitude: location.latitude, longitude: location.longitude });
        }
      } catch {
        // Fall back to the device's current or last known fix.
      }
    };
    void refreshServerFix();
    const locationRefresh = setInterval(() => void refreshServerFix(), 15_000);
    void (async () => {
      const jobLatitude = Number(offer.site_latitude);
      const jobLongitude = Number(offer.site_longitude);
      const hasCoordinates = Number.isFinite(jobLatitude) && Number.isFinite(jobLongitude) && !(jobLatitude === 0 && jobLongitude === 0);
      if (hasCoordinates) {
        setCustomerCoordinates({ latitude: jobLatitude, longitude: jobLongitude });
      } else {
        const address = offer.location || offer.site_address || offer.address;
        if (address) {
          void Location.geocodeAsync(address).then((matches) => {
            const match = matches[0];
            if (active && match && Number.isFinite(match.latitude) && Number.isFinite(match.longitude)) {
              setCustomerCoordinates({ latitude: match.latitude, longitude: match.longitude });
            }
          }).catch(() => {
            // Some addresses cannot be geocoded; display the fallback state.
          });
        }
      }
      try {
        let permission = await Location.getForegroundPermissionsAsync();
        if (permission.status !== "granted") {
          permission = await Location.requestForegroundPermissionsAsync();
        }
        if (permission.status !== "granted") {
          if (active) setDistanceLoading(false);
          return;
        }
        const lastKnown = await Location.getLastKnownPositionAsync({ maxAge: 120_000, requiredAccuracy: 1_000 });
        if (lastKnown && active) {
          setTechnicianLocation({ latitude: lastKnown.coords.latitude, longitude: lastKnown.coords.longitude });
          return;
        }
        const fix = await Promise.race([
          Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }),
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error("Location lookup timed out")), DISTANCE_LOOKUP_TIMEOUT_MS))
        ]);
        if (active) setTechnicianLocation({ latitude: fix.coords.latitude, longitude: fix.coords.longitude });
      } catch {
        // Distance is optional; never block an assignment offer on GPS.
      }
    })();
    return () => { active = false; clearTimeout(timeout); clearInterval(locationRefresh); };
  }, [offer?.id, user?.tenant_id]);

  useEffect(() => {
    if (technicianLocation && customerCoordinates) setDistanceLoading(false);
  }, [technicianLocation, customerCoordinates]);

  const deadline = offer ? getDeadline(offer) : null;
  const secondsRemaining = deadline === null ? null : Math.max(0, Math.floor((deadline - now) / 1000));
  const expired = secondsRemaining === 0;
  const distanceKm = technicianLocation && customerCoordinates
    ? haversineDistanceKm(technicianLocation, customerCoordinates)
    : null;

  async function handleOfferAction(action: "accept" | "reject") {
    if (!offer || busy || (action === "accept" && expired)) return;
    setBusy(action);
    setError(null);
    try {
      await performTechnicianJobAction(
        offer.id,
        action,
        action === "reject"
          ? { reason: "Technician declined from the mobile assignment offer." }
          : {}
      );
      const jobId = String(offer.id);
      handledOfferIds.current.add(jobId);
      setOffer(null);
      if (action === "accept") {
        router.push({ pathname: "/(app)/jobs/[jobId]", params: { jobId } });
      }
    } catch {
      setError(action === "accept" ? "Could not accept this job. Please try again." : "Could not decline this job. Please try again.");
    } finally {
      setBusy(null);
    }
  }

  if (!offer) return null;

  return (
    <Modal visible transparent animationType="slide" statusBarTranslucent onRequestClose={() => undefined}>
      <View style={styles.backdrop}>
        <View style={styles.sheet} accessibilityViewIsModal>
          <View style={styles.grabber} />
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.sheetContent}>
          <View style={styles.headingRow}>
            <View style={styles.newJobIcon}><Ionicons name="briefcase" size={25} color="#FFFFFF" /></View>
            <View style={styles.headingText}>
              <Text style={styles.eyebrow}>NEW JOB REQUEST</Text>
              <Text style={styles.title}>You’ve got a job</Text>
            </View>
            <View style={[styles.timer, expired && styles.timerExpired]}>
              <Ionicons name="time-outline" size={16} color={expired ? "#B42332" : "#087653"} />
              <Text style={[styles.timerText, expired && styles.timerTextExpired]}>{formatCountdown(secondsRemaining)}</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel="Close job offer" hitSlop={10} onPress={() => {
              if (offer) handledOfferIds.current.add(String(offer.id));
              setOffer(null);
              setError(null);
            }} style={styles.closeButton}>
              <Ionicons name="close" size={23} color="#64748B" />
            </Pressable>
          </View>

          <View style={styles.jobSummary}>
            <Text style={styles.jobId}>JOB #{offer.job_number ?? offer.id}</Text>
            <Text style={styles.serviceName}>{offer.service_type || offer.title || "Service Request"}</Text>
            <View style={styles.summaryDivider} />
            <View style={styles.infoRow}><Ionicons name="person-outline" size={18} color="#52627E" /><Text style={styles.infoText}>{offer.customer_name || "Customer"}</Text></View>
            <View style={styles.infoRow}><Ionicons name="location-outline" size={18} color="#52627E" /><Text style={styles.infoText}>{offer.location || offer.site_address || offer.address || "Location not provided"}</Text></View>
            {offer.priority ? <View style={styles.priorityPill}><Ionicons name="alert-circle-outline" size={15} color="#B45309" /><Text style={styles.priorityText}>{offer.priority.toUpperCase()} PRIORITY</Text></View> : null}
          </View>

          <View style={styles.prominentInfo}>
            <View style={styles.prominentIcon}><Ionicons name="navigate" size={21} color="#087653" /></View>
            <View style={styles.prominentText}>
              <Text style={styles.infoLabel}>TECHNICIAN LOCATION</Text>
              <Text style={styles.technicianCoordinates}>{technicianLocation ? `${technicianLocation.latitude.toFixed(5)}, ${technicianLocation.longitude.toFixed(5)}` : distanceLoading ? "Getting current location…" : "Location unavailable"}</Text>
              <Text style={[styles.infoLabel, styles.distanceLabel]}>DISTANCE TO CUSTOMER</Text>
              <Text style={styles.distanceValue}>{distanceKm !== null ? `${distanceKm.toFixed(1)} km` : distanceLoading ? "Calculating…" : "Unavailable"}</Text>
            </View>
          </View>

          <View style={[styles.prominentInfo, styles.scheduleInfo]}>
            <View style={[styles.prominentIcon, styles.scheduleIcon]}><Ionicons name="calendar" size={20} color="#72510A" /></View>
            <View style={styles.prominentText}>
              <Text style={styles.infoLabel}>PREFERRED DATE & TIME</Text>
              <Text style={styles.scheduleValue}>{getPreferredDateTime(offer)}</Text>
            </View>
          </View>

          <Text style={styles.prompt}>Can you take this job?</Text>
          {error ? <Text accessibilityRole="alert" style={styles.errorText}>{error}</Text> : null}
          <View style={styles.actions}>
            <Pressable accessibilityRole="button" disabled={busy !== null} onPress={() => void handleOfferAction("reject")} style={({ pressed }) => [styles.declineButton, pressed && styles.buttonPressed, busy !== null && styles.disabled]}>
              {busy === "reject" ? <Text style={styles.declineText}>Rejecting…</Text> : <><Ionicons name="close" size={19} color="#FFFFFF" /><Text style={styles.declineText}>Reject</Text></>}
            </Pressable>
            <Pressable accessibilityRole="button" disabled={busy !== null || expired} onPress={() => void handleOfferAction("accept")} style={({ pressed }) => [styles.acceptButton, pressed && styles.buttonPressed, (busy !== null || expired) && styles.disabled]}>
              {busy === "accept" ? <Text style={styles.acceptText}>Accepting…</Text> : <><Ionicons name="checkmark" size={20} color="#FFFFFF" /><Text style={styles.acceptText}>{expired ? "Offer expired" : "Accept Job"}</Text></>}
            </Pressable>
          </View>
          <Text style={styles.footerNote}>Respond before the timer runs out.</Text>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(15, 23, 42, 0.58)" },
  sheet: { maxHeight: "90%", paddingHorizontal: 20, paddingTop: 12, paddingBottom: 16, backgroundColor: "#FFFFFF", borderTopLeftRadius: 26, borderTopRightRadius: 26 },
  sheetContent: { paddingBottom: 14 },
  grabber: { alignSelf: "center", width: 42, height: 5, borderRadius: 3, backgroundColor: "#D8E1DD", marginBottom: 20 },
  headingRow: { flexDirection: "row", alignItems: "center", gap: 9, marginBottom: 18 },
  newJobIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: "#078A4D" },
  headingText: { flex: 1 },
  eyebrow: { color: "#078A4D", fontSize: 10, fontWeight: "900", letterSpacing: 1.2 },
  title: { color: "#14213D", fontSize: 21, fontWeight: "900", marginTop: 3 },
  timer: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 8, borderRadius: 12, backgroundColor: "#EAF8F0" },
  timerExpired: { backgroundColor: "#FEF2F2" },
  timerText: { color: "#087653", fontSize: 15, fontWeight: "900", fontVariant: ["tabular-nums"] },
  timerTextExpired: { color: "#B42332" },
  closeButton: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", backgroundColor: "#F1F5F4" },
  jobSummary: { padding: 16, borderRadius: 18, borderWidth: 1, borderColor: "#DCECE4", backgroundColor: "#F7FCF9" },
  jobId: { color: "#718096", fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  serviceName: { color: "#14213D", fontSize: 20, fontWeight: "900", marginTop: 4 },
  summaryDivider: { height: 1, backgroundColor: "#E1EBE5", marginVertical: 13 },
  infoRow: { flexDirection: "row", alignItems: "flex-start", gap: 9, marginBottom: 9 },
  infoText: { flex: 1, color: "#52627E", fontSize: 14, lineHeight: 20 },
  preferredDate: { flex: 1 },
  infoLabel: { color: "#718096", fontSize: 9, fontWeight: "900", letterSpacing: 0.7, marginBottom: 3 },
  prominentInfo: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 13, paddingVertical: 10, marginTop: 10, borderRadius: 15, borderWidth: 1, borderColor: "#BCEED8", backgroundColor: "#ECFDF5" },
  prominentIcon: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center", backgroundColor: "#D1FAE5" },
  prominentText: { flex: 1 },
  distanceValue: { color: "#075C43", fontSize: 22, fontWeight: "900", marginTop: 2 },
  technicianCoordinates: { color: "#075C43", fontSize: 14, fontWeight: "800", marginTop: 2 },
  distanceLabel: { marginTop: 9 },
  scheduleInfo: { borderColor: "#F2DEAA", backgroundColor: "#FFFBEB" },
  scheduleIcon: { backgroundColor: "#FEF3C7" },
  scheduleValue: { color: "#45320A", fontSize: 15, lineHeight: 21, fontWeight: "800", marginTop: 2 },
  priorityPill: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 9, paddingVertical: 6, marginTop: 3, borderRadius: 12, backgroundColor: "#FEF3C7" },
  priorityText: { color: "#92400E", fontSize: 10, fontWeight: "900", letterSpacing: 0.4 },
  prompt: { color: "#52627E", fontSize: 14, fontWeight: "700", textAlign: "center", marginTop: 20, marginBottom: 12 },
  actions: { flexDirection: "row", gap: 10 },
  declineButton: { width: "36%", minHeight: 54, borderWidth: 1, borderColor: "#DC2626", borderRadius: 14, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5, backgroundColor: "#DC2626" },
  declineText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  acceptButton: { flex: 1, minHeight: 54, borderRadius: 14, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, backgroundColor: "#078A4D" },
  acceptText: { color: "#FFFFFF", fontSize: 16, fontWeight: "900" },
  buttonPressed: { transform: [{ scale: 0.98 }], opacity: 0.92 },
  disabled: { opacity: 0.55 },
  errorText: { color: "#B42332", fontSize: 13, textAlign: "center", marginBottom: 10 },
  footerNote: { color: "#8A97A2", fontSize: 11, textAlign: "center", marginTop: 12 }
});
