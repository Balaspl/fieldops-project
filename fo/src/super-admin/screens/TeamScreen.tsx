import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  BackHandler,
  ImageBackground,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from 'react-native';
import {
  ArrowLeft,
  BriefcaseBusiness,
  CircleCheck,
  Leaf,
  SlidersHorizontal,
  Users,
  Wifi,
  WifiOff,
  Wrench,
  Mail,
  MapPin,
  PauseCircle,
  Phone,
  Play,
  ShieldCheck,
  HardHat,
  Headset,
  Filter,
  EllipsisVertical,
  ChevronDown,
} from 'lucide-react-native';
import * as Clipboard from 'expo-clipboard';
import { useAuth } from '../auth/AuthContext';
import {
  getDispatchers,
  getTechnicianAssignedJobs,
  getTechnicianById,
  getTechniciansPage,
  provisionOrganizationUser,
  updateTechnicianAvailability,
  type OrganizationUserRole,
} from '../api/operations';
import {
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Pill,
  PrimaryButton,
  ScreenScroll,
  SearchField,
  SectionTitle,
} from '../components/UI';
import { colors } from '../theme';
import { dateTime, initials, statusLabel, statusTone, text, timeAgo } from '../utils/format';

type StaffView = 'technicians' | 'dispatchers';
type TechnicianForm = {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone_number: string;
  role: OrganizationUserRole;
};
type JobFilter = 'ALL' | 'ACTIVE_ONLY' | 'COMPLETED_ONLY' | 'ONHOLD_ONLY';

const EMPTY_FORM: TechnicianForm = {
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  phone_number: '',
  role: 'technician',
};

const ACTIVE_JOB_STATUSES = new Set([
  'ACCEPTED',
  'ENROUTE',
  'ONSITE',
  'INPROGRESS',
  'PAUSED',
  'ONHOLD',
  'HOLD',
  'ESCALATED',
]);
const ON_HOLD_JOB_STATUSES = new Set(['PAUSED', 'ONHOLD', 'HOLD']);
const COMPLETED_JOB_STATUSES = new Set(['COMPLETED', 'CLOSED']);
const LIST_STATUS_FILTERS = ['All', 'Available', 'Busy', 'Offline'];
const TECHNICIAN_PAGE_SIZE = 20;

const normalizeStatus = (value: unknown) =>
  String(value || '').replace(/[_-]+/g, ' ').trim().toLowerCase();

const normalizedJobStatus = (value: unknown) =>
  String(value ?? 'unknown').trim().toUpperCase().replace(/[\s_-]/g, '');

const availabilityLabel = (value: unknown) => {
  const status = normalizeStatus(value);
  if (status === 'available') return 'Online';
  if (status === 'offline') return 'Offline';
  return statusLabel(value);
};

const formatJobDate = (value: unknown) => {
  if (!value) return '—';
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
};

function countTechnicianJobs(jobs: any[]) {
  const counts = { all: jobs.length, active: 0, completed: 0, onHold: 0 };
  for (const job of jobs) {
    const status = normalizedJobStatus(job.status);
    if (COMPLETED_JOB_STATUSES.has(status)) {
      counts.completed += 1;
    } else {
      if (ON_HOLD_JOB_STATUSES.has(status)) counts.onHold += 1;
      if (ACTIVE_JOB_STATUSES.has(status)) counts.active += 1;
    }
  }
  return counts;
}

function priorityTone(value: unknown): 'red' | 'amber' | 'green' | 'neutral' {
  const priority = String(value || '').toUpperCase();
  if (/CRITICAL|HIGH|P1|P2/.test(priority)) return 'red';
  if (/MEDIUM|P3/.test(priority)) return 'amber';
  if (/LOW|P4|P5/.test(priority)) return 'green';
  return 'neutral';
}

function filterJobs(jobs: any[], filter: JobFilter) {
  if (filter === 'ALL') return jobs;
  return jobs.filter(job => {
    const status = normalizedJobStatus(job.status);
    if (filter === 'ACTIVE_ONLY') return ACTIVE_JOB_STATUSES.has(status);
    if (filter === 'COMPLETED_ONLY') return COMPLETED_JOB_STATUSES.has(status);
    return ON_HOLD_JOB_STATUSES.has(status);
  });
}

function SummaryMetric({
  label,
  value,
  tone,
  icon,
  selected,
  onPress,
}: {
  label: string;
  value: number | string;
  tone: 'green' | 'blue' | 'amber';
  icon: React.ReactNode;
  selected?: boolean;
  onPress: () => void;
}) {
  const palette = {
    green: { background: '#EAF7EF', border: '#CDE9D7', color: '#087348' },
    blue: { background: '#EDF4FF', border: '#D5E4FF', color: '#2670D8' },
    amber: { background: '#FFF6E8', border: '#F9E3BF', color: '#D08713' },
  }[tone];

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Show ${label} jobs`}
      onPress={onPress}
      style={({ pressed }) => ({
        flex: 1,
        minWidth: '47%',
        minHeight: 76,
        padding: 11,
        borderRadius: 15,
        borderWidth: selected ? 2 : 1,
        borderColor: selected ? palette.color : palette.border,
        backgroundColor: palette.background,
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        opacity: pressed ? 0.86 : 1,
      })}
    >
      <View style={{ width: 38, height: 38, borderRadius: 20, backgroundColor: 'rgba(255,255,255,.86)', alignItems: 'center', justifyContent: 'center' }}>
        {icon}
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={{ color: '#526276', fontSize: 11, fontWeight: '600' }}>{label}</Text>
        <Text style={{ color: colors.ink, fontSize: 21, lineHeight: 25, fontWeight: '900' }}>{value}</Text>
      </View>
    </Pressable>
  );
}

export default function TeamScreen({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const { role, user } = useAuth();
  const isSuperAdmin = role === 'super_admin';
  const isDispatcher = role === 'dispatcher';
  const organizationId = String(user?.tenant_id || '');

  const [view, setView] = useState<StaffView>('technicians');
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [dispatchers, setDispatchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [filterModalVisible, setFilterModalVisible] = useState(false);
  const [showDeactivatedTechnicians, setShowDeactivatedTechnicians] = useState(false);
  const [updatingTechnicianId, setUpdatingTechnicianId] = useState<string | null>(null);
  const [technicianPage, setTechnicianPage] = useState(1);
  const [technicianTotal, setTechnicianTotal] = useState(0);
  const [hasMoreTechnicians, setHasMoreTechnicians] = useState(false);
  const [loadingMoreTechnicians, setLoadingMoreTechnicians] = useState(false);
  const technicianPageRef = useRef(1);
  const directoryRequestRef = useRef(0);

  const [selectedTechnician, setSelectedTechnician] = useState<any | null>(null);
  const selectedTechnicianIdRef = useRef<number | string | null>(null);
  const [technicianDetails, setTechnicianDetails] = useState<any | null>(null);
  const [assignedJobs, setAssignedJobs] = useState<any[]>([]);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState('');
  const [jobsError, setJobsError] = useState('');
  const [detailRefreshing, setDetailRefreshing] = useState(false);
  const [jobFilter, setJobFilter] = useState<JobFilter>('ALL');

  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [credentials, setCredentials] = useState<{ name: string; email: string; password: string; role: OrganizationUserRole } | null>(null);
  const [form, setForm] = useState<TechnicianForm>(EMPTY_FORM);

  const technicianQuery = useCallback((page: number) => ({
    search: debouncedSearch || undefined,
    // The backend stores availability as Available / Offline.
    // Deactivated technicians are retrieved using their dedicated status.
    status: showDeactivatedTechnicians
      ? 'DEACTIVATED'
      : statusFilter === 'Available'
        ? 'Available'
        : statusFilter === 'Busy'
          ? 'Busy'
          : statusFilter === 'Offline'
            ? 'Offline'
            : undefined,
    page,
    limit: TECHNICIAN_PAGE_SIZE,
  }), [debouncedSearch, statusFilter, showDeactivatedTechnicians]);

  const load = useCallback(async (silent = false, preserveLoadedPages = false) => {
    const requestId = ++directoryRequestRef.current;
    const pagesToLoad = preserveLoadedPages ? Math.max(1, technicianPageRef.current) : 1;
    setLoadingMoreTechnicians(false);
    if (!preserveLoadedPages) {
      technicianPageRef.current = 1;
      setTechnicianPage(1);
      setHasMoreTechnicians(false);
    }
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const [technicianPages, dispatcherRows] = await Promise.all([
        Promise.all(Array.from({ length: pagesToLoad }, (_, index) => getTechniciansPage(technicianQuery(index + 1)))),
        isSuperAdmin ? getDispatchers() : Promise.resolve([]),
      ]);
      if (requestId !== directoryRequestRef.current) return;

      const techRows = technicianPages.flatMap(result => result.items);
      const total = technicianPages[0]?.total ?? techRows.length;
      setTechnicians(techRows);
      setTechnicianTotal(total);
      technicianPageRef.current = pagesToLoad;
      setTechnicianPage(pagesToLoad);
      setHasMoreTechnicians(techRows.length < total);
      setDispatchers(dispatcherRows);
      setSelectedTechnician((current: any) => {
        if (!current) return current;
        return techRows.find((row: any) => String(row.technician_id) === String(current.technician_id)) || current;
      });
    } catch (e: any) {
      if (requestId === directoryRequestRef.current) {
        setError(e?.response?.data?.detail || e?.message || 'Could not load staff records.');
      }
    } finally {
      if (requestId === directoryRequestRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [isSuperAdmin, technicianQuery]);

  const loadMoreTechnicians = useCallback(async () => {
    if (loadingMoreTechnicians || !hasMoreTechnicians) return;

    const nextPage = technicianPageRef.current + 1;
    const requestId = directoryRequestRef.current;
    setLoadingMoreTechnicians(true);
    setError('');
    try {
      const result = await getTechniciansPage(technicianQuery(nextPage));
      // Ignore a stale page response if search/status was changed while it loaded.
      if (requestId !== directoryRequestRef.current) return;

      setTechnicians(current => {
        const seen = new Set(current.map((row: any) => String(row.technician_id)));
        return [...current, ...result.items.filter((row: any) => !seen.has(String(row.technician_id)))];
      });
      setTechnicianTotal(result.total);
      technicianPageRef.current = nextPage;
      setTechnicianPage(nextPage);
      setHasMoreTechnicians(nextPage * TECHNICIAN_PAGE_SIZE < result.total);
    } catch (e: any) {
      if (requestId === directoryRequestRef.current) {
        setError(e?.response?.data?.detail || e?.message || 'Could not load more technicians.');
      }
    } finally {
      if (requestId === directoryRequestRef.current) setLoadingMoreTechnicians(false);
    }
  }, [hasMoreTechnicians, loadingMoreTechnicians, technicianQuery]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (!selectedTechnician) void load(true, true);
    }, 30000);
    return () => clearInterval(timer);
  }, [load, selectedTechnician?.technician_id]);

  const rows = useMemo(() => {
    if (view === 'technicians') return technicians;

    const source = dispatchers;
    const term = search.trim().toLowerCase();
    return source.filter((row: any) => !term || [
        row.technician_name,
        row.name,
        row.email,
        row.technician_skill,
        row.technician_location,
        row.phone_number,
      ].some(value => String(value || '').toLowerCase().includes(term)));
  }, [view, technicians, dispatchers, search]);

  const selectedId = selectedTechnician?.technician_id;
  const profile = technicianDetails || selectedTechnician || {};
  const jobCounts = useMemo(() => countTechnicianJobs(assignedJobs), [assignedJobs]);
  const visibleJobs = useMemo(() => filterJobs(assignedJobs, jobFilter), [assignedJobs, jobFilter]);
  const workloadLimit = Number(profile.max_jobs ?? selectedTechnician?.max_jobs ?? 5) || 5;
  const activeWorkload = Math.min(jobCounts.active, workloadLimit);

  const loadTechnicianProfile = useCallback(async (technicianId: number | string, silent = false) => {
    if (!silent) setDetailsLoading(true);
    try {
      const response = await getTechnicianById(technicianId);
      if (String(selectedTechnicianIdRef.current) === String(technicianId)) {
        setTechnicianDetails(response);
        setDetailsError('');
      }
    } catch (e: any) {
      if (String(selectedTechnicianIdRef.current) === String(technicianId)) {
        setDetailsError(e?.response?.data?.detail || e?.message || 'Could not load technician details.');
      }
    } finally {
      if (!silent) setDetailsLoading(false);
    }
  }, []);

  const loadTechnicianJobs = useCallback(async (technicianId: number | string, silent = false) => {
    if (!silent) setJobsLoading(true);
    try {
      // Same tenant-scoped query used by the web technician dashboard.
      const rowsForTechnician = await getTechnicianAssignedJobs(technicianId);
      if (String(selectedTechnicianIdRef.current) === String(technicianId)) {
        setAssignedJobs(rowsForTechnician);
        setJobsError('');
      }
    } catch (e: any) {
      if (String(selectedTechnicianIdRef.current) === String(technicianId)) {
        setJobsError(e?.response?.data?.detail || e?.response?.data?.error || e?.message || "Unable to load this technician's assigned jobs.");
      }
    } finally {
      if (!silent) setJobsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId === undefined || selectedId === null) {
      setTechnicianDetails(null);
      setAssignedJobs([]);
      setDetailsError('');
      setJobsError('');
      setJobFilter('ALL');
      return;
    }

    setTechnicianDetails(null);
    setAssignedJobs([]);
    setDetailsError('');
    setJobsError('');
    setJobFilter('ALL');
    void loadTechnicianProfile(selectedId);
    void loadTechnicianJobs(selectedId);
  }, [selectedId, loadTechnicianProfile, loadTechnicianJobs]);

  useEffect(() => {
    if (selectedId === undefined || selectedId === null) return;
    const jobsTimer = setInterval(() => void loadTechnicianJobs(selectedId, true), 3000);
    const profileTimer = setInterval(() => void loadTechnicianProfile(selectedId, true), 30000);
    return () => {
      clearInterval(jobsTimer);
      clearInterval(profileTimer);
    };
  }, [selectedId, loadTechnicianJobs, loadTechnicianProfile]);

  const goBackToDirectory = useCallback(() => {
    selectedTechnicianIdRef.current = null;
    setSelectedTechnician(null);
    setTechnicianDetails(null);
    setAssignedJobs([]);
    setJobFilter('ALL');
    // Restore the shared StaffShell header when returning to the directory.
    onNavigate('team');
  }, [onNavigate]);

  useEffect(() => {
    if (selectedId === undefined || selectedId === null) return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      goBackToDirectory();
      return true;
    });
    return () => subscription.remove();
  }, [selectedId, goBackToDirectory]);

  const openTechnicianDetails = (technician: any) => {
    selectedTechnicianIdRef.current = technician.technician_id;
    setSelectedTechnician(technician);
    setTechnicianDetails(null);
    setAssignedJobs([]);
    setJobFilter('ALL');
    // Tell StaffShell to hide its global brand/profile header for this full-screen detail view.
    onNavigate('technician-details');
  };

  const startCreate = () => {
    if (!organizationId || organizationId === '__platform__') {
      Alert.alert('Organization required', 'A valid organization ID is required to create staff accounts.');
      return;
    }
    setForm({ ...EMPTY_FORM, role: 'technician' });
    setFormOpen(true);
  };

  const saveTechnician = async () => {
    if (!form.first_name.trim() || !form.last_name.trim() || !form.email.trim() || !form.password || !form.phone_number.trim()) {
      Alert.alert('Required information', 'Enter first name, last name, email, password and phone number.');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) {
      Alert.alert('Invalid email', 'Enter a valid email address.');
      return;
    }
    if (!/^\d{10}$/.test(form.phone_number.trim())) {
      Alert.alert('Invalid phone number', 'Enter a mobile number with exactly 10 digits.');
      return;
    }
    if (form.password.length < 8) {
      Alert.alert('Invalid password', 'Password must contain at least 8 characters.');
      return;
    }
    if (isDispatcher && form.role === 'dispatcher') {
      Alert.alert('Permission denied', 'Dispatchers cannot create another dispatcher.');
      return;
    }
    if (!organizationId || organizationId === '__platform__') {
      Alert.alert('Organization required', 'A valid organization ID is required to create staff accounts.');
      return;
    }

    setSubmitting(true);
    try {
      const email = form.email.trim().toLowerCase();
      const name = `${form.first_name.trim()} ${form.last_name.trim()}`;
      const selectedRole = form.role;
      await provisionOrganizationUser(organizationId, {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email,
        password: form.password,
        phone_number: form.phone_number.trim(),
        role: selectedRole,
      });
      setFormOpen(false);
      setForm(EMPTY_FORM);
      setCredentials({ name, email, password: form.password, role: selectedRole });
      await load(true);
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'Staff account could not be created.';
      Alert.alert('Staff creation failed', typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setSubmitting(false);
    }
  };

  const refreshCurrentScreen = async () => {
    if (selectedId !== undefined && selectedId !== null) {
      setDetailRefreshing(true);
      await Promise.all([
        loadTechnicianProfile(selectedId, true),
        loadTechnicianJobs(selectedId, true),
      ]);
      setDetailRefreshing(false);
    } else {
      await load(true);
    }
  };

  // Updates the technician lifecycle status through the existing backend.
  const updateTechnicianLifecycleStatus = async (
    technician: any,
    nextStatus: 'Deactivated' | 'Offline',
  ) => {
    const technicianId = technician.technician_id;
    const technicianName = text(technician.technician_name, 'Technician');
    setUpdatingTechnicianId(String(technicianId));

    try {
      await updateTechnicianAvailability(technicianId, nextStatus);

      if (String(selectedTechnicianIdRef.current) === String(technicianId)) {
        selectedTechnicianIdRef.current = null;
        setSelectedTechnician(null);
        setTechnicianDetails(null);
        setAssignedJobs([]);
        setJobFilter('ALL');
        onNavigate('team');
      }

      await load(true);

      Alert.alert(
        nextStatus === 'Deactivated' ? 'Technician deactivated' : 'Technician reactivated',
        nextStatus === 'Deactivated'
          ? `${technicianName} has been moved to Deactivated Technicians. Their record and job history have been kept.`
          : `${technicianName} has been reactivated with Offline status.`,
      );
    } catch (e: any) {
      const message = e?.response?.data?.detail || e?.response?.data?.error || e?.message || 'Could not update technician status.';
      Alert.alert('Technician status update failed', String(message));
    } finally {
      setUpdatingTechnicianId(null);
    }
  };

  // Ask for confirmation before deactivation, matching the web application.
  const confirmDeactivateTechnician = (technician: any) => {
    const technicianName = text(technician.technician_name, 'this technician');

    Alert.alert(
      'Deactivate technician?',
      `Deactivate “${technicianName}”? Their record and job history will be kept. You can reactivate them from Deactivated Technicians.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Deactivate',
          style: 'destructive',
          onPress: () => void updateTechnicianLifecycleStatus(technician, 'Deactivated'),
        },
      ],
      { cancelable: true },
    );
  };

  const toggleDeactivatedTechnicians = () => {
    setShowDeactivatedTechnicians(current => !current);
    setSearch('');
    setDebouncedSearch('');
    setStatusFilter('All');
  };

  const availableCount = technicians.filter((item: any) =>
    normalizeStatus(item.technician_status || item.status) === 'available'
  ).length;
  const offlineCount = technicians.filter((item: any) =>
    normalizeStatus(item.technician_status || item.status) === 'offline'
  ).length;

  const busyCount = technicians.filter((item: any) =>
    normalizeStatus(item.technician_status || item.status) === 'busy'
  ).length;

  const renderTechnicianDirectory = () => (
    <ImageBackground
      source={require('../../../assets/team/nature_team_background.png')}
      resizeMode="cover"
      imageStyle={{ opacity: 1 }}
      style={{ flex: 1, backgroundColor: '#E8F1E6' }}
    >
      <ScrollView
        style={{ flex: 1, backgroundColor: 'transparent' }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor="#145C3B" />
        }
        contentContainerStyle={{
          paddingHorizontal: 14,
          paddingTop: 14,
          paddingBottom: 34,
          gap: 13,
          backgroundColor: 'transparent',
        }}
      >
        {/* Title and staff actions */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: 3, paddingVertical: 5 }}>
          <View style={{ flex: 1, gap: 4 }}>
            <Text style={{ color: '#103F2B', fontSize: 27, fontWeight: '900', letterSpacing: -0.8 }}>
              {view === 'technicians' && showDeactivatedTechnicians ? 'Deactivated' : view === 'technicians' ? 'Technicians' : 'Dispatchers'}
            </Text>
            <Text style={{ color: '#244F3A', fontSize: 12, fontWeight: '600' }}>
              {view === 'technicians' ? 'Manage your field technicians' : 'Manage your dispatch team'}
            </Text>
          </View>
          {view === 'technicians' ? (
            <Pressable
              onPress={toggleDeactivatedTechnicians}
              style={{ minHeight: 42, paddingHorizontal: 13, borderRadius: 24, borderWidth: 1.4, borderColor: '#4F8C59', backgroundColor: 'rgba(247,252,239,0.94)', alignItems: 'center', justifyContent: 'center' }}
            >
              <Text style={{ color: '#174D32', fontSize: 11, fontWeight: '900' }}>{showDeactivatedTechnicians ? 'Active team' : 'Deactivated'}</Text>
            </Pressable>
          ) : null}
          {!(view === 'technicians' && showDeactivatedTechnicians) ? (
            <Pressable
              onPress={startCreate}
              style={{ minHeight: 44, paddingHorizontal: 15, borderRadius: 24, backgroundColor: '#075B36', borderWidth: 1, borderColor: '#2F8B4D', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, elevation: 2 }}
            >
              <Text style={{ color: '#FFFFFF', fontSize: 12, fontWeight: '900' }}>＋ Add Staff</Text>
            </Pressable>
          ) : null}
        </View>

        {/* Three color-coded team metrics */}
        {view === 'technicians' && !showDeactivatedTechnicians ? (
          <View style={{ flexDirection: 'row', gap: 8 }}>
            <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,255,255,0.94)', borderRadius: 19, borderWidth: 1, borderColor: '#CFE3D0', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
              <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#E2F3E3', alignItems: 'center', justifyContent: 'center' }}>
                <Users size={23} color="#075B36" />
              </View>
              <View style={{ flex: 1, gap: 1 }}>
                <Text style={{ color: '#073F27', fontSize: 23, fontWeight: '900' }}>{technicianTotal}</Text>
                <Text style={{ color: '#244F3A', fontSize: 10, fontWeight: '800' }}>Total team</Text>
              </View>
            </View>
            <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(229,248,220,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#C7E5B9', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
              <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#D7F0CB', alignItems: 'center', justifyContent: 'center' }}>
                <Wifi size={23} color="#16813C" />
              </View>
              <View style={{ flex: 1, gap: 1 }}>
                <Text style={{ color: '#16813C', fontSize: 23, fontWeight: '900' }}>{availableCount}</Text>
                <Text style={{ color: '#285B35', fontSize: 10, fontWeight: '800' }}>Available</Text>
              </View>
            </View>
            <View style={{ flex: 1, minHeight: 76, backgroundColor: 'rgba(255,235,229,0.96)', borderRadius: 19, borderWidth: 1, borderColor: '#F0D0C8', padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, elevation: 2 }}>
              <View style={{ width: 39, height: 39, borderRadius: 14, backgroundColor: '#FBE0D9', alignItems: 'center', justifyContent: 'center' }}>
                <WifiOff size={23} color="#D52D2D" />
              </View>
              <View style={{ flex: 1, gap: 1 }}>
                <Text style={{ color: '#A52222', fontSize: 23, fontWeight: '900' }}>{offlineCount}</Text>
                <Text style={{ color: '#80413C', fontSize: 10, fontWeight: '800' }}>Offline</Text>
              </View>
            </View>
          </View>
        ) : null}

        {/* Technician / dispatcher switch */}
        {isSuperAdmin ? (
          <View style={{ flexDirection: 'row', backgroundColor: 'rgba(223,241,215,0.94)', padding: 3, borderRadius: 28, gap: 3, borderWidth: 1, borderColor: '#D1E5C9' }}>
            {(['technicians', 'dispatchers'] as const).map(tab => {
              const active = view === tab;
              return (
                <Pressable
                  key={tab}
                  onPress={() => { setView(tab); setSearch(''); setStatusFilter('All'); }}
                  style={{ flex: 1, minHeight: 48, borderRadius: 25, backgroundColor: active ? '#075B36' : 'transparent', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 7, elevation: active ? 2 : 0 }}
                >
                  {tab === 'technicians' ? <HardHat size={20} color={active ? '#FFFFFF' : '#12482F'} /> : <Headset size={20} color={active ? '#FFFFFF' : '#12482F'} />}
                  <Text style={{ color: active ? '#FFFFFF' : '#12482F', fontSize: 12, fontWeight: '900' }}>
                    {tab === 'technicians' ? 'Technicians' : 'Dispatchers'}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}

        {/* Search and filter action */}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ flex: 1 }}>
            <SearchField
              value={search}
              onChangeText={setSearch}
              placeholder={view === 'technicians' ? 'Search name, skill or location...' : 'Search dispatchers...'}
            />
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open technician availability filters"
            onPress={() => setFilterModalVisible(true)}
            style={{ minWidth: 82, height: 48, paddingHorizontal: 12, borderRadius: 25, backgroundColor: 'rgba(231,247,215,0.96)', borderWidth: 1.2, borderColor: '#9CCB7F', alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 6 }}
          >
            <Filter size={18} color="#164C2F" />
            <Text style={{ color: '#164C2F', fontSize: 11, fontWeight: '900' }}>Filter</Text>
          </Pressable>
        </View>

        {/* Availability chips */}
        {view === 'technicians' && !showDeactivatedTechnicians ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7, paddingRight: 3 }}>
            {[
              { key: 'All', label: `All (${technicianTotal})`, dot: '#075B36', bg: '#075B36', fg: '#FFFFFF' },
              { key: 'Available', label: `Available (${availableCount})`, dot: '#20A83B', bg: 'rgba(234,249,225,0.96)', fg: '#15582D' },
              { key: 'Busy', label: `Busy (${busyCount})`, dot: '#F59E0B', bg: 'rgba(255,244,218,0.97)', fg: '#92510A' },
              { key: 'Offline', label: `Offline (${offlineCount})`, dot: '#E32929', bg: 'rgba(255,232,229,0.97)', fg: '#962727' },
            ].map(filter => {
              const active = statusFilter === filter.key;
              return (
                <Pressable
                  key={filter.key}
                  onPress={() => setStatusFilter(filter.key)}
                  style={{ minHeight: 37, paddingHorizontal: 13, borderRadius: 22, backgroundColor: active && filter.key === 'All' ? '#075B36' : filter.bg, borderWidth: 1, borderColor: active ? '#2C8B45' : 'rgba(190,216,185,0.85)', flexDirection: 'row', alignItems: 'center', gap: 6, elevation: active ? 2 : 0 }}
                >
                  {filter.key !== 'All' ? <View style={{ width: 9, height: 9, borderRadius: 5, backgroundColor: filter.dot }} /> : null}
                  <Text style={{ color: filter.fg, fontSize: 10, fontWeight: '900' }}>{filter.label}</Text>
                </Pressable>
              );
            })}
          </ScrollView>
        ) : null}

        {/* Directory heading */}
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 2, paddingTop: 2 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
            <Leaf size={22} color="#3C8A38" fill="#7CBF48" />
            <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>
              {view === 'technicians' ? (showDeactivatedTechnicians ? 'Deactivated Technicians' : 'Technicians') : 'Dispatcher Directory'}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <Text style={{ color: '#153F2C', fontSize: 10, fontWeight: '900' }}>Sort: Name</Text>
            <ChevronDown size={15} color="#153F2C" />
          </View>
        </View>

        {error ? <ErrorBanner message={error} /> : null}
        {loading ? (
          <Text style={{ textAlign: 'center', color: '#718277', padding: 24 }}>Loading staff...</Text>
        ) : rows.length === 0 ? (
          <EmptyState
            title={`No ${view} found`}
            detail={showDeactivatedTechnicians
              ? 'No deactivated technicians found.'
              : search || statusFilter !== 'All'
                ? 'Try another search or availability filter.'
                : 'Staff records will appear here when available.'}
            onRetry={() => load(true)}
          />
        ) : view === 'technicians' ? (
          rows.map((item: any) => {
            const technicianStatus = item.technician_status || item.status;
            const displayedStatus = availabilityLabel(technicianStatus);
            const workload = Math.max(0, Number(item.current_jobs ?? 0));
            const maxJobs = Math.max(1, Number(item.max_jobs ?? 5));
            const progress = Math.min(100, (workload / maxJobs) * 100);
            const actionBusy = updatingTechnicianId === String(item.technician_id);
            const isOnline = normalizeStatus(technicianStatus) === 'available';
            const isBusy = normalizeStatus(technicianStatus) === 'busy';
            const location = text(item.technician_location, 'Location not set');
            const statusColor = isOnline ? '#16813C' : isBusy ? '#C27A0A' : '#D52D2D';
            const statusBg = isOnline ? '#E6F7DF' : isBusy ? '#FFF0D4' : '#FCE7E4';

            return (
              <Card
                key={String(item.technician_id)}
                style={{ padding: 11, borderRadius: 21, borderColor: '#D8E8D4', borderLeftWidth: 5, borderLeftColor: showDeactivatedTechnicians ? '#9AA69D' : isOnline ? '#3ABF32' : isBusy ? '#F4A51C' : '#F05B61', backgroundColor: 'rgba(255,255,255,0.95)', gap: 8, shadowColor: '#17432B', shadowOpacity: 0.10, shadowRadius: 6, shadowOffset: { width: 0, height: 3 }, elevation: 3 }}
              >
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={`View ${text(item.technician_name, 'technician')} details`}
                    onPress={() => openTechnicianDetails(item)}
                    style={{ flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 9 }}
                  >
                    <View style={{ width: 54, height: 54, borderRadius: 17, backgroundColor: '#DDF4C9', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                      <Text style={{ color: '#064522', fontWeight: '900', fontSize: 19 }}>{initials(item.technician_name)}</Text>
                      <View style={{ position: 'absolute', left: -3, bottom: -3, width: 21, height: 21, borderRadius: 11, backgroundColor: '#DDF4C9', alignItems: 'center', justifyContent: 'center' }}>
                        <Leaf size={16} color="#65A832" fill="#65A832" strokeWidth={1.8} />
                      </View>
                    </View>
                    <View style={{ flex: 1, minWidth: 0, gap: 3 }}>
                      <Text numberOfLines={1} style={{ color: '#101C15', fontSize: 14, fontWeight: '900' }}>{text(item.technician_name, 'Technician')}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                        <Wrench size={12} color="#315C45" />
                        <Text numberOfLines={1} style={{ color: '#30483A', fontSize: 10, flex: 1 }}>{text(item.technician_skill, 'Skill not set')}</Text>
                      </View>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                        <MapPin size={12} color="#315C45" />
                        <Text numberOfLines={1} style={{ color: '#607367', fontSize: 10, flex: 1 }}>{location}</Text>
                      </View>
                    </View>
                  </Pressable>

                  <View style={{ alignItems: 'center', minWidth: 68, gap: 4 }}>
                    <View style={{ paddingHorizontal: 8, paddingVertical: 6, borderRadius: 20, backgroundColor: statusBg, flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                      <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: statusColor }} />
                      <Text style={{ color: statusColor, fontSize: 9, fontWeight: '900' }}>{displayedStatus}</Text>
                    </View>
                    <Text style={{ color: '#5E7065', fontSize: 9, fontWeight: '700' }}>Status</Text>
                  </View>

                  <View style={{ width: 82, borderLeftWidth: 1, borderLeftColor: '#D6E4D6', paddingLeft: 8, gap: 3 }}>
                    <Text style={{ color: '#415B4A', fontSize: 9 }}>Workload</Text>
                    <Text style={{ color: '#101C15', fontSize: 12, fontWeight: '900' }}>{workload} / {maxJobs} Jobs</Text>
                    <View style={{ height: 7, borderRadius: 8, backgroundColor: '#DFE7E0', overflow: 'hidden', marginTop: 2 }}>
                      <View style={{ width: `${progress}%`, height: 7, borderRadius: 8, backgroundColor: '#32B72D' }} />
                    </View>
                  </View>

                </View>

                <View style={{ flexDirection: 'row', justifyContent: 'flex-end', paddingTop: 2 }}>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={showDeactivatedTechnicians ? `Reactivate ${text(item.technician_name, 'technician')}` : `Deactivate ${text(item.technician_name, 'technician')}`}
                    disabled={actionBusy}
                    onPress={() => showDeactivatedTechnicians
                      ? void updateTechnicianLifecycleStatus(item, 'Offline')
                      : confirmDeactivateTechnician(item)}
                    style={{
                      minWidth: 112,
                      minHeight: 38,
                      paddingHorizontal: 16,
                      paddingVertical: 9,
                      borderRadius: 12,
                      alignItems: 'center',
                      justifyContent: 'center',
                      backgroundColor: showDeactivatedTechnicians ? '#E4F3E7' : '#FFF0EE',
                      borderWidth: 1,
                      borderColor: showDeactivatedTechnicians ? '#9BCBA5' : '#F0B8B3',
                      opacity: actionBusy ? 0.5 : 1,
                    }}
                  >
                    <Text style={{ color: showDeactivatedTechnicians ? '#17643B' : '#B33B36', fontSize: 12, fontWeight: '900' }}>
                      {actionBusy ? 'Please wait...' : showDeactivatedTechnicians ? 'Reactivate' : 'Deactivate'}
                    </Text>
                  </Pressable>
                </View>
              </Card>
            );
          })
        ) : (
          rows.map((item: any) => (
            <Card key={String(item.id)} style={{ gap: 10, padding: 14, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.94)', borderColor: '#CFE1D0' }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <View style={{ flex: 1, gap: 3 }}>
                  <Text style={{ color: '#173D2B', fontSize: 14, fontWeight: '900' }}>{item.name || `${item.first_name || ''} ${item.last_name || ''}`}</Text>
                  <Text style={{ color: '#718277', fontSize: 11 }}>{text(item.email)}</Text>
                </View>
                <Pill label={item.is_active ? 'Active' : 'Inactive'} tone={item.is_active ? 'green' : 'red'} />
              </View>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
                <Text style={{ color: '#52675A', fontSize: 11 }}>{text(item.phone_number)}</Text>
                <Text style={{ color: '#718277', fontSize: 10 }}>{item.is_on_duty ? 'On duty' : 'Off duty'}</Text>
              </View>
              <Text style={{ color: '#829087', fontSize: 10 }}>Last login: {dateTime(item.last_login)}</Text>
            </Card>
          ))
        )}

        {view === 'technicians' && technicians.length > 0 ? (
          <Text style={{ color: '#829087', fontSize: 10, textAlign: 'center' }}>
            Showing {technicians.length} of {technicianTotal} {showDeactivatedTechnicians ? 'deactivated ' : ''}technicians · Page {technicianPage}
          </Text>
        ) : null}
        {view === 'technicians' && hasMoreTechnicians ? (
          <PrimaryButton
            title={loadingMoreTechnicians ? 'Loading technicians...' : 'Load more technicians'}
            compact variant="secondary" loading={loadingMoreTechnicians}
            onPress={() => void loadMoreTechnicians()}
            style={{ backgroundColor: '#E5F0E4', borderColor: '#CFE1D0' }}
          />
        ) : null}
      </ScrollView>
    </ImageBackground>
  );
  const renderTechnicianDetails = () => (
    <ScreenScroll
      refreshControl={<RefreshControl refreshing={detailRefreshing} onRefresh={refreshCurrentScreen} tintColor={colors.forest} />}
      contentContainerStyle={{ padding: 16, paddingBottom: 30, gap: 16 }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable onPress={goBackToDirectory} accessibilityRole="button" accessibilityLabel="Back to technicians" style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: '#E5F1E9', alignItems: 'center', justifyContent: 'center' }}>
          <ArrowLeft size={21} color={colors.forest} />
        </Pressable>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={{ color: colors.ink, fontSize: 21, fontWeight: '900' }}>Technician Details</Text>
          <Text style={{ color: colors.muted, fontSize: 11 }}>Profile and assigned job summary</Text>
        </View>
      </View>

      <ImageBackground
        source={require('../../../assets/services/technician_banner.png')}
        resizeMode="cover"
        imageStyle={{ borderRadius: 20 }}
        style={{ minHeight: 206, borderRadius: 20, overflow: 'hidden', padding: 16, justifyContent: 'space-between', backgroundColor: colors.forestDark }}
      >
        <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(0,48,28,.38)' }} />
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={{ width: 58, height: 58, borderRadius: 30, borderWidth: 2, borderColor: '#D9F7E5', backgroundColor: 'rgba(255,255,255,.12)', alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: colors.white, fontSize: 19, fontWeight: '900' }}>{initials(profile.technician_name || selectedTechnician?.technician_name)}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0, gap: 5 }}>
            <Text numberOfLines={2} style={{ color: colors.white, fontSize: 18, fontWeight: '900' }}>{text(profile.technician_name, 'Technician')}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Text style={{ color: '#E1F4E8', fontSize: 11, fontWeight: '700' }}>Technician</Text>
              <Pill label={availabilityLabel(profile.technician_status || selectedTechnician?.technician_status)} tone={statusTone(availabilityLabel(profile.technician_status || selectedTechnician?.technician_status))} />
            </View>
          </View>
        </View>

        <View style={{ borderWidth: 1, borderColor: 'rgba(220,255,232,.42)', borderRadius: 14, backgroundColor: 'rgba(0,42,25,.72)', padding: 11, flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          <View style={{ width: '47%', gap: 4 }}>
            <Text style={{ color: '#BCE8CC', fontSize: 9, fontWeight: '900', letterSpacing: 0.6 }}>PHONE</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}><Phone size={12} color="#FFFFFF" /><Text numberOfLines={1} style={{ color: colors.white, fontSize: 11, fontWeight: '800', flex: 1 }}>{text(profile.phone_number || profile.mobile_number)}</Text></View>
          </View>
          <View style={{ width: '47%', gap: 4 }}>
            <Text style={{ color: '#BCE8CC', fontSize: 9, fontWeight: '900', letterSpacing: 0.6 }}>EMAIL</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}><Mail size={12} color="#FFFFFF" /><Text numberOfLines={1} style={{ color: colors.white, fontSize: 11, fontWeight: '800', flex: 1 }}>{text(profile.email)}</Text></View>
          </View>
          <View style={{ width: '47%', gap: 4 }}>
            <Text style={{ color: '#BCE8CC', fontSize: 9, fontWeight: '900', letterSpacing: 0.6 }}>SKILLS</Text>
            <Text numberOfLines={2} style={{ color: colors.white, fontSize: 11, fontWeight: '800' }}>{text(profile.technician_skill)}</Text>
          </View>
          <View style={{ width: '47%', gap: 4 }}>
            <Text style={{ color: '#BCE8CC', fontSize: 9, fontWeight: '900', letterSpacing: 0.6 }}>WORKLOAD</Text>
            <Text style={{ color: colors.white, fontSize: 14, fontWeight: '900' }}>{activeWorkload}/{workloadLimit}</Text>
          </View>
        </View>
      </ImageBackground>

      {detailsError ? <ErrorBanner message={detailsError} /> : null}
      {detailsLoading && !technicianDetails ? <Text style={{ color: colors.muted, fontSize: 11 }}>Loading technician profile...</Text> : null}

      <SectionTitle title="JOB SUMMARY" subtitle="Counts are calculated from this technician’s assigned jobs" />
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <SummaryMetric label="All Jobs" value={jobsLoading && assignedJobs.length === 0 ? '—' : jobCounts.all} tone="green" icon={<BriefcaseBusiness size={20} color="#087348" />} selected={jobFilter === 'ALL'} onPress={() => setJobFilter('ALL')} />
        <SummaryMetric label="Active" value={jobsLoading && assignedJobs.length === 0 ? '—' : jobCounts.active} tone="blue" icon={<Play size={20} color="#2670D8" />} selected={jobFilter === 'ACTIVE_ONLY'} onPress={() => setJobFilter('ACTIVE_ONLY')} />
        <SummaryMetric label="Completed" value={jobsLoading && assignedJobs.length === 0 ? '—' : jobCounts.completed} tone="green" icon={<CircleCheck size={20} color="#087348" />} selected={jobFilter === 'COMPLETED_ONLY'} onPress={() => setJobFilter('COMPLETED_ONLY')} />
        <SummaryMetric label="On Hold" value={jobsLoading && assignedJobs.length === 0 ? '—' : jobCounts.onHold} tone="amber" icon={<PauseCircle size={20} color="#D08713" />} selected={jobFilter === 'ONHOLD_ONLY'} onPress={() => setJobFilter('ONHOLD_ONLY')} />
      </View>

      <SectionTitle title="Assigned jobs" subtitle={`${assignedJobs.length} total`} />
      {jobsError ? (
        <View style={{ gap: 8 }}>
          <ErrorBanner message={jobsError} />
          <PrimaryButton title="Retry assigned jobs" compact variant="secondary" onPress={() => selectedId !== undefined && void loadTechnicianJobs(selectedId)} />
        </View>
      ) : null}
      {jobsLoading && assignedJobs.length === 0 ? (
        <Text style={{ color: colors.muted, textAlign: 'center', padding: 22 }}>Loading assigned jobs...</Text>
      ) : visibleJobs.length === 0 ? (
        <EmptyState
          title={assignedJobs.length ? 'No jobs in this category' : 'No jobs assigned'}
          detail={assignedJobs.length ? 'Choose another job summary card to view a different status.' : 'Assigned jobs will appear here when this technician receives work.'}
          onRetry={() => selectedId !== undefined && void loadTechnicianJobs(selectedId)}
        />
      ) : (
        visibleJobs.map((job: any) => {
          const updatedAt = job.updated_at || job.completed_at || job.closed_at || job.created_at;
          const priority = text(job.priority, 'Normal');
          const jobStatus = statusLabel(job.status || 'Unknown');
          return (
            <Card key={String(job.id)} style={{ padding: 12, borderRadius: 16, gap: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 9 }}>
                <View style={{ minWidth: 54, paddingRight: 9, borderRightWidth: 1, borderRightColor: colors.border, justifyContent: 'center', alignSelf: 'stretch' }}>
                  <Text style={{ color: colors.forest, fontSize: 17, fontWeight: '900' }}>#{job.id}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0, gap: 4 }}>
                  <Text numberOfLines={2} style={{ color: colors.ink, fontSize: 12, fontWeight: '900', lineHeight: 17 }}>{text(job.issue_description, text(job.service_type, 'Service job'))}</Text>
                  <Text numberOfLines={1} style={{ color: colors.muted, fontSize: 10 }}>Customer: {text(job.customer_name, 'Customer')}</Text>
                  <Text numberOfLines={1} style={{ color: colors.muted, fontSize: 10 }}>Service: {text(job.service_type || job.required_skill)}</Text>
                </View>
                <View style={{ alignItems: 'flex-end', gap: 6, maxWidth: 100 }}>
                  <Pill label={priority} tone={priorityTone(priority)} />
                  <Pill label={jobStatus} tone={statusTone(job.status)} />
                </View>
              </View>
              <Text style={{ color: colors.muted, fontSize: 10, textAlign: 'right' }}>Updated: {formatJobDate(updatedAt)}</Text>
            </Card>
          );
        })
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <MapPin size={13} color={colors.muted} />
        <Text style={{ color: colors.muted, fontSize: 10 }}>Work location: {text(profile.technician_location)}</Text>
        <View style={{ flex: 1 }} />
        <Text style={{ color: colors.muted, fontSize: 10 }}>Last GPS: {timeAgo(profile.last_ping)}</Text>
      </View>
    </ScreenScroll>
  );

  return (
    <>
      {selectedTechnician ? renderTechnicianDetails() : renderTechnicianDirectory()}

      <Modal visible={filterModalVisible} animationType="fade" transparent onRequestClose={() => setFilterModalVisible(false)}>
        <Pressable onPress={() => setFilterModalVisible(false)} style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.48)', justifyContent: 'flex-end' }}>
          <Pressable onPress={() => {}} style={{ backgroundColor: '#F7FAF5', padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, gap: 14 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
              <View style={{ gap: 3 }}>
                <Text style={{ color: '#173D2B', fontSize: 19, fontWeight: '900' }}>Filter technicians</Text>
                <Text style={{ color: '#718277', fontSize: 12 }}>Choose an availability status</Text>
              </View>
              <Pressable onPress={() => setFilterModalVisible(false)} hitSlop={10} style={{ padding: 8 }}>
                <Text style={{ color: '#285A40', fontSize: 14, fontWeight: '900' }}>Close</Text>
              </Pressable>
            </View>
            {LIST_STATUS_FILTERS.map(filter => {
              const active = statusFilter === filter;
              return (
                <Pressable
                  key={`modal-${filter}`}
                  onPress={() => { setStatusFilter(filter); setFilterModalVisible(false); }}
                  style={{ minHeight: 48, paddingHorizontal: 15, borderRadius: 13, borderWidth: 1.2, borderColor: active ? '#145C3B' : '#D9E5DA', backgroundColor: active ? '#E5F0E6' : '#FFFFFF', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}
                >
                  <Text style={{ color: '#173D2B', fontSize: 14, fontWeight: '800' }}>{filter === 'All' ? 'All technicians' : filter === 'Available' ? 'Available technicians' : filter === 'Busy' ? 'Busy technicians' : 'Offline technicians'}</Text>
                  {active ? <CircleCheck size={20} color="#145C3B" /> : null}
                </Pressable>
              );
            })}
            <Pressable onPress={() => { setStatusFilter('All'); setFilterModalVisible(false); }} style={{ minHeight: 46, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: '#145C3B' }}>
              <Text style={{ color: '#FFFFFF', fontSize: 13, fontWeight: '900' }}>Clear filters</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={formOpen} animationType="slide" transparent onRequestClose={() => setFormOpen(false)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.5)', justifyContent: 'flex-end' }}>
          <View style={{ backgroundColor: colors.canvas, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '94%', gap: 13 }}>
            <View style={{ gap: 4 }}>
              <Text style={{ color: colors.ink, fontSize: 20, fontWeight: '900' }}>Create staff account</Text>
              <Text style={{ color: colors.muted, fontSize: 11 }}>Create a Technician or Dispatcher account for your organization.</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <View style={{ flex: 1 }}><Field label="FIRST NAME" value={form.first_name} onChangeText={first_name => setForm(current => ({ ...current, first_name }))} placeholder="First name" /></View>
              <View style={{ flex: 1 }}><Field label="LAST NAME" value={form.last_name} onChangeText={last_name => setForm(current => ({ ...current, last_name }))} placeholder="Last name" /></View>
            </View>
            <Field label="WORK EMAIL / LOGIN" value={form.email} onChangeText={email => setForm(current => ({ ...current, email }))} placeholder="staff@company.com" keyboardType="email-address" autoCapitalize="none" />
            <Field label="PASSWORD" value={form.password} onChangeText={password => setForm(current => ({ ...current, password }))} placeholder="Enter password" secureTextEntry autoCapitalize="none" />
            <Field label="PHONE NUMBER" value={form.phone_number} onChangeText={phone_number => setForm(current => ({ ...current, phone_number }))} placeholder="10-digit mobile number" keyboardType="phone-pad" maxLength={10} />
            <View style={{ gap: 8 }}>
              <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>STAFF ROLE</Text>
              <View style={{ flexDirection: 'row', gap: 9 }}>
                <Pressable onPress={() => setForm(current => ({ ...current, role: 'technician' }))} style={{ flex: 1, padding: 13, borderRadius: 12, borderWidth: 1.5, borderColor: form.role === 'technician' ? colors.forest : colors.border, backgroundColor: form.role === 'technician' ? '#EAF4EE' : colors.white }}>
                  <Text style={{ color: form.role === 'technician' ? colors.forest : colors.text, fontWeight: '900', fontSize: 12, textAlign: 'center' }}>Technician</Text>
                </Pressable>
                {!isDispatcher ? (
                  <Pressable onPress={() => setForm(current => ({ ...current, role: 'dispatcher' }))} style={{ flex: 1, padding: 13, borderRadius: 12, borderWidth: 1.5, borderColor: form.role === 'dispatcher' ? colors.forest : colors.border, backgroundColor: form.role === 'dispatcher' ? '#EAF4EE' : colors.white }}>
                    <Text style={{ color: form.role === 'dispatcher' ? colors.forest : colors.text, fontWeight: '900', fontSize: 12, textAlign: 'center' }}>Dispatcher</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
            <View style={{ backgroundColor: '#EAF4EE', borderRadius: 12, padding: 11 }}>
              <Text style={{ color: colors.forest, fontWeight: '800', fontSize: 11 }}>The password you enter will be used for the staff member’s first login.</Text>
            </View>
            <PrimaryButton title="Create staff account" onPress={saveTechnician} loading={submitting} />
            <PrimaryButton title="Cancel" variant="ghost" onPress={() => { setFormOpen(false); setForm(EMPTY_FORM); }} />
          </View>
        </View>
      </Modal>

      <Modal visible={!!credentials} animationType="fade" transparent onRequestClose={() => setCredentials(null)}>
        <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'center', padding: 20 }}>
          <Card style={{ padding: 21, gap: 14 }}>
            <View style={{ alignItems: 'center', gap: 7 }}>
              <View style={{ width: 52, height: 52, borderRadius: 18, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center' }}><ShieldCheck size={26} color={colors.forest} /></View>
              <Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>Staff account created</Text>
              <Text style={{ color: colors.muted, fontSize: 11, textAlign: 'center' }}>{credentials?.name} can use these credentials to sign in to the {credentials?.role === 'dispatcher' ? 'dispatcher portal' : 'technician app'}.</Text>
            </View>
            <View style={{ gap: 5 }}><Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>LOGIN EMAIL</Text><Text selectable style={{ color: colors.ink, fontSize: 14, fontWeight: '800' }}>{credentials?.email}</Text></View>
            <View style={{ gap: 5 }}><Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>PASSWORD</Text><Text selectable style={{ color: colors.forest, fontSize: 19, fontWeight: '900', letterSpacing: 1 }}>{credentials?.password}</Text></View>
            <PrimaryButton title="Copy login details" onPress={async () => { await Clipboard.setStringAsync(`FieldOps ${credentials?.role === 'dispatcher' ? 'Dispatcher' : 'Technician'} Login\nEmail: ${credentials?.email}\nPassword: ${credentials?.password}`); Alert.alert('Copied', 'Staff login details copied to clipboard.'); }} />
            <Text style={{ color: colors.amber, fontSize: 10, lineHeight: 15 }}>Share this password securely with the staff member. It cannot be shown again after closing this screen.</Text>
            <PrimaryButton title="Done" variant="secondary" onPress={() => setCredentials(null)} />
          </Card>
        </View>
      </Modal>
    </>
  );
}
