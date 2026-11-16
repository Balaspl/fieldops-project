import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, ImageBackground, Modal, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { Mail, MapPin, Phone, ShieldCheck } from 'lucide-react-native';
import * as Clipboard from 'expo-clipboard';
import { useAuth } from '../auth/AuthContext';
import { deleteTechnician, getDispatchers, getTechnicians, provisionTechnician, updateTechnician } from '../api/operations';
import { Card, EmptyState, ErrorBanner, Field, Pill, PrimaryButton, ScreenHeading, ScreenScroll, SearchField } from '../components/UI';
import { colors } from '../theme';
import { generateTemporaryPassword } from '../utils/credentials';
import { dateTime, initials, statusLabel, statusTone, text, timeAgo } from '../utils/format';

type StaffView = 'technicians' | 'dispatchers';
type TechnicianForm = {
  first_name: string; last_name: string; email: string; phone_number: string;
  technician_name: string; technician_skill: string; technician_location: string;
};
const EMPTY_FORM: TechnicianForm = {
  first_name: '', last_name: '', email: '', phone_number: '',
  technician_name: '', technician_skill: '', technician_location: '',
};
const STATUS_FILTERS = ['All', 'Available', 'Busy', 'Assigned', 'Offline', 'En Route', 'On Site', 'On Break', 'Suspended'];
const normalizeStatus = (v: any) => String(v || '').replace(/[_-]+/g, ' ').toLowerCase();

export default function TeamScreen({ onNavigate }: { onNavigate: (tab: string) => void }) {
  const { role, user } = useAuth();
  const isSuperAdmin = role === 'super_admin';
  const [view, setView] = useState<StaffView>('technicians');
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [dispatchers, setDispatchers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [formOpen, setFormOpen] = useState(false);
  const [editingTechnician, setEditingTechnician] = useState<any | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [credentials, setCredentials] = useState<{ name: string; email: string; password: string } | null>(null);
  const [form, setForm] = useState<TechnicianForm>(EMPTY_FORM);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true); else setLoading(true);
    setError('');
    try {
      const [techRows, dispatcherRows] = await Promise.all([
        getTechnicians({ page: 1, limit: 150 }),
        isSuperAdmin ? getDispatchers() : Promise.resolve([]),
      ]);
      setTechnicians(techRows); setDispatchers(dispatcherRows);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || 'Could not load staff records.');
    } finally { setLoading(false); setRefreshing(false); }
  }, [isSuperAdmin]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => { void load(true); }, 30000);
    return () => clearInterval(timer);
  }, [load]);

  const rows = useMemo(() => {
    const source = view === 'technicians' ? technicians : dispatchers;
    const term = search.trim().toLowerCase();
    return source.filter((row: any) => {
      const matchesSearch = !term || [row.technician_name, row.name, row.email, row.technician_skill, row.technician_location, row.phone_number].some(x => String(x || '').toLowerCase().includes(term));
      const status = normalizeStatus(row.technician_status || row.status);
      const matchesStatus = view !== 'technicians' || statusFilter === 'All' || status === normalizeStatus(statusFilter);
      return matchesSearch && matchesStatus;
    });
  }, [view, technicians, dispatchers, search, statusFilter]);

  const startCreate = () => {
    setEditingTechnician(null); setForm(EMPTY_FORM); setFormOpen(true);
  };

  const startEdit = (tech: any) => {
    setEditingTechnician(tech);
    setForm({
      ...EMPTY_FORM,
      technician_name: String(tech.technician_name || tech.name || ''),
      technician_skill: String(tech.technician_skill || tech.skill || ''),
      technician_location: String(tech.technician_location || tech.location || ''),
    });
    setFormOpen(true);
  };

  const saveTechnician = async () => {
    if (editingTechnician) {
      if (!form.technician_name.trim() || !form.technician_skill.trim() || !form.technician_location.trim()) {
        Alert.alert('Required information', 'Enter the technician name, skill and work location.'); return;
      }
    } else if (!form.first_name.trim() || !form.last_name.trim() || !form.email.trim() || !form.technician_skill.trim() || !form.technician_location.trim()) {
      Alert.alert('Required information', 'Enter the technician’s name, work email, skill and location.'); return;
    }
    setSubmitting(true);
    try {
      if (editingTechnician) {
        await updateTechnician(editingTechnician.technician_id, {
          technician_name: form.technician_name.trim(),
          technician_skill: form.technician_skill.trim(),
          technician_location: form.technician_location.trim(),
          // The web edit form intentionally leaves availability to the technician portal.
          // Preserve the backend status instead of changing it from the admin screen.
          technician_status: editingTechnician.technician_status || editingTechnician.status || 'OFFLINE',
        });
        setFormOpen(false); setEditingTechnician(null);
        Alert.alert('Technician updated', 'The technician profile has been updated.');
        await load(true);
      } else {
        const password = await generateTemporaryPassword();
        const email = form.email.trim().toLowerCase();
        const name = `${form.first_name.trim()} ${form.last_name.trim()}`;
        await provisionTechnician({
          first_name: form.first_name.trim(), last_name: form.last_name.trim(), email,
          phone_number: form.phone_number.trim() || undefined,
          technician_skill: form.technician_skill.trim(),
          technician_location: form.technician_location.trim(), password,
        });
        setFormOpen(false);
        setCredentials({ name, email, password });
        await load(true);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || (editingTechnician ? 'Technician could not be updated.' : 'Technician account could not be created.');
      Alert.alert(editingTechnician ? 'Update failed' : 'Provisioning failed', typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally { setSubmitting(false); }
  };

  const confirmDelete = (tech: any) => {
    Alert.alert(
      'Delete technician profile?',
      `Remove ${tech.technician_name || 'this technician'} from the operational technician directory? This action cannot be undone.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete profile', style: 'destructive', onPress: async () => {
          try {
            await deleteTechnician(tech.technician_id);
            await load(true);
            Alert.alert('Technician deleted', 'The technician operational profile was removed.');
          } catch (e: any) {
            Alert.alert('Delete failed', e?.response?.data?.detail || e?.message || 'The technician could not be deleted.');
          }
        } },
      ],
    );
  };

  return <>
    <ScreenScroll refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={colors.forest} />}>
      <ImageBackground source={require('../../assets/services/technician_banner.png')} resizeMode="cover" style={{ height: 145, borderRadius: 18, overflow: 'hidden', justifyContent: 'flex-end', padding: 16 }}>
        <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(3,64,37,.65)' }} />
        <Text style={{ color: '#DAF4E2', fontWeight: '900', fontSize: 10, letterSpacing: 1 }}>PEOPLE & FIELD OPERATIONS</Text>
        <Text style={{ color: '#fff', fontSize: 23, fontWeight: '900', marginTop: 4 }}>Team management</Text>
        <Text style={{ color: '#E6F6EC', fontSize: 11, marginTop: 3 }}>Technician accounts, skills and team directory</Text>
      </ImageBackground>
      <ScreenHeading title="Staff" subtitle={user?.organization_name || 'Your organization'} action={view === 'technicians' ? <PrimaryButton title="Add technician" compact onPress={startCreate} /> : undefined} />
      {isSuperAdmin ? <View style={{ flexDirection: 'row', backgroundColor: '#E7EFEA', padding: 4, borderRadius: 13, gap: 4 }}>
        {(['technicians', 'dispatchers'] as const).map(tab => <PrimaryButton key={tab} title={tab === 'technicians' ? 'Technicians' : 'Dispatchers'} compact variant={view === tab ? 'primary' : 'ghost'} style={{ flex: 1 }} onPress={() => { setView(tab); setSearch(''); setStatusFilter('All'); }} />)}
      </View> : null}
      {view === 'technicians' ? <View style={{ flexDirection: 'row', gap: 8 }}>
        <Card style={{ flex: 1, padding: 12 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Technicians</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 22 }}>{technicians.length}</Text></Card>
        <Card style={{ flex: 1, padding: 12 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Available now</Text><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 22 }}>{technicians.filter(t => normalizeStatus(t.technician_status || t.status) === 'available').length}</Text></Card>
        <Card style={{ flex: 1, padding: 12 }}><Text style={{ color: colors.muted, fontSize: 10 }}>On field</Text><Text style={{ color: colors.blue, fontWeight: '900', fontSize: 22 }}>{technicians.filter(t => ['busy', 'on job', 'en route', 'on site', 'assigned'].includes(normalizeStatus(t.technician_status || t.status))).length}</Text></Card>
      </View> : <Card style={{ padding: 13 }}><Text style={{ color: colors.muted, fontSize: 10 }}>DISPATCHER ACCOUNTS</Text><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 22 }}>{dispatchers.length}</Text><Text style={{ color: colors.muted, fontSize: 11, marginTop: 3 }}>Dispatcher accounts created for your organization.</Text></Card>}
      <SearchField value={search} onChangeText={setSearch} placeholder={`Search ${view}…`} />
      {view === 'technicians' ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 7 }}>
        {STATUS_FILTERS.map(filter => <Pressable key={filter} onPress={() => setStatusFilter(filter)} style={{ paddingVertical: 8, paddingHorizontal: 12, borderRadius: 20, backgroundColor: statusFilter === filter ? colors.forest : colors.white, borderWidth: 1, borderColor: statusFilter === filter ? colors.forest : colors.border }}><Text style={{ color: statusFilter === filter ? colors.white : colors.text, fontSize: 10, fontWeight: '800' }}>{filter}</Text></Pressable>)}
      </ScrollView> : null}
      {error ? <ErrorBanner message={error} /> : null}
      {loading ? <Text style={{ textAlign: 'center', color: colors.muted, padding: 24 }}>Loading staff…</Text> : rows.length === 0 ? <EmptyState title={`No ${view} found`} detail={search || statusFilter !== 'All' ? 'Try another search or status filter.' : 'Staff records will appear here when available.'} onRetry={() => load(true)} /> : rows.map((item: any) => view === 'technicians' ? <Card key={String(item.technician_id)} style={{ gap: 12 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}>
          <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: colors.forest, fontWeight: '900', fontSize: 15 }}>{initials(item.technician_name)}</Text></View>
          <View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 14 }}>{text(item.technician_name, 'Technician')}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{text(item.technician_skill, 'Skill not set')}</Text></View>
          <Pill label={statusLabel(item.technician_status || item.status)} tone={statusTone(item.technician_status || item.status)} />
        </View>
        <View style={{ gap: 8 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><MapPin size={14} color={colors.muted} /><Text style={{ color: colors.text, fontSize: 11, flex: 1 }}>{text(item.technician_location)}</Text></View>
          {item.email ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><Mail size={14} color={colors.muted} /><Text style={{ color: colors.text, fontSize: 11, flex: 1 }}>{item.email}</Text></View> : null}
          {(item.phone_number || item.mobile_number) ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><Phone size={14} color={colors.muted} /><Text style={{ color: colors.text, fontSize: 11 }}>{item.phone_number || item.mobile_number}</Text></View> : null}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.softBorder }}>
          <View style={{ gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Workload</Text><Text style={{ color: colors.ink, fontWeight: '800', fontSize: 12 }}>{item.current_jobs ?? 0} / {item.max_jobs ?? 5} jobs</Text></View>
          <View style={{ alignItems: 'flex-end', gap: 3 }}><Text style={{ color: colors.muted, fontSize: 10 }}>Last GPS ping</Text><Text style={{ color: colors.text, fontSize: 11 }}>{timeAgo(item.last_ping)}</Text></View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <View style={{ flex: 1 }}><PrimaryButton title="Edit details" compact variant="secondary" onPress={() => startEdit(item)} /></View>
          <View style={{ flex: 1 }}><PrimaryButton title="Delete profile" compact variant="danger" onPress={() => confirmDelete(item)} /></View>
        </View>
        <Text style={{ color: colors.muted, fontSize: 10 }}>Technician availability is controlled by the technician from their portal.</Text>
      </Card> : <Card key={String(item.id)} style={{ gap: 11 }}>
        <ImageBackground source={require('../../assets/banners/dispatcher-banner.png')} resizeMode="cover" imageStyle={{ borderRadius: 14 }} style={{ height: 104, borderRadius: 14, padding: 13, justifyContent: 'flex-end', overflow: 'hidden' }}>
          <View style={{ position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, backgroundColor: 'rgba(4,60,36,.58)' }} />
          <Text style={{ color: '#fff', fontSize: 17, fontWeight: '900' }}>{item.name || `${item.first_name || ''} ${item.last_name || ''}`}</Text>
          <Text style={{ color: '#E3F5EA', fontSize: 11 }}>Dispatcher</Text>
        </ImageBackground>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}><Text style={{ flex: 1, color: colors.text, fontSize: 11 }}>{text(item.email)}</Text><Pill label={item.is_active ? 'Active' : 'Inactive'} tone={item.is_active ? 'green' : 'red'} /></View>
        <View style={{ flexDirection: 'row', gap: 7, alignItems: 'center' }}><Phone size={14} color={colors.muted} /><Text style={{ color: colors.text, fontSize: 11 }}>{text(item.phone_number)}</Text></View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}><Text style={{ color: colors.muted, fontSize: 10 }}>Duty status</Text><Pill label={item.is_on_duty ? 'On duty' : 'Off duty'} tone={item.is_on_duty ? 'green' : 'neutral'} /></View>
        <Text style={{ color: colors.muted, fontSize: 10 }}>Last login: {dateTime(item.last_login)}</Text>
      </Card>)}
      <Card style={{ backgroundColor: '#F3F8F5' }}><Text style={{ color: colors.muted, fontSize: 10, lineHeight: 16 }}>{view === 'technicians' ? 'Technician account provisioning creates a login user and a linked technician record inside this tenant. The generated password is only displayed once. Editing and deletion use the existing technician API; live availability remains technician-controlled.' : 'Dispatcher account details are shown within your organization. Only Super Admin can access this directory.'}</Text></Card>
    </ScreenScroll>

    <Modal visible={formOpen} animationType="slide" transparent onRequestClose={() => { setFormOpen(false); setEditingTechnician(null); }}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.5)', justifyContent: 'flex-end' }}>
        <View style={{ backgroundColor: colors.canvas, padding: 20, borderTopLeftRadius: 24, borderTopRightRadius: 24, maxHeight: '94%', gap: 13 }}>
          <View style={{ gap: 4 }}><Text style={{ color: colors.ink, fontSize: 20, fontWeight: '900' }}>{editingTechnician ? 'Edit technician details' : 'Create technician account'}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{editingTechnician ? 'Update the operational profile. Availability remains controlled by the technician.' : 'Create a portal login and its linked technician profile.'}</Text></View>
          {editingTechnician ? <Field label="FULL NAME" value={form.technician_name} onChangeText={technician_name => setForm(p => ({ ...p, technician_name }))} placeholder="Technician full name" /> : <>
            <View style={{ flexDirection: 'row', gap: 10 }}><View style={{ flex: 1 }}><Field label="FIRST NAME" value={form.first_name} onChangeText={first_name => setForm(p => ({ ...p, first_name }))} placeholder="First name" /></View><View style={{ flex: 1 }}><Field label="LAST NAME" value={form.last_name} onChangeText={last_name => setForm(p => ({ ...p, last_name }))} placeholder="Last name" /></View></View>
            <Field label="WORK EMAIL / LOGIN" value={form.email} onChangeText={email => setForm(p => ({ ...p, email }))} placeholder="technician@company.com" keyboardType="email-address" autoCapitalize="none" />
            <Field label="PHONE NUMBER" value={form.phone_number} onChangeText={phone_number => setForm(p => ({ ...p, phone_number }))} placeholder="Optional contact number" keyboardType="phone-pad" />
          </>}
          <Field label="PRIMARY SKILL" value={form.technician_skill} onChangeText={technician_skill => setForm(p => ({ ...p, technician_skill }))} placeholder="e.g. Electrical, Plumbing, HVAC" />
          <Field label="WORK LOCATION / ZONE" value={form.technician_location} onChangeText={technician_location => setForm(p => ({ ...p, technician_location }))} placeholder="e.g. Chennai West or coordinates" />
          {!editingTechnician ? <View style={{ backgroundColor: '#EAF4EE', borderRadius: 12, padding: 11 }}><Text style={{ color: colors.forest, fontWeight: '800', fontSize: 11 }}>A strong temporary password is generated securely during account creation. The technician starts Offline and controls availability from their app.</Text></View> : null}
          <PrimaryButton title={editingTechnician ? 'Save technician changes' : 'Create login & technician'} onPress={saveTechnician} loading={submitting} />
          <PrimaryButton title="Cancel" variant="ghost" onPress={() => { setFormOpen(false); setEditingTechnician(null); }} />
        </View>
      </View>
    </Modal>

    <Modal visible={!!credentials} animationType="fade" transparent onRequestClose={() => setCredentials(null)}>
      <View style={{ flex: 1, backgroundColor: 'rgba(7,25,16,.55)', justifyContent: 'center', padding: 20 }}>
        <Card style={{ padding: 21, gap: 14 }}>
          <View style={{ alignItems: 'center', gap: 7 }}><View style={{ width: 52, height: 52, borderRadius: 18, backgroundColor: colors.mint, alignItems: 'center', justifyContent: 'center' }}><ShieldCheck size={26} color={colors.forest} /></View><Text style={{ color: colors.ink, fontSize: 19, fontWeight: '900' }}>Technician account created</Text><Text style={{ color: colors.muted, fontSize: 11, textAlign: 'center' }}>{credentials?.name} can use these credentials to sign in to the technician app.</Text></View>
          <View style={{ gap: 5 }}><Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>LOGIN EMAIL</Text><Text selectable style={{ color: colors.ink, fontSize: 14, fontWeight: '800' }}>{credentials?.email}</Text></View>
          <View style={{ gap: 5 }}><Text style={{ color: colors.muted, fontSize: 10, fontWeight: '900' }}>TEMPORARY PASSWORD</Text><Text selectable style={{ color: colors.forest, fontSize: 19, fontWeight: '900', letterSpacing: 1 }}>{credentials?.password}</Text></View>
          <PrimaryButton title="Copy login details" onPress={async () => { await Clipboard.setStringAsync(`FieldOps Technician Login\nEmail: ${credentials?.email}\nTemporary password: ${credentials?.password}`); Alert.alert('Copied', 'Technician login details copied to clipboard.'); }} />
          <Text style={{ color: colors.amber, fontSize: 10, lineHeight: 15 }}>Share this password securely with the technician. It is not stored in the mobile app and cannot be shown again after closing this screen.</Text>
          <PrimaryButton title="Done" variant="secondary" onPress={() => setCredentials(null)} />
        </Card>
      </View>
    </Modal>
  </>;
}
