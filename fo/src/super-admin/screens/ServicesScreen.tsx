import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Pressable,
  RefreshControl,
  ScrollView,
  ImageBackground,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import {
  ArrowLeft,
  Check,
  ChevronRight,
  ImageOff,
  Layers3,
  Leaf,
} from 'lucide-react-native';
import { useAuth } from '../auth/AuthContext';
import { createServicesBatch, deleteService, getServices } from '../api/operations';
import {
  Card,
  EmptyState,
  ErrorBanner,
  Pill,
  PrimaryButton,
  SearchField,
} from '../components/UI';
import { colors } from '../theme';
import { text } from '../utils/format';
import {
  SERVICE_CATALOGUE_TAXONOMY,
  type TaxonomyCategory,
  type TaxonomyServiceType,
} from '../data/serviceCatalogueTaxonomy';
import { getCategoryCardImage, getIssueCardImage } from '../data/categoryImages';
import { getLocalServiceImage } from '../utils/serviceAssetMap';

type WizardStep = 1 | 2 | 3;
type ConfiguredService = {
  id: number;
  service_type: string;
  category: string;
  issue: string;
  description?: string;
  required_skill?: string;
  is_active: boolean;
  priority?: string;
};

type SelectionMap = Record<string, string[]>;

const normalizeCatalogValue = (value?: string | null) =>
  (value || '').trim().toLowerCase().replace(/[^a-z0-9]/g, '');

// Legacy category labels from the web catalogue are retained so older rows
// already stored by an organization map back to the canonical taxonomy cards.
const CATEGORY_LABELS: Record<string, Record<string, string>> = {
  electrical: {
    'lights and lighting': 'Lights, Bulbs & Tube Lights',
    'wiring and cabling': 'House Wiring & Cables',
    'switches, sockets and switchboards': 'Switches, Sockets & Plug Points',
    'fans and ventilation': 'Fans & Exhaust Fans',
    'mcb, fuse and distribution board': 'MCB, Fuse & Distribution Box',
    'inverter, ups and battery': 'Inverter, UPS & Battery',
    'appliance electrical points': 'Appliance Connections & New Points',
    'doorbell, intercom and low-voltage': 'Doorbell & Intercom',
    'safety, earthing and inspection': 'Earthing & Electrical Safety',
  },
  plumbing: {
    'taps and faucets': 'Taps & Faucets',
    'pipes and pipelines': 'Pipes & Plumbing Lines',
    'drainage and blockage': 'Drainage & Blockage',
    'toilet and sanitary': 'Toilet & Sanitary Fittings',
    'wash basin and kitchen sink': 'Washbasin & Kitchen Sink',
    'water tank, motor and pump': 'Water Tanks, Pumps & Motors',
    'geyser and hot water lines': 'Geyser & Water Heater',
    'shower and bathroom fittings': 'Shower & Bathroom Fittings',
    'water pressure and supply': 'Water Supply & Pressure Problems',
    'leakage and seepage': 'Water Leakage & Seepage',
    'sewage and septic': 'Sewerage & Septic Tank',
  },
  'air conditioning and refrigeration': {
    'cassette, ducted and vrf systems': 'Cassette, Ductable & VRF AC Systems',
    'cassette, ductable & vrf ac': 'Cassette, Ductable & VRF AC Systems',
    'ac installation and relocation': 'AC Installation, Uninstallation & Relocation',
    'ac installation & uninstallation': 'AC Installation, Uninstallation & Relocation',
    'ac servicing and maintenance': 'AC Service & Maintenance',
    'refrigerator (domestic)': 'Home Refrigerator Repair',
    'home refrigerator': 'Home Refrigerator Repair',
    'air coolers and air purifiers': 'Air Coolers, Air Purifiers & Humidifiers',
  },
  'home appliance repair': {
    television: 'TV (LED, LCD & Smart TV)',
    'microwave oven and otg': 'Microwave Oven & OTG',
    'kitchen chimney and hob': 'Kitchen Chimney & Hob',
    'mixer grinder and blender': 'Mixer Grinder & Blender',
    'vacuum cleaner and floor care': 'Vacuum Cleaner & Floor Care',
    'electric water heater (appliance)': 'Electric Geyser & Water Heater',
    'water dispenser and others': 'Water Dispenser & Other Appliances',
  },
  'carpentry and furniture': {
    'furniture repair': 'Furniture Repair & Restoration',
    'modular kitchen and wardrobe': 'Modular Kitchen and Wardrobe',
    'wooden doors': 'Wooden Door Repair & Installation',
    'custom furniture': 'Custom Furniture Design & Making',
    'custom furniture making': 'Custom Furniture Design & Making',
    'polishing and finishing': 'Furniture Polishing & Painting',
    'furniture assembly and fitting': 'Furniture Assembly & Installation',
    'partitions and wooden ceilings': 'Woodwork, Partitions & False Ceilings',
    'wooden partitions & false ceilings': 'Woodwork, Partitions & False Ceilings',
  },
  'cctv and security systems': {
    'cctv cameras': 'CCTV Cameras & Installation',
    'dvr and nvr': 'DVR, NVR & Recording Systems',
    'biometric and access control': 'Biometric Attendance & Access Control',
    'alarms and sensors': 'Security Alarms & Sensors',
    'video door phone and intercom': 'Video Door Phone & Intercom',
    'gate and barrier automation': 'Automatic Gates & Boom Barriers',
    'electric fence and perimeter': 'Electric Fencing & Perimeter Security',
  },
  'water purifier (ro) and water treatment': {
    'ro water purifier': 'Domestic RO Water Purifier',
    'uv, uf and gravity purifiers': 'UV, UF & Gravity Water Purifiers',
    'commercial and industrial ro plant': 'Commercial & Industrial RO Plants',
    'water softener and filtration': 'Water Softeners & Filter Systems',
    'water cooler and dispenser': 'Water Coolers & Dispensers',
    'installation and maintenance': 'RO Installation & Maintenance',
  },
  'painting and waterproofing': {
    'wood and metal painting': 'Wood & Metal Painting',
    'wall defects': 'Wall Repair & Crack Filling',
    waterproofing: 'Waterproofing Services',
  },
  painting: {
    'wood and metal painting': 'Wood & Metal Painting',
    'wall defects': 'Wall Repair & Crack Filling',
    waterproofing: 'Waterproofing Services',
  },
  'painting & waterproofing': {
    'wood and metal painting': 'Wood & Metal Painting',
    'wall defects': 'Wall Repair & Crack Filling',
    waterproofing: 'Waterproofing Services',
  },
  'painting, wall repair & waterproofing': {
    'wood and metal painting': 'Wood & Metal Painting',
    'wall defects': 'Wall Repair & Crack Filling',
    waterproofing: 'Waterproofing Services',
  },
  'cleaning services': {
    'sofa, carpet, mattress and curtain': 'Sofa, Carpet, Mattress & Curtain Cleaning',
    'water tank and sump cleaning': 'Water Tank & Sump Cleaning',
    'kitchen cleaning': 'Kitchen Deep Cleaning',
    'bathroom cleaning': 'Bathroom Deep Cleaning',
    'office and commercial cleaning': 'Office & Commercial Cleaning',
    'specialised cleaning': 'Specialised Cleaning Services',
  },
};

function getCategoryLabel(serviceType?: string | null, category?: string | null): string {
  const label = category || 'General';
  const serviceTypeKey = (serviceType || '').trim().toLowerCase();
  return CATEGORY_LABELS[serviceTypeKey]?.[label.trim().toLowerCase()] || label;
}

function CatalogRemoteImage({
  path,
  style,
  resizeMode = 'contain',
}: {
  path: string | null | undefined;
  style: StyleProp<ViewStyle>;
  resizeMode?: 'contain' | 'cover';
}) {
  const [failed, setFailed] = useState(false);

  // Resolve both legacy web-manifest paths and normal /services paths
  // against the bundled local image registry. No network request is made.
  const sharedPath = typeof path === 'string'
    ?  path.replace(/^\/services\/plumbing\//i, '/services/Plumbing/')
    : path;

  const imageSource = getLocalServiceImage(sharedPath);

  return (
    <View
      style={[
        {
          backgroundColor: '#F1F5F9',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        },
        style,
      ]}
    >
      {imageSource && !failed ? (
        <Image
          source={imageSource}
          resizeMode={resizeMode}
          style={{ width: '100%', height: '100%' }}
          onError={() => setFailed(true)}
        />
      ) : (
        <View
          style={{
            alignItems: 'center',
            justifyContent: 'center',
            gap: 5,
            padding: 8,
          }}
        >
          <ImageOff size={20} color={colors.muted} />
          <Text
            style={{
              color: colors.muted,
              fontSize: 9,
              textAlign: 'center',
            }}
          >
            Image not found in local assets
          </Text>
        </View>
      )}
    </View>
  );
}

function SelectionBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <View style={{ position: 'absolute', top: 8, right: 8, borderRadius: 99, backgroundColor: '#059669', paddingHorizontal: 8, paddingVertical: 5 }}>
      <Text style={{ color: colors.white, fontSize: 10, fontWeight: '900' }}>{count} selected</Text>
    </View>
  );
}

export default function ServicesScreen() {
  const { role } = useAuth();
  const canManage = role === 'super_admin';
  const [services, setServices] = useState<ConfiguredService[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState<WizardStep>(1);
  const [selectedServiceType, setSelectedServiceType] = useState<TaxonomyServiceType | null>(null);
  const [activeCategory, setActiveCategory] = useState<TaxonomyCategory | null>(null);
  const [selectedIssuesByCategory, setSelectedIssuesByCategory] = useState<SelectionMap>({});
  const [serviceSearch, setServiceSearch] = useState('');
  const [categorySearch, setCategorySearch] = useState('');
  const [issueSearch, setIssueSearch] = useState('');
  const [catalogSearch, setCatalogSearch] = useState('');

  const loadServices = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const rows = await getServices();
      setServices(rows as ConfiguredService[]);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Unable to load the organization service catalog.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadServices();
  }, [loadServices]);

  const savedIssuesForType = useCallback((
    serviceType: TaxonomyServiceType,
    source: ConfiguredService[] = services,
  ): SelectionMap => {
    const result: SelectionMap = {};
    const matchesType = (value: string) => {
      const normalized = normalizeCatalogValue(value);
      return normalized === normalizeCatalogValue(serviceType.name)
        || normalized === normalizeCatalogValue(serviceType.id);
    };

    serviceType.categories.forEach((category) => {
      const savedRows = source.filter((service) => {
        if (!matchesType(service.service_type)) return false;
        const savedCategory = normalizeCatalogValue(getCategoryLabel(service.service_type, service.category));
        return savedCategory === normalizeCatalogValue(category.name)
          || normalizeCatalogValue(service.category) === normalizeCatalogValue(category.id);
      });

      result[category.id] = category.issues.filter((issue) =>
        savedRows.some((service) => normalizeCatalogValue(service.issue) === normalizeCatalogValue(issue)),
      );
    });

    return result;
  }, [services]);

  const activeIssueCountForType = useCallback((serviceType: TaxonomyServiceType) => {
    const activeRows = services.filter((item) => item.is_active === true);
    return Object.values(savedIssuesForType(serviceType, activeRows))
      .reduce((total, issues) => total + issues.length, 0);
  }, [savedIssuesForType, services]);

  const visibleServiceTypes = useMemo(() => {
    const query = serviceSearch.trim().toLowerCase();
    if (!query) return SERVICE_CATALOGUE_TAXONOMY;
    return SERVICE_CATALOGUE_TAXONOMY.filter((item) =>
      `${item.name} ${item.description}`.toLowerCase().includes(query),
    );
  }, [serviceSearch]);

  const visibleCategories = useMemo(() => {
    if (!selectedServiceType) return [];
    const query = categorySearch.trim().toLowerCase();
    if (!query) return selectedServiceType.categories;
    return selectedServiceType.categories.filter((item) =>
      `${item.name} ${item.code}`.toLowerCase().includes(query),
    );
  }, [selectedServiceType, categorySearch]);

  const visibleIssues = useMemo(() => {
    if (!activeCategory) return [];
    const query = issueSearch.trim().toLowerCase();
    if (!query) return activeCategory.issues;
    return activeCategory.issues.filter((item) => item.toLowerCase().includes(query));
  }, [activeCategory, issueSearch]);

  const selectedCategoryCount = Object.values(selectedIssuesByCategory)
    .filter((items) => items.length > 0).length;
  const selectedIssueCount = Object.values(selectedIssuesByCategory)
    .reduce((total, items) => total + items.length, 0);

  const chooseServiceType = (serviceType: TaxonomyServiceType) => {
    if (selectedServiceType?.id !== serviceType.id) {
      setSelectedIssuesByCategory(savedIssuesForType(serviceType));
    }
    setSelectedServiceType(serviceType);
    setActiveCategory(null);
    setCategorySearch('');
    setIssueSearch('');
    setError('');
    setStep(2);
  };

  const openCategory = (category: TaxonomyCategory) => {
    setActiveCategory(category);
    setIssueSearch('');
    setError('');
    setStep(3);
  };

  const goBack = () => {
    if (saving) return;
    setError('');
    if (step === 3) {
      setActiveCategory(null);
      setIssueSearch('');
      setStep(2);
      return;
    }
    if (step === 2) {
      setActiveCategory(null);
      setCategorySearch('');
      setIssueSearch('');
      setStep(1);
    }
  };

  const toggleIssue = (issue: string) => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => {
      const existing = current[activeCategory.id] || [];
      const next = existing.some((item) => normalizeCatalogValue(item) === normalizeCatalogValue(issue))
        ? existing.filter((item) => normalizeCatalogValue(item) !== normalizeCatalogValue(issue))
        : [...existing, issue];
      return { ...current, [activeCategory.id]: next };
    });
  };

  const selectAllIssues = () => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => ({
      ...current,
      [activeCategory.id]: [...activeCategory.issues],
    }));
  };

  const deselectAllIssues = () => {
    if (!activeCategory) return;
    setSelectedIssuesByCategory((current) => ({ ...current, [activeCategory.id]: [] }));
  };

  const handleSave = async () => {
    if (!canManage || !selectedServiceType || saving) return;

    const savedSelections = savedIssuesForType(selectedServiceType);
    const groupsToAdd = selectedServiceType.categories
      .map((category) => {
        const selected = selectedIssuesByCategory[category.id] || [];
        const saved = savedSelections[category.id] || [];
        return {
          category: category.name,
          issues: selected.filter((issue) =>
            !saved.some((existing) => normalizeCatalogValue(existing) === normalizeCatalogValue(issue)),
          ),
        };
      })
      .filter((group) => group.issues.length > 0);

    // Match the web wizard: remove only known taxonomy issues for this service
    // type that the user has deselected. Unknown legacy rows are left untouched.
    const servicesToRemove = services.filter((service) => {
      const normalizedType = normalizeCatalogValue(service.service_type);
      const matchesType = normalizedType === normalizeCatalogValue(selectedServiceType.name)
        || normalizedType === normalizeCatalogValue(selectedServiceType.id);
      if (!matchesType) return false;

      const category = selectedServiceType.categories.find((item) =>
        normalizeCatalogValue(item.name) === normalizeCatalogValue(getCategoryLabel(service.service_type, service.category))
        || normalizeCatalogValue(item.id) === normalizeCatalogValue(service.category),
      );
      if (!category) return false;

      const knownIssue = category.issues.some((issue) =>
        normalizeCatalogValue(issue) === normalizeCatalogValue(service.issue),
      );
      if (!knownIssue) return false;

      const selected = selectedIssuesByCategory[category.id] || [];
      return !selected.some((issue) => normalizeCatalogValue(issue) === normalizeCatalogValue(service.issue));
    });

    const additionsCount = groupsToAdd.reduce((total, group) => total + group.issues.length, 0);
    if (additionsCount === 0 && servicesToRemove.length === 0) {
      Alert.alert('No changes to save', 'Your organization service selections are already up to date.');
      return;
    }

    setSaving(true);
    setError('');
    try {
      if (groupsToAdd.length > 0) {
        await createServicesBatch({ service_type: selectedServiceType.name, groups: groupsToAdd });
      }

      for (const service of servicesToRemove) {
        await deleteService(Number(service.id));
      }

      await loadServices(true);
      Alert.alert(
        'Services saved',
        `Successfully saved ${selectedIssueCount} selected issues under "${selectedServiceType.name}".`,
      );
    } catch (err: any) {
      const message = err?.response?.data?.detail || err?.message || 'Unable to save all service changes. Please try again.';
      await loadServices(true);
      setError(String(message));
      Alert.alert('Could not save services', String(message));
    } finally {
      setSaving(false);
    }
  };

  const renderWizardSummary = () => (
    <View style={{ borderRadius: 15, borderWidth: 1, borderColor: '#CFE3D0', backgroundColor: 'rgba(255,255,255,0.94)', padding: 12, gap: 9 }}>
      <Text style={{ color: colors.forest, fontSize: 11, fontWeight: '900', letterSpacing: 0.5 }}>CURRENT SELECTION</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 7 }}>
        <Pill label={selectedServiceType?.name || 'No service type'} tone="green" />
        <Text style={{ color: colors.muted, fontSize: 11 }}>{selectedCategoryCount} categories</Text>
        <Text style={{ color: colors.muted, fontSize: 11 }}>{selectedIssueCount} issues</Text>
      </View>
    </View>
  );

  const renderReadOnlyCatalog = () => {
    const query = catalogSearch.trim().toLowerCase();
    const visible = services.filter((item) => !query || [item.service_type, item.category, item.issue, item.description, item.required_skill]
      .some((value) => String(value || '').toLowerCase().includes(query)));

    return (
      <ImageBackground
        source={require('../../../assets/team/nature_team_background.png')}
        resizeMode="cover"
        imageStyle={{ opacity: 1 }}
        style={{ flex: 1, backgroundColor: '#E8F1E6' }}
      >
      <ScrollView
        style={{ flex: 1, backgroundColor: 'transparent' }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadServices(true)} tintColor="#145C3B" />}
        contentContainerStyle={{ paddingHorizontal: 14, paddingTop: 14, paddingBottom: 34, gap: 13, backgroundColor: 'transparent' }}
      >
        <View style={{ paddingHorizontal: 3, paddingVertical: 5, gap: 4 }}>
          <Text style={{ color: '#103F2B', fontSize: 27, fontWeight: '900', letterSpacing: -0.8 }}>Services Catalog</Text>
          <Text style={{ color: '#244F3A', fontSize: 12, fontWeight: '600' }}>Browse services configured by your organization</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
            <Leaf size={21} color="#3C8A38" fill="#7CBF48" />
            <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>Service Directory</Text>
          </View>
          <Pill label="Read only" tone="neutral" />
        </View>
        <SearchField value={catalogSearch} onChangeText={setCatalogSearch} placeholder="Search service, category or issue…" />
        {error ? <ErrorBanner message={error} /> : null}
        {loading ? <View style={{ padding: 28, alignItems: 'center' }}><ActivityIndicator color={colors.forest} /><Text style={{ color: colors.muted, marginTop: 9, fontSize: 12 }}>Loading services…</Text></View>
          : visible.length === 0 ? <EmptyState title="No services found" detail="No configured services match your search." onRetry={() => loadServices(true)} />
            : visible.map((item) => {
              const serviceType = SERVICE_CATALOGUE_TAXONOMY.find((entry) => normalizeCatalogValue(entry.name) === normalizeCatalogValue(item.service_type));
              return (
                <Card key={String(item.id)} style={{ padding: 12, borderRadius: 21, borderColor: '#D8E8D4', backgroundColor: 'rgba(255,255,255,0.95)', gap: 9, elevation: 3 }}>
                  <View style={{ flexDirection: 'row', gap: 11 }}>
                    <CatalogRemoteImage path={serviceType?.image} style={{ width: 76, height: 76, borderRadius: 12 }} />
                    <View style={{ flex: 1, gap: 4 }}>
                      <Text style={{ color: colors.forest, fontWeight: '900', fontSize: 11 }}>{text(item.service_type)}</Text>
                      <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 13 }}>{text(item.issue)}</Text>
                      <Text style={{ color: colors.muted, fontSize: 10 }}>{text(item.category)}</Text>
                      <Pill label={item.is_active ? 'Active' : 'Inactive'} tone={item.is_active ? 'green' : 'neutral'} />
                    </View>
                  </View>
                </Card>
              );
            })}
      </ScrollView>
      </ImageBackground>
    );
  };

  if (!canManage) return renderReadOnlyCatalog();

  return (
    <ImageBackground
      source={require('../../../assets/team/nature_team_background.png')}
      resizeMode="cover"
      imageStyle={{ opacity: 1 }}
      style={{ flex: 1, backgroundColor: '#E8F1E6' }}
    >
    <ScrollView
      style={{ flex: 1, backgroundColor: 'transparent' }}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ paddingHorizontal: 14, paddingTop: 14, paddingBottom: 34, gap: 13, backgroundColor: 'transparent' }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadServices(true)} tintColor="#145C3B" />}
    >
      <View style={{ paddingHorizontal: 3, paddingVertical: 5, gap: 4 }}>
        <Text style={{ color: '#103F2B', fontSize: 27, fontWeight: '900', letterSpacing: -0.8 }}>Services</Text>
        <Text style={{ color: '#244F3A', fontSize: 12, fontWeight: '600' }}>Configure the services your organization provides</Text>
      </View>

      <View style={{ flexDirection: 'row', gap: 6 }}>
        {([
          { number: 1, label: 'Service type' },
          { number: 2, label: 'Categories' },
          { number: 3, label: 'Issues' },
        ] as const).map((item) => (
          <View key={item.number} style={{ flex: 1, gap: 6 }}>
            <View style={{ height: 5, borderRadius: 99, backgroundColor: step >= item.number ? colors.green : '#DCE6DF' }} />
            <Text style={{ color: step === item.number ? colors.forest : colors.muted, fontSize: 9, fontWeight: step === item.number ? '900' : '700', textAlign: 'center' }}>{item.label}</Text>
          </View>
        ))}
      </View>

      {error ? <ErrorBanner message={error} /> : null}
      {loading ? (
        <View style={{ paddingVertical: 34, alignItems: 'center', gap: 10 }}>
          <ActivityIndicator size="large" color={colors.forest} />
          <Text style={{ color: colors.muted, fontSize: 12 }}>Loading your organization's service selections…</Text>
        </View>
      ) : (
        <>
          {step === 1 ? (
            <>
              <View style={{ gap: 4, paddingHorizontal: 2 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
                  <Leaf size={21} color="#3C8A38" fill="#7CBF48" />
                  <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>Select Service Type</Text>
                </View>
                <Text style={{ color: '#244F3A', fontSize: 11, fontWeight: '600' }}>Choose a service type to configure its categories and issues.</Text>
              </View>
              <SearchField value={serviceSearch} onChangeText={setServiceSearch} placeholder="Search 16 service types…" />
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 }}>
                {visibleServiceTypes.map((serviceType) => {
                  const activeCount = activeIssueCountForType(serviceType);
                  const selected = selectedServiceType?.id === serviceType.id;
                  return (
                    <Card
                      key={serviceType.id}
                      onPress={() => chooseServiceType(serviceType)}
                      style={{ width: '48.5%', padding: 9, gap: 8, borderColor: selected ? '#3ABF32' : '#D8E8D4', borderWidth: selected ? 2 : 1, borderRadius: 19, backgroundColor: 'rgba(255,255,255,0.95)', elevation: 2 }}
                    >
                      <View style={{ height: 104, borderRadius: 11, overflow: 'hidden', backgroundColor: '#F8FAFC' }}>
                        <CatalogRemoteImage path={serviceType.image} style={{ flex: 1 }} />
                        {activeCount > 0 ? <SelectionBadge count={activeCount} /> : null}
                      </View>
                      <Text numberOfLines={2} style={{ color: colors.ink, fontSize: 12, lineHeight: 16, fontWeight: '900', minHeight: 32 }}>{serviceType.name}</Text>
                      <Text numberOfLines={3} style={{ color: colors.muted, fontSize: 9, lineHeight: 13, minHeight: 38 }}>{serviceType.description}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                        <Text style={{ color: activeCount > 0 ? colors.forest : colors.muted, fontSize: 9, fontWeight: '800' }}>{activeCount} active issues</Text>
                        <ChevronRight size={15} color={colors.forest} />
                      </View>
                    </Card>
                  );
                })}
              </View>
              {visibleServiceTypes.length === 0 ? <EmptyState title="No service types found" detail="Try a different search term." /> : null}
            </>
          ) : null}

          {step === 2 && selectedServiceType ? (
            <>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 2 }}>
                <Leaf size={21} color="#3C8A38" fill="#7CBF48" />
                <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>Service Categories</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Pressable onPress={goBack} disabled={saving} style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowLeft size={18} color={colors.forest} />
                </Pressable>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '800' }}>{selectedServiceType.name.toUpperCase()} / SERVICE TYPE</Text>
                  <Text style={{ color: colors.ink, fontSize: 17, fontWeight: '900' }}>Step 2: Categories</Text>
                </View>
                <Pill label={`${selectedServiceType.categories.length} categories`} tone="green" />
              </View>
              <SearchField value={categorySearch} onChangeText={setCategorySearch} placeholder="Search categories…" />
              {renderWizardSummary()}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 12 }}>
                {visibleCategories.map((category) => {
                  const selectedCount = (selectedIssuesByCategory[category.id] || []).length;
                  const imagePath = getCategoryCardImage(category.id, selectedServiceType.id);
                  return (
                    <Card
                      key={category.id}
                      onPress={() => openCategory(category)}
                      style={{ width: '48.5%', padding: 0, overflow: 'hidden', gap: 0, borderColor: selectedCount > 0 ? '#3ABF32' : '#D8E8D4', borderWidth: selectedCount > 0 ? 1.5 : 1, borderRadius: 19, backgroundColor: 'rgba(255,255,255,0.95)', elevation: 2 }}
                    >
                      <View style={{ height: 112, position: 'relative' }}>
                        <CatalogRemoteImage path={imagePath} style={{ flex: 1 }} />
                        {selectedCount > 0 ? <SelectionBadge count={selectedCount} /> : null}
                      </View>
                      <View style={{ padding: 10, gap: 5, minHeight: 68 }}>
                        <Text numberOfLines={3} style={{ color: colors.ink, fontSize: 11, lineHeight: 15, fontWeight: '900' }}>{category.name}</Text>
                        <Text style={{ color: selectedCount > 0 ? colors.forest : colors.muted, fontSize: 9, fontWeight: '800' }}>{selectedCount > 0 ? `${selectedCount} selected` : `${category.issues.length} issues`}</Text>
                      </View>
                    </Card>
                  );
                })}
              </View>
              {visibleCategories.length === 0 ? <EmptyState title="No categories found" detail="Try another category search." /> : null}
            </>
          ) : null}

          {step === 3 && selectedServiceType && activeCategory ? (
            <>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 2 }}>
                <Leaf size={21} color="#3C8A38" fill="#7CBF48" />
                <Text style={{ color: '#103F2B', fontSize: 19, fontWeight: '900' }}>Service Issues</Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <Pressable onPress={goBack} disabled={saving} style={{ width: 38, height: 38, borderRadius: 12, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }}>
                  <ArrowLeft size={18} color={colors.forest} />
                </Pressable>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={{ color: colors.muted, fontSize: 10, fontWeight: '800' }}>{selectedServiceType.name.toUpperCase()} / CATEGORY</Text>
                  <Text numberOfLines={2} style={{ color: colors.ink, fontSize: 16, fontWeight: '900' }}>{activeCategory.name}</Text>
                </View>
              </View>
              <SearchField value={issueSearch} onChangeText={setIssueSearch} placeholder="Search issues…" />
              <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                <Pill label={`${(selectedIssuesByCategory[activeCategory.id] || []).length} of ${activeCategory.issues.length} selected`} tone="green" />
                <View style={{ flexDirection: 'row', gap: 7 }}>
                  <PrimaryButton title="Select All" compact variant="secondary" onPress={selectAllIssues} disabled={saving} />
                  <PrimaryButton title="Deselect All" compact variant="ghost" onPress={deselectAllIssues} disabled={saving} />
                </View>
              </View>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 11 }}>
                {visibleIssues.map((issue) => {
                  const selected = (selectedIssuesByCategory[activeCategory.id] || [])
                    .some((item) => normalizeCatalogValue(item) === normalizeCatalogValue(issue));
                  const imagePath = getIssueCardImage(issue, activeCategory.id, selectedServiceType.id, activeCategory.issues.indexOf(issue));
                  return (
                    <Card
                      key={issue}
                      onPress={() => toggleIssue(issue)}
                      style={{ width: '48.5%', padding: 0, overflow: 'hidden', gap: 0, borderColor: selected ? '#3ABF32' : '#D8E8D4', borderWidth: selected ? 2 : 1, borderRadius: 19, backgroundColor: 'rgba(255,255,255,0.95)', elevation: 2 }}
                    >
                      <View style={{ height: 112, position: 'relative' }}>
                        <CatalogRemoteImage path={imagePath} style={{ flex: 1 }} />
                        <View style={{ position: 'absolute', top: 7, right: 7, width: 24, height: 24, borderRadius: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: selected ? colors.green : 'rgba(255,255,255,0.96)', borderWidth: 1, borderColor: selected ? colors.green : '#94A3B8' }}>
                          {selected ? <Check size={15} color={colors.white} strokeWidth={3} /> : null}
                        </View>
                      </View>
                      <View style={{ minHeight: 64, padding: 10, justifyContent: 'center' }}>
                        <Text style={{ color: colors.ink, fontSize: 10, lineHeight: 14, fontWeight: '800' }}>{issue}</Text>
                      </View>
                    </Card>
                  );
                })}
              </View>
              {visibleIssues.length === 0 ? <EmptyState title="No issues found" detail="Try another issue search." /> : null}
            </>
          ) : null}
        </>
      )}

      {step !== 1 ? renderWizardSummary() : null}
      {step !== 1 ? (
        <PrimaryButton
          title={saving ? 'Saving services…' : `Save ${selectedIssueCount} selected issues`}
          onPress={() => void handleSave()}
          loading={saving}
          disabled={loading || !selectedServiceType}
        />
      ) : (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 13, backgroundColor: '#F3F8F5' }}>
          <Layers3 size={17} color={colors.forest} />
          <Text style={{ flex: 1, color: colors.muted, fontSize: 10, lineHeight: 15 }}>Select a service type to review its categories and choose the exact issues your organization offers.</Text>
        </View>
      )}

      {!loading && services.length > 0 ? (
        <Text style={{ color: colors.muted, fontSize: 10, textAlign: 'center' }}>
          {services.filter((item) => item.is_active).length} active organization service offerings
        </Text>
      ) : null}
    </ScrollView>
    </ImageBackground>
  );
}
