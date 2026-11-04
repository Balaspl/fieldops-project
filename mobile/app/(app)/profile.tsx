import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { useAuthStore } from "../../src/auth/authStore";
import { getTechnicianDashboard } from "../../src/api/dashboard";
import {
  getOrganizationServicesTaxonomy,
  getTechnicianProfile,
  saveTechnicianProfile,
  type ServicesTaxonomy,
  type TechnicianProfile
} from "../../src/api/technicianProfile";
import {
  hasTechnicianLocationConsent,
  setTechnicianLocationConsent,
  startTechnicianLocationTracking,
  stopTechnicianLocationTracking
} from "../../src/gps/backgroundLocationService";
import { logError } from "../../src/observability/logger";

type SectionKey = "personal" | "address" | "employment" | "emergency" | "skills";

const GREEN = "#078A4D";
const DARK_GREEN = "#075B3C";

function emptyProfile(fullName: string): TechnicianProfile {
  return {
    full_name: fullName,
    mobile_number: "",
    skills: [],
    certifications: [],
    profile_completed: false
  };
}

function getDisplayDate(value?: string | null): string {
  if (!value) return "Add your date of birth";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  keyboardType,
  multiline
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address" | "phone-pad" | "numeric";
  multiline?: boolean;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder || `Enter ${label.toLowerCase()}`}
        placeholderTextColor="#9AA99F"
        keyboardType={keyboardType || "default"}
        autoCapitalize={keyboardType === "email-address" ? "none" : "sentences"}
        multiline={multiline}
        textAlignVertical={multiline ? "top" : "center"}
        style={[styles.input, multiline && styles.multilineInput]}
      />
    </View>
  );
}

function ProfileSection({
  icon,
  title,
  subtitle,
  expanded,
  onPress,
  children
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  expanded: boolean;
  onPress: () => void;
  children?: React.ReactNode;
}) {
  return (
    <View style={styles.sectionCard}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded }}
        onPress={onPress}
        style={({ pressed }) => [styles.sectionHeader, pressed && styles.pressed]}
      >
        <View style={styles.sectionIcon}>
          <Ionicons name={icon} size={23} color={GREEN} />
        </View>
        <View style={styles.sectionCopy}>
          <Text style={styles.sectionTitle}>{title}</Text>
          <Text style={styles.sectionSubtitle} numberOfLines={2}>{subtitle}</Text>
        </View>
        <Ionicons name={expanded ? "chevron-up" : "chevron-forward"} size={20} color="#234332" />
      </Pressable>
      {expanded ? <View style={styles.editor}>{children}</View> : null}
    </View>
  );
}

function ProfileSkeleton() {
  const pulse = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.9, duration: 700, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.4, duration: 700, useNativeDriver: true })
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  const block = (style: object) => (
    <Animated.View style={[styles.skeletonBlock, style, { opacity: pulse }]} />
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} accessibilityLabel="Loading profile">
      <View style={styles.skeletonHero}>
        <View style={styles.skeletonNav}>
          {block({ width: 38, height: 38, borderRadius: 13 })}
          {block({ width: 126, height: 22, borderRadius: 8 })}
          {block({ width: 38, height: 38, borderRadius: 13 })}
        </View>
        {block({ width: 82, height: 28, borderRadius: 16 })}
        <View style={styles.skeletonIdentity}>
          {block({ width: 84, height: 84, borderRadius: 42 })}
          <View style={{ flex: 1, gap: 10 }}>
            {block({ width: "78%", height: 21, borderRadius: 7 })}
            {block({ width: "58%", height: 14, borderRadius: 6 })}
          </View>
        </View>
      </View>
      <View style={styles.skeletonStats}>
        {[0, 1, 2, 3].map((item) => (
          <View key={item} style={styles.skeletonStat}>
            {block({ width: 23, height: 23, borderRadius: 8 })}
            {block({ width: "72%", height: 11, borderRadius: 5 })}
            {block({ width: "56%", height: 9, borderRadius: 5 })}
          </View>
        ))}
      </View>
      <View style={styles.skeletonProgress}>
        {block({ width: 58, height: 58, borderRadius: 29 })}
        <View style={{ flex: 1, gap: 9 }}>
          {block({ width: "64%", height: 17, borderRadius: 6 })}
          {block({ width: "88%", height: 12, borderRadius: 5 })}
        </View>
        {block({ width: 17, height: 17, borderRadius: 7 })}
      </View>
      {[0, 1, 2, 3, 4].map((item) => (
        <View key={item} style={styles.skeletonSection}>
          {block({ width: 48, height: 48, borderRadius: 15 })}
          <View style={{ flex: 1, gap: 9 }}>
            {block({ width: "58%", height: 16, borderRadius: 6 })}
            {block({ width: "82%", height: 11, borderRadius: 5 })}
          </View>
          {block({ width: 15, height: 15, borderRadius: 6 })}
        </View>
      ))}
    </ScrollView>
  );
}

export default function ProfileScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const fallbackName = user?.full_name?.trim() ||
    [user?.first_name, user?.last_name].filter(Boolean).join(" ") || "Technician";

  const [profile, setProfile] = useState<TechnicianProfile>(() => emptyProfile(fallbackName));
  const [savedProfile, setSavedProfile] = useState<TechnicianProfile>(() => emptyProfile(fallbackName));
  const [taxonomy, setTaxonomy] = useState<ServicesTaxonomy | null>(null);
  const [technicianStatus, setTechnicianStatus] = useState("Offline");
  const [completedJobs, setCompletedJobs] = useState(0);
  const [expandedSection, setExpandedSection] = useState<SectionKey | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [hasLocationConsent, setHasLocationConsent] = useState(false);
  const [isLoadingConsent, setIsLoadingConsent] = useState(true);
  const [isUpdatingConsent, setIsUpdatingConsent] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.allSettled([
      getTechnicianProfile(),
      getOrganizationServicesTaxonomy(user?.tenant_id),
      getTechnicianDashboard()
    ]).then(([profileResult, taxonomyResult, dashboardResult]) => {
      if (!active) return;
      if (profileResult.status === "fulfilled") {
        const loadedProfile = {
          ...emptyProfile(fallbackName),
          ...profileResult.value,
          skills: profileResult.value.skills || [],
          certifications: profileResult.value.certifications || []
        };
        setProfile(loadedProfile);
        setSavedProfile(loadedProfile);
      }
      if (taxonomyResult.status === "fulfilled") setTaxonomy(taxonomyResult.value);
      if (dashboardResult.status === "fulfilled") {
        const dashboard = dashboardResult.value;
        setTechnicianStatus(String(dashboard.technician_status || "Offline")
          .replace(/_/g, " ")
          .toLowerCase()
          .replace(/\b\w/g, (letter) => letter.toUpperCase()));
        setCompletedJobs(Number(dashboard.total_completed || dashboard.completed_jobs || 0));
      }
      setIsLoading(false);
    });
    return () => { active = false; };
  }, [fallbackName, user?.tenant_id]);

  useEffect(() => {
    let active = true;
    if (user?.id == null || user.tenant_id == null) {
      setIsLoadingConsent(false);
      return () => { active = false; };
    }
    void hasTechnicianLocationConsent({ technicianId: user.id, tenantId: user.tenant_id })
      .then((granted) => { if (active) setHasLocationConsent(granted); })
      .catch((error: unknown) => {
        logError("gps.location_consent_read_failed", error);
        if (active) setHasLocationConsent(false);
      })
      .finally(() => { if (active) setIsLoadingConsent(false); });
    return () => { active = false; };
  }, [user?.id, user?.tenant_id]);

  const allCatalogSkills = useMemo(() => {
    if (!taxonomy) return new Set<string>();
    const values = new Set<string>();
    for (const serviceType of taxonomy.service_types || []) {
      values.add(serviceType);
      for (const category of taxonomy.categories_by_type?.[serviceType] || []) {
        values.add(category);
        for (const issue of taxonomy.issues_by_category?.[category] || []) {
          values.add(typeof issue === "string" ? issue : issue.issue);
        }
      }
    }
    return values;
  }, [taxonomy]);

  const profileCompletion = useMemo(() => {
    const checks = [
      Boolean(profile.full_name.trim()),
      Boolean(profile.mobile_number.trim()),
      Boolean(profile.date_of_birth),
      Boolean(profile.address || profile.city),
      Boolean(profile.emergency_contact),
      profile.skills.length > 0,
      profile.certifications.length > 0,
      Boolean(profile.experience)
    ];
    return Math.round(checks.filter(Boolean).length / checks.length * 100);
  }, [profile]);

  const update = useCallback(<K extends keyof TechnicianProfile>(key: K, value: TechnicianProfile[K]) => {
    setProfile((current) => ({ ...current, [key]: value }));
  }, []);

  const saveSection = useCallback(async () => {
    if (expandedSection === "personal") {
      if (!profile.full_name.trim()) {
        Alert.alert("Name required", "Enter your full name before saving.");
        return;
      }
      if (profile.mobile_number.replace(/\D/g, "").length !== 10) {
        Alert.alert("Check mobile number", "Enter a valid 10-digit mobile number.");
        return;
      }
    }
    setIsSaving(true);
    try {
      const response = await saveTechnicianProfile(
        { ...profile, profile_completed: true },
        !profile.profile_completed
      );
      const saved = {
        ...response,
        skills: response.skills || [],
        certifications: response.certifications || []
      };
      setProfile(saved);
      setSavedProfile(saved);
      setExpandedSection(null);
      Alert.alert("Profile updated", "Your changes have been saved.");
    } catch (error: unknown) {
      logError("technician.profile_save_failed", error);
      Alert.alert("Unable to save profile", "Check your connection and try again.");
    } finally {
      setIsSaving(false);
    }
  }, [expandedSection, profile]);

  const cancelEditing = useCallback(() => {
    setProfile(savedProfile);
    setExpandedSection(null);
  }, [savedProfile]);

  const toggleSkill = useCallback((skill: string) => {
    setProfile((current) => ({
      ...current,
      skills: current.skills.includes(skill)
        ? current.skills.filter((value) => value !== skill)
        : [...current.skills, skill]
    }));
  }, []);

  async function updateLocationConsent(granted: boolean): Promise<void> {
    if (isUpdatingConsent || user?.id == null || user.tenant_id == null) return;
    const identity = { technicianId: user.id, tenantId: user.tenant_id };
    setIsUpdatingConsent(true);
    try {
      if (granted) {
        await setTechnicianLocationConsent(identity, true);
        try {
          await startTechnicianLocationTracking(identity);
        } catch (error: unknown) {
          await setTechnicianLocationConsent(identity, false).catch((rollbackError: unknown) => {
            logError("gps.location_consent_rollback_failed", rollbackError);
          });
          throw error;
        }
        setHasLocationConsent(true);
      } else {
        await setTechnicianLocationConsent(identity, false);
        setHasLocationConsent(false);
        await stopTechnicianLocationTracking();
      }
    } catch (error: unknown) {
      logError("gps.location_consent_update_failed", error);
      Alert.alert("Unable to update location sharing", "Check your device permissions and try again.");
    } finally {
      setIsUpdatingConsent(false);
    }
  }

  function confirmLocationConsentChange(): void {
    const granted = !hasLocationConsent;
    Alert.alert(
      granted ? "Enable background location?" : "Turn off location sharing?",
      granted
        ? "FieldOps uses your location for technician availability and active job tracking while you are signed in."
        : "Background GPS tracking will stop when you withdraw consent.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: granted ? "Enable" : "Turn off",
          style: granted ? "default" : "destructive",
          onPress: () => { void updateLocationConsent(granted); }
        }
      ]
    );
  }

  async function handleLogout(): Promise<void> {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logout();
      router.replace("/(auth)/login");
    } catch {
      Alert.alert("Sign-out issue", "Your session could not be cleared completely. Please try again.");
    } finally {
      setIsLoggingOut(false);
    }
  }

  const setValue = <K extends keyof TechnicianProfile>(key: K, value: string) => {
    update(key, value as TechnicianProfile[K]);
  };
  const skillSummary = profile.skills.slice(0, 3).join(" · ") || "Choose from your organization’s services";
  const locationSummary = [profile.address, profile.city, profile.state, profile.pincode].filter(Boolean).join(", ") || "Add your address and service area";
  const employmentSummary = [skillSummary, profile.experience].filter(Boolean).join(" · ");
  const emergencySummary = profile.emergency_contact || "Add an emergency contact";
  const fullName = profile.full_name || fallbackName;
  const initials = fullName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "T";

  if (isLoading) {
    return <ProfileSkeleton />;
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.hero}>
        <LinearGradient
          colors={["#0B8750", "#05643F", "#03462F"]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
        <View pointerEvents="none" style={styles.heroGlow} />
        <View pointerEvents="none" style={styles.heroOrbit} />
        <View pointerEvents="none" style={styles.heroAccent} />
        <View style={styles.heroNav}>
          <Pressable accessibilityRole="button" accessibilityLabel="Back to dashboard" onPress={() => router.replace("/(app)/dashboard")} style={styles.heroNavButton}>
            <Ionicons name="arrow-back" size={21} color="#FFFFFF" />
          </Pressable>
          <Text style={styles.heroNavTitle}>My Profile</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Open notifications" onPress={() => router.push("/(app)/notifications")} style={styles.heroNavButton}>
            <Ionicons name="notifications-outline" size={21} color="#FFFFFF" />
          </Pressable>
        </View>
        <View style={[styles.onlinePill, technicianStatus.toLowerCase() !== "available" && styles.offlinePill]}>
          <View style={[styles.onlineDot, technicianStatus.toLowerCase() !== "available" && styles.offlineDot]} />
          <Text style={styles.onlineText}>{technicianStatus}</Text>
        </View>
        <View style={styles.identityRow}>
          <View style={styles.avatarWrap}>
            <View style={styles.avatar}><Text style={styles.avatarText}>{initials}</Text></View>
            <View style={styles.avatarCamera}><Ionicons name="camera" size={15} color="#FFFFFF" /></View>
          </View>
          <View style={styles.identityCopy}>
            <View style={styles.nameRow}>
              <Text style={styles.name} numberOfLines={1}>{fullName}</Text>
              <Ionicons name="checkmark-circle" size={20} color="#55E37A" />
            </View>
            <Text style={styles.roleLine}>Technician · {profile.skills[0] || "Add your skills"}</Text>
          </View>
        </View>
      </View>

      <View style={styles.statsCard}>
        <Stat icon="flash" value={profile.skills[0] || "Skills"} label="Specialty" />
        <View style={styles.statDivider} />
        <Stat icon="location" value={profile.city || "Location"} label={profile.state || "Service area"} />
        <View style={styles.statDivider} />
        <Stat icon="briefcase" value={String(completedJobs)} label="Jobs done" />
        <View style={styles.statDivider} />
        <Stat icon="ribbon" value={profile.experience || "Experience"} label="Experience" />
      </View>

      <View style={styles.progressCard}>
        <View style={styles.progressRing}>
          <Text style={styles.progressValue}>{profileCompletion}%</Text>
        </View>
        <View style={styles.progressCopy}>
          <Text style={styles.progressTitle}>Complete your profile</Text>
          <Text style={styles.progressSubtitle}>Add contact details, skills and certifications</Text>
        </View>
        <Ionicons name="chevron-forward" size={21} color="#173B29" />
      </View>

      <ProfileSection icon="person-outline" title="Personal Details" subtitle={[profile.full_name, profile.email || user?.email, profile.mobile_number, profile.date_of_birth, profile.gender].filter(Boolean).join(" · ") || "Name, email, mobile, date of birth, gender"} expanded={expandedSection === "personal"} onPress={() => setExpandedSection(expandedSection === "personal" ? null : "personal")}>
        <Field label="Full name" value={profile.full_name} onChangeText={(value) => setValue("full_name", value)} />
        <Field label="Mobile number" value={profile.mobile_number} onChangeText={(value) => setValue("mobile_number", value.replace(/\D/g, "").slice(0, 10))} keyboardType="phone-pad" />
        <Field label="Date of birth (YYYY-MM-DD)" value={profile.date_of_birth || ""} onChangeText={(value) => setValue("date_of_birth", value)} placeholder="1995-04-23" />
        <Text style={styles.fieldLabel}>Gender</Text>
        <View style={styles.chipWrap}>
          {["Male", "Female", "Other", "Prefer not to say"].map((value) => (
            <ChoiceChip key={value} label={value} selected={profile.gender === value} onPress={() => update("gender", value)} />
          ))}
        </View>
        <View style={styles.readOnlyEmail}><Ionicons name="mail-outline" size={16} color="#6C8374" /><Text style={styles.readOnlyEmailText}>{profile.email || user?.email || "Email unavailable"} · managed by your account</Text></View>
        <SaveControls saving={isSaving} onSave={() => void saveSection()} onCancel={cancelEditing} />
      </ProfileSection>

      <ProfileSection icon="location-outline" title="Address & Location" subtitle={locationSummary} expanded={expandedSection === "address"} onPress={() => setExpandedSection(expandedSection === "address" ? null : "address")}>
        <Field label="Street address" value={profile.address || ""} onChangeText={(value) => setValue("address", value)} multiline />
        <View style={styles.fieldRow}>
          <View style={styles.fieldHalf}><Field label="City" value={profile.city || ""} onChangeText={(value) => setValue("city", value)} /></View>
          <View style={styles.fieldHalf}><Field label="Postal code" value={profile.pincode || ""} onChangeText={(value) => setValue("pincode", value.replace(/\D/g, "").slice(0, 6))} keyboardType="numeric" /></View>
        </View>
        <Field label="State" value={profile.state || ""} onChangeText={(value) => setValue("state", value)} />
        <SaveControls saving={isSaving} onSave={() => void saveSection()} onCancel={cancelEditing} />
      </ProfileSection>

      <ProfileSection icon="briefcase-outline" title="Employment Details" subtitle={employmentSummary || "Service skills, experience and work status"} expanded={expandedSection === "employment"} onPress={() => setExpandedSection(expandedSection === "employment" ? null : "employment")}>
        <Field label="Years of experience" value={profile.experience || ""} onChangeText={(value) => setValue("experience", value)} placeholder="e.g. 5 years" />
        <View style={styles.statusInfo}><Ionicons name="information-circle-outline" size={17} color={GREEN} /><Text style={styles.statusInfoText}>Work status is managed from your dashboard availability control.</Text></View>
        <SaveControls saving={isSaving} onSave={() => void saveSection()} onCancel={cancelEditing} />
      </ProfileSection>

      <ProfileSection icon="call-outline" title="Emergency Contact" subtitle={emergencySummary} expanded={expandedSection === "emergency"} onPress={() => setExpandedSection(expandedSection === "emergency" ? null : "emergency")}>
        <Field label="Emergency contact number" value={profile.emergency_contact || ""} onChangeText={(value) => setValue("emergency_contact", value.replace(/\D/g, "").slice(0, 15))} keyboardType="phone-pad" />
        <SaveControls saving={isSaving} onSave={() => void saveSection()} onCancel={cancelEditing} />
      </ProfileSection>

      <ProfileSection icon="ribbon-outline" title="Skills & Certifications" subtitle={`${profile.skills.length} skills · ${profile.certifications.length} certifications`} expanded={expandedSection === "skills"} onPress={() => setExpandedSection(expandedSection === "skills" ? null : "skills")}>
        <Text style={styles.fieldLabel}>Organization services and skills</Text>
        {!taxonomy || taxonomy.service_types.length === 0 ? (
          <Text style={styles.helperText}>Your organization’s active service catalog is not available right now. Pull to refresh and try again.</Text>
        ) : (
          <View style={styles.serviceList}>
            {taxonomy.service_types.map((serviceType) => (
              <ServiceSkillGroup
                key={serviceType}
                serviceType={serviceType}
                taxonomy={taxonomy}
                selectedSkills={profile.skills}
                onToggle={toggleSkill}
              />
            ))}
          </View>
        )}
        {profile.skills.filter((skill) => !allCatalogSkills.has(skill)).length > 0 ? (
          <View style={styles.existingSkillBox}>
            <Text style={styles.fieldLabel}>Other saved skills</Text>
            <View style={styles.chipWrap}>
              {profile.skills.filter((skill) => !allCatalogSkills.has(skill)).map((skill) => (
                <ChoiceChip key={skill} label={skill} selected onPress={() => toggleSkill(skill)} />
              ))}
            </View>
          </View>
        ) : null}
        <Field label="Certifications (comma separated)" value={profile.certifications.join(", ")} onChangeText={(value) => update("certifications", value.split(",").map((item) => item.trim()).filter(Boolean))} placeholder="Electrical safety, OSHA…" multiline />
        <SaveControls saving={isSaving} onSave={() => void saveSection()} onCancel={cancelEditing} />
      </ProfileSection>

      <View style={styles.locationPanel}>
        <View style={styles.locationPanelHeading}>
          <View style={styles.sectionIcon}><Ionicons name="navigate-outline" size={22} color={GREEN} /></View>
          <View style={styles.sectionCopy}><Text style={styles.sectionTitle}>Location sharing</Text><Text style={styles.sectionSubtitle}>Background GPS for job tracking</Text></View>
          {isLoadingConsent ? <ActivityIndicator size="small" color={GREEN} /> : <View style={[styles.onlineDot, !hasLocationConsent && styles.offlineDot]} />}
        </View>
        <Text style={styles.locationDescription}>{hasLocationConsent ? "Location sharing is enabled while you are signed in." : "Enable location sharing for availability and active job tracking."}</Text>
        <Pressable
          accessibilityRole="button"
          disabled={isLoadingConsent || isUpdatingConsent || user?.id == null || user.tenant_id == null}
          onPress={confirmLocationConsentChange}
          style={({ pressed }) => [styles.consentButton, hasLocationConsent && styles.withdrawButton, pressed && styles.pressed, (isLoadingConsent || isUpdatingConsent) && styles.disabled]}
        >
          {isUpdatingConsent ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.consentButtonText}>{hasLocationConsent ? "Turn off location sharing" : "Enable location sharing"}</Text>}
        </Pressable>
      </View>

      <Pressable accessibilityRole="button" accessibilityLabel="Sign out" disabled={isLoggingOut} onPress={() => void handleLogout()} style={({ pressed }) => [styles.signOutButton, pressed && styles.pressed, isLoggingOut && styles.disabled]}>
        {isLoggingOut ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.signOutText}>Sign out</Text>}
      </Pressable>
    </ScrollView>
  );
}

function Stat({ icon, value, label }: { icon: keyof typeof Ionicons.glyphMap; value: string; label: string }) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon} size={23} color={GREEN} />
      <Text style={styles.statValue} numberOfLines={1}>{value}</Text>
      <Text style={styles.statLabel} numberOfLines={1}>{label}</Text>
    </View>
  );
}

function ChoiceChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} style={[styles.choiceChip, selected && styles.choiceChipSelected]}>
      {selected ? <Ionicons name="checkmark" size={14} color={GREEN} /> : null}
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function ServiceSkillGroup({
  serviceType,
  taxonomy,
  selectedSkills,
  onToggle
}: {
  serviceType: string;
  taxonomy: ServicesTaxonomy;
  selectedSkills: string[];
  onToggle: (skill: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const categories = taxonomy.categories_by_type?.[serviceType] || [];
  return (
    <View style={styles.serviceGroup}>
      <Pressable onPress={() => setExpanded((current) => !current)} style={styles.serviceHeading}>
        <ChoiceChip label={serviceType} selected={selectedSkills.includes(serviceType)} onPress={() => onToggle(serviceType)} />
        <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={17} color="#547363" />
      </Pressable>
      {expanded ? categories.map((category) => {
        const issueItems = taxonomy.issues_by_category?.[category] || [];
        const issues = issueItems.map((issue) => typeof issue === "string" ? issue : issue.issue);
        return (
          <View key={category} style={styles.categoryGroup}>
            <ChoiceChip label={category} selected={selectedSkills.includes(category)} onPress={() => onToggle(category)} />
            <View style={styles.issueList}>
              {issues.map((issue) => (
                <ChoiceChip key={issue} label={issue} selected={selectedSkills.includes(issue)} onPress={() => onToggle(issue)} />
              ))}
            </View>
          </View>
        );
      }) : null}
    </View>
  );
}

function SaveControls({ saving, onSave, onCancel }: { saving: boolean; onSave: () => void; onCancel: () => void }) {
  return (
    <View style={styles.saveRow}>
      <Pressable accessibilityRole="button" onPress={onCancel} disabled={saving} style={styles.cancelButton}><Text style={styles.cancelText}>Cancel</Text></Pressable>
      <Pressable accessibilityRole="button" onPress={onSave} disabled={saving} style={({ pressed }) => [styles.saveButton, pressed && styles.pressed, saving && styles.disabled]}>
        {saving ? <ActivityIndicator size="small" color="#FFFFFF" /> : <Ionicons name="checkmark" size={17} color="#FFFFFF" />}
        <Text style={styles.saveText}>{saving ? "Saving…" : "Save changes"}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F3F7F4" },
  content: { paddingBottom: 36 },
  skeletonHero: { height: 322, paddingHorizontal: 22, paddingTop: 16, paddingBottom: 44, justifyContent: "space-between", backgroundColor: "#DCE8DF", borderBottomLeftRadius: 34, borderBottomRightRadius: 34 },
  skeletonNav: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  skeletonIdentity: { flexDirection: "row", alignItems: "center", gap: 14 },
  skeletonStats: { flexDirection: "row", minHeight: 105, marginHorizontal: 16, marginTop: -33, paddingHorizontal: 8, borderRadius: 22, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "space-around", elevation: 3 },
  skeletonStat: { flex: 1, alignItems: "center", gap: 7 },
  skeletonProgress: { minHeight: 91, flexDirection: "row", alignItems: "center", gap: 13, marginHorizontal: 16, marginTop: 17, marginBottom: 7, padding: 15, borderRadius: 20, backgroundColor: "#FFFFFF", elevation: 2 },
  skeletonSection: { minHeight: 80, flexDirection: "row", alignItems: "center", gap: 12, marginHorizontal: 16, marginTop: 10, paddingHorizontal: 14, paddingVertical: 12, borderRadius: 19, backgroundColor: "#FFFFFF", elevation: 2 },
  skeletonBlock: { backgroundColor: "#C8D8CC" },
  hero: { height: 322, paddingHorizontal: 22, paddingTop: 16, justifyContent: "space-between", overflow: "hidden", backgroundColor: DARK_GREEN, borderBottomLeftRadius: 34, borderBottomRightRadius: 34 },
  heroGlow: { position: "absolute", width: 270, height: 270, borderRadius: 135, top: -126, right: -70, backgroundColor: "rgba(139,239,171,0.16)" },
  heroOrbit: { position: "absolute", width: 240, height: 240, borderRadius: 120, borderWidth: 1, borderColor: "rgba(222,255,233,0.16)", top: 30, right: -60 },
  heroAccent: { position: "absolute", width: 155, height: 155, borderRadius: 78, backgroundColor: "rgba(0,37,25,0.16)", bottom: -96, left: -48 },
  heroNav: { flexDirection: "row", alignItems: "center", gap: 14 },
  heroNavButton: { width: 38, height: 38, alignItems: "center", justifyContent: "center", borderRadius: 13, backgroundColor: "rgba(255,255,255,0.14)" },
  heroNavTitle: { color: "#FFFFFF", fontSize: 21, fontWeight: "900", flex: 1 },
  onlinePill: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 18, backgroundColor: "#DDF8E4" },
  offlinePill: { backgroundColor: "#F1F4F1" },
  onlineDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#12A64A" },
  offlineDot: { backgroundColor: "#95A39A" },
  onlineText: { color: "#14532D", fontSize: 12, fontWeight: "800", textTransform: "capitalize" },
  identityRow: { flexDirection: "row", alignItems: "center", gap: 14, paddingBottom: 44 },
  avatarWrap: { position: "relative" },
  avatar: { width: 88, height: 88, borderRadius: 44, backgroundColor: "#DDF8E7", borderWidth: 4, borderColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  avatarText: { color: DARK_GREEN, fontSize: 29, fontWeight: "900" },
  avatarCamera: { position: "absolute", right: -2, bottom: -1, width: 30, height: 30, borderRadius: 15, backgroundColor: GREEN, borderColor: "#FFFFFF", borderWidth: 2, alignItems: "center", justifyContent: "center" },
  identityCopy: { flex: 1, minWidth: 0 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  name: { color: "#FFFFFF", fontSize: 20, fontWeight: "900", flexShrink: 1 },
  roleLine: { color: "#E2F5E9", fontSize: 13, marginTop: 6 },
  statsCard: { flexDirection: "row", alignItems: "center", marginHorizontal: 16, marginTop: -33, minHeight: 105, borderRadius: 22, backgroundColor: "#FFFFFF", paddingHorizontal: 8, paddingVertical: 13, shadowColor: "#123B2B", shadowOffset: { width: 0, height: 7 }, shadowOpacity: 0.12, shadowRadius: 12, elevation: 4 },
  stat: { flex: 1, alignItems: "center", justifyContent: "center", gap: 4, minWidth: 0 },
  statValue: { color: "#14291E", fontSize: 12, fontWeight: "900", maxWidth: "100%" },
  statLabel: { color: "#66766C", fontSize: 10, textAlign: "center", maxWidth: "100%" },
  statDivider: { width: 1, height: 47, backgroundColor: "#DCE5DE" },
  progressCard: { flexDirection: "row", alignItems: "center", gap: 13, marginHorizontal: 16, marginTop: 17, marginBottom: 7, padding: 15, minHeight: 91, borderRadius: 20, backgroundColor: "#FFFFFF", shadowColor: "#173B2A", shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.07, shadowRadius: 9, elevation: 2 },
  progressRing: { width: 58, height: 58, borderRadius: 29, borderWidth: 5, borderColor: "#19A34A", alignItems: "center", justifyContent: "center", backgroundColor: "#F2FBF4" },
  progressValue: { color: DARK_GREEN, fontSize: 13, fontWeight: "900" },
  progressCopy: { flex: 1 },
  progressTitle: { color: "#16271D", fontSize: 16, fontWeight: "900" },
  progressSubtitle: { color: "#657369", fontSize: 12, lineHeight: 17, marginTop: 4 },
  sectionCard: { marginHorizontal: 16, marginTop: 10, borderRadius: 19, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E7EEE8", shadowColor: "#173B2A", shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.055, shadowRadius: 8, elevation: 2, overflow: "hidden" },
  sectionHeader: { minHeight: 80, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 12 },
  sectionIcon: { width: 48, height: 48, borderRadius: 15, backgroundColor: "#E8F7EA", alignItems: "center", justifyContent: "center" },
  sectionCopy: { flex: 1, minWidth: 0 },
  sectionTitle: { color: "#16271D", fontSize: 16, fontWeight: "900" },
  sectionSubtitle: { color: "#627267", fontSize: 12, lineHeight: 17, marginTop: 3 },
  editor: { borderTopWidth: 1, borderTopColor: "#EAF0EB", paddingHorizontal: 15, paddingTop: 16, paddingBottom: 15 },
  fieldWrap: { marginBottom: 13 },
  fieldLabel: { color: "#3F5547", fontSize: 12, fontWeight: "800", marginBottom: 7 },
  input: { minHeight: 46, borderRadius: 12, borderWidth: 1, borderColor: "#DAE5DC", backgroundColor: "#FBFDFC", paddingHorizontal: 13, color: "#1C3325", fontSize: 14 },
  multilineInput: { minHeight: 76, paddingTop: 12 },
  fieldRow: { flexDirection: "row", gap: 11 },
  fieldHalf: { flex: 1 },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: 12 },
  choiceChip: { flexDirection: "row", alignItems: "center", gap: 5, borderWidth: 1, borderColor: "#DDE8DF", borderRadius: 18, backgroundColor: "#FFFFFF", paddingHorizontal: 11, paddingVertical: 8 },
  choiceChipSelected: { borderColor: "#8DCBA2", backgroundColor: "#EAF8EE" },
  choiceText: { color: "#51665A", fontSize: 12, fontWeight: "700" },
  choiceTextSelected: { color: DARK_GREEN },
  readOnlyEmail: { flexDirection: "row", alignItems: "center", gap: 7, paddingVertical: 9, marginBottom: 6 },
  readOnlyEmailText: { color: "#718278", fontSize: 11, flex: 1 },
  saveRow: { flexDirection: "row", justifyContent: "flex-end", alignItems: "center", gap: 10, marginTop: 7 },
  cancelButton: { paddingHorizontal: 14, paddingVertical: 11 },
  cancelText: { color: "#627267", fontSize: 13, fontWeight: "800" },
  saveButton: { minHeight: 43, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: 12, paddingHorizontal: 15, backgroundColor: GREEN },
  saveText: { color: "#FFFFFF", fontSize: 12, fontWeight: "900" },
  serviceList: { gap: 7, marginTop: 3, marginBottom: 12 },
  serviceGroup: { borderWidth: 1, borderColor: "#E4ECE6", borderRadius: 13, padding: 9, backgroundColor: "#FBFDFC" },
  serviceHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  categoryGroup: { borderTopWidth: 1, borderTopColor: "#EAF0EB", paddingTop: 9, marginTop: 8, gap: 7 },
  issueList: { flexDirection: "row", flexWrap: "wrap", gap: 7, paddingLeft: 7 },
  helperText: { color: "#718278", fontSize: 12, lineHeight: 18, marginBottom: 12 },
  existingSkillBox: { borderTopWidth: 1, borderTopColor: "#E8EFE9", paddingTop: 12, marginBottom: 7 },
  statusInfo: { flexDirection: "row", alignItems: "flex-start", gap: 7, borderRadius: 11, backgroundColor: "#F0F8F2", padding: 11, marginBottom: 10 },
  statusInfoText: { flex: 1, color: "#56705F", fontSize: 11, lineHeight: 16 },
  locationPanel: { marginHorizontal: 16, marginTop: 15, padding: 16, borderRadius: 18, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E4ECE6" },
  locationPanelHeading: { flexDirection: "row", alignItems: "center", gap: 11 },
  locationDescription: { color: "#697A6F", fontSize: 12, lineHeight: 18, marginTop: 12, marginBottom: 13 },
  consentButton: { minHeight: 45, alignItems: "center", justifyContent: "center", borderRadius: 12, backgroundColor: GREEN, paddingHorizontal: 14 },
  withdrawButton: { backgroundColor: "#5D7164" },
  consentButtonText: { color: "#FFFFFF", fontSize: 12, fontWeight: "900" },
  signOutButton: { minHeight: 48, alignItems: "center", justifyContent: "center", marginHorizontal: 16, marginTop: 16, borderRadius: 13, backgroundColor: "#A93C43" },
  signOutText: { color: "#FFFFFF", fontSize: 14, fontWeight: "900" },
  pressed: { opacity: 0.78 },
  disabled: { opacity: 0.55 }
});
