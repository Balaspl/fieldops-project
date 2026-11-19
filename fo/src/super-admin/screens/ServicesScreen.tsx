
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from 'react-native';
import { ShieldCheck, Wrench, X } from 'lucide-react-native';

import { useAuth } from '../auth/AuthContext';
import {
  createService,
  deleteService,
  getServices,
  getTaxonomy,
  toggleService,
} from '../api/operations';

import {
  Card,
  EmptyState,
  ErrorBanner,
  Field,
  Pill,
  PrimaryButton,
  ScreenHeading,
  ScreenScroll,
  SearchField,
  SectionTitle,
} from '../components/UI';

import { colors } from '../theme';
import { text } from '../utils/format';

const SERVICE_IMAGES: Record<string, any> = {
  ac: require('../../../assets/services/ac_refrigeration.png'),
  hvac: require('../../../assets/services/ac_refrigeration.png'),
  electrical: require('../../../assets/services/electrical.png'),
  plumbing: require('../../../assets/services/plumbing.png'),
  'home appliances': require('../../../assets/services/appliances.png'),
  appliances: require('../../../assets/services/appliances.png'),
  carpentry: require('../../../assets/services/carpentry.png'),
  civil: require('../../../assets/services/civil_masonry.png'),
  masonry: require('../../../assets/services/civil_masonry.png'),
  cleaning: require('../../../assets/services/cleaning.png'),
  doors: require('../../../assets/services/doors_windows.png'),
  windows: require('../../../assets/services/doors_windows.png'),
  gardening: require('../../../assets/services/gardening.png'),
  handyman: require('../../../assets/services/handyman.png'),
  it: require('../../../assets/services/it_networking.png'),
  network: require('../../../assets/services/it_networking.png'),
  painting: require('../../../assets/services/painting.png'),
  pest: require('../../../assets/services/pest_control.png'),
  security: require('../../../assets/services/security.png'),
  solar: require('../../../assets/services/solar_backup.png'),
  water: require('../../../assets/services/water_purifier.png'),
};

function serviceImage(name: string) {
  const normalized = String(name || '').toLowerCase();

  const key = Object.keys(SERVICE_IMAGES).find(candidate =>
    normalized.includes(candidate)
  );

  return key
    ? SERVICE_IMAGES[key]
    : require('../../../assets/services/handyman.png');
}

const EMPTY_FORM = {
  service_type: '',
  category: '',
  issue: '',
  description: '',
  priority: 'NORMAL',
};

export default function ServicesScreen() {
  const { role } = useAuth();

  const canManage = role === 'super_admin';

  const [services, setServices] = useState<any[]>([]);
  const [taxonomy, setTaxonomy] = useState<any>({
    service_types: [],
    categories_by_type: {},
    issues_by_category: {},
  });

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const [search, setSearch] = useState('');

  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState(EMPTY_FORM);

  // --------------------------------------------------
  // LOAD SERVICE CATALOG
  // --------------------------------------------------

  const load = useCallback(async (silent = false) => {
    if (silent) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError('');

    try {
      const [rows, suggestions] = await Promise.all([
        getServices(),
        getTaxonomy().catch(() => ({})),
      ]);

      console.log('[ServicesScreen] API services count:', rows.length);
      console.log('[ServicesScreen] API services:', rows);

      setServices(rows);
      setTaxonomy(suggestions || {});
    } catch (e: any) {
      console.error('[ServicesScreen] Load failed:', e);

      setError(
        e?.response?.data?.detail ||
          e?.message ||
          'Unable to load the service catalog.'
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // --------------------------------------------------
  // SEARCH
  // --------------------------------------------------

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();

    return services.filter(item => {
      if (!term) return true;

      return [
        item.service_type,
        item.category,
        item.issue,
        item.description,
        item.required_skill,
      ].some(value =>
        String(value || '').toLowerCase().includes(term)
      );
    });
  }, [services, search]);

  const serviceTypes: string[] =
    taxonomy?.service_types || [];

  const categories: string[] =
    taxonomy?.categories_by_type?.[form.service_type] || [];

  const issues: any[] =
    taxonomy?.issues_by_category?.[form.category] || [];

  // --------------------------------------------------
  // RESET AND CLOSE FORM
  // --------------------------------------------------

  const openCreateForm = () => {
    setForm(EMPTY_FORM);
    setFormOpen(true);
  };

  const closeForm = () => {
    if (saving) return;

    setFormOpen(false);
    setForm(EMPTY_FORM);
  };

  // --------------------------------------------------
  // CREATE SERVICE
  // --------------------------------------------------

  const save = async () => {
    if (
      !form.service_type.trim() ||
      !form.category.trim() ||
      !form.issue.trim()
    ) {
      Alert.alert(
        'Required fields',
        'Service type, category and issue are required.'
      );
      return;
    }

    setSaving(true);

    try {
      const payload = {
        service_type: form.service_type.trim(),
        category: form.category.trim(),
        issue: form.issue.trim(),
        description: form.description.trim() || undefined,
        priority: form.priority,
      };

      console.log('[ServicesScreen] Creating service:', payload);

      await createService(payload);

      setFormOpen(false);
      setForm(EMPTY_FORM);

      await load(true);

      Alert.alert(
        'Service created',
        'The service catalog has been updated.'
      );
    } catch (e: any) {
      console.error('[ServicesScreen] Create failed:', e);

      Alert.alert(
        'Could not create service',
        e?.response?.data?.detail ||
          e?.message ||
          'Please try again.'
      );
    } finally {
      setSaving(false);
    }
  };

  // --------------------------------------------------
  // ACTIVATE / DEACTIVATE
  // --------------------------------------------------

  const changeActive = async (item: any) => {
    try {
      await toggleService(Number(item.id));
      await load(true);
    } catch (e: any) {
      Alert.alert(
        'Update failed',
        e?.response?.data?.detail ||
          e?.message ||
          'Could not change service availability.'
      );
    }
  };

  // --------------------------------------------------
  // DELETE SERVICE
  // --------------------------------------------------

  const remove = (item: any) => {
    Alert.alert(
      'Delete service?',
      `Remove "${item.issue}" from the catalog? This operation is permanent.`,
      [
        {
          text: 'Cancel',
          style: 'cancel',
        },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteService(Number(item.id));
              await load(true);
            } catch (e: any) {
              Alert.alert(
                'Delete failed',
                e?.response?.data?.detail ||
                  e?.message ||
                  'Could not delete service.'
              );
            }
          },
        },
      ]
    );
  };

  // --------------------------------------------------
  // TAXONOMY SUGGESTION BUTTON
  // --------------------------------------------------

  const Suggestion = ({
    value,
    selected,
    onPress,
  }: {
    value: string;
    selected: boolean;
    onPress: () => void;
  }) => (
    <View style={{ marginRight: 7, marginBottom: 7 }}>
      <PrimaryButton
        title={value}
        compact
        variant={selected ? 'primary' : 'secondary'}
        onPress={onPress}
      />
    </View>
  );

  // --------------------------------------------------
  // UI
  // --------------------------------------------------

  return (
    <>
      <ScreenScroll
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => load(true)}
            tintColor={colors.forest}
          />
        }
      >
        {/* HEADER */}

        <ScreenHeading
          title="Services catalog"
          subtitle={
            canManage
              ? 'Manage your organization’s service taxonomy.'
              : 'Browse services configured by your organization.'
          }
          action={
            canManage ? (
              <PrimaryButton
                title="Add service"
                compact
                onPress={openCreateForm}
              />
            ) : (
              <Pill label="Read only" tone="neutral" />
            )
          }
        />

        {/* BANNER */}

        <Card
          style={{
            padding: 0,
            overflow: 'hidden',
            gap: 0,
          }}
        >
          <Image
            source={require('../../../assets/services/user_banner.png')}
            resizeMode="cover"
            style={{
              width: '100%',
              height: 140,
            }}
          />

          <View style={{ padding: 14, gap: 4 }}>
            <Text
              style={{
                color: colors.ink,
                fontSize: 17,
                fontWeight: '900',
              }}
            >
              Service coverage
            </Text>

            <Text
              style={{
                color: colors.muted,
                fontSize: 11,
                lineHeight: 16,
              }}
            >
              Browse and manage services available in the FieldOps catalog.
            </Text>
          </View>
        </Card>

        {/* STATISTICS */}

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Card style={{ flex: 1, padding: 13 }}>
            <Text style={{ color: colors.muted, fontSize: 10 }}>
              Catalog entries
            </Text>

            <Text
              style={{
                color: colors.ink,
                fontSize: 22,
                fontWeight: '900',
              }}
            >
              {services.length}
            </Text>
          </Card>

          <Card style={{ flex: 1, padding: 13 }}>
            <Text style={{ color: colors.muted, fontSize: 10 }}>
              Active services
            </Text>

            <Text
              style={{
                color: colors.forest,
                fontSize: 22,
                fontWeight: '900',
              }}
            >
              {services.filter(s => s.is_active).length}
            </Text>
          </Card>
        </View>

        {/* SEARCH */}

        <SearchField
          value={search}
          onChangeText={setSearch}
          placeholder="Search service, category, issue or skill…"
        />

        {error ? <ErrorBanner message={error} /> : null}

        {/* SERVICE LIST */}

        <SectionTitle
          title="Available services"
          subtitle={`Service type → category → issue (${visible.length} entries)`}
        />

        {loading ? (
          <Text
            style={{
              color: colors.muted,
              textAlign: 'center',
              padding: 25,
            }}
          >
            Loading service catalog…
          </Text>
        ) : visible.length === 0 ? (
          <EmptyState
            title="No services found"
            detail={
              search
                ? 'Try a different search term.'
                : 'Your organization has not configured any service entries yet.'
            }
            onRetry={() => load(true)}
          />
        ) : (
          visible.map(item => (
            <Card
              key={String(item.id)}
              style={{
                padding: 0,
                overflow: 'hidden',
                gap: 0,
              }}
            >
              <View
                style={{
                  flexDirection: 'row',
                  gap: 12,
                  padding: 13,
                }}
              >
                <Image
                  source={serviceImage(item.service_type)}
                  resizeMode="cover"
                  style={{
                    width: 82,
                    height: 82,
                    borderRadius: 14,
                    backgroundColor: colors.mint,
                  }}
                />

                <View style={{ flex: 1, gap: 5 }}>
                  <View
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 6,
                    }}
                  >
                    <Text
                      style={{
                        color: colors.forest,
                        fontSize: 10,
                        fontWeight: '900',
                        flex: 1,
                      }}
                    >
                      {text(item.service_type)}
                    </Text>

                    <Pill
                      label={item.is_active ? 'Active' : 'Inactive'}
                      tone={item.is_active ? 'green' : 'neutral'}
                    />
                  </View>

                  <Text
                    style={{
                      color: colors.ink,
                      fontSize: 14,
                      fontWeight: '900',
                    }}
                  >
                    {text(item.issue)}
                  </Text>

                  <Text
                    style={{
                      color: colors.muted,
                      fontSize: 10,
                    }}
                  >
                    {text(item.category)}
                  </Text>

                  <Text
                    style={{
                      color: colors.text,
                      fontSize: 10,
                    }}
                    numberOfLines={2}
                  >
                    {text(
                      item.description,
                      'No additional description.'
                    )}
                  </Text>
                </View>
              </View>

              <View
                style={{
                  borderTopWidth: 1,
                  borderTopColor: colors.softBorder,
                  paddingHorizontal: 13,
                  paddingVertical: 10,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 8,
                  flexWrap: 'wrap',
                }}
              >
                <Text
                  style={{
                    color: colors.muted,
                    fontSize: 10,
                    flex: 1,
                  }}
                >
                  Required skill: {text(item.required_skill, 'Not specified')}
                </Text>

                {canManage ? (
                  <View
                    style={{
                      flexDirection: 'row',
                      gap: 7,
                    }}
                  >
                    <PrimaryButton
                      title={item.is_active ? 'Deactivate' : 'Activate'}
                      compact
                      variant="secondary"
                      onPress={() => void changeActive(item)}
                    />

                    <PrimaryButton
                      title="Delete"
                      compact
                      variant="danger"
                      onPress={() => remove(item)}
                    />
                  </View>
                ) : (
                  <ShieldCheck
                    size={16}
                    color={colors.forest}
                  />
                )}
              </View>
            </Card>
          ))
        )}

        {/* FOOTER */}

        <Card style={{ backgroundColor: '#F3F8F5' }}>
          <Text
            style={{
              color: colors.muted,
              fontSize: 10,
              lineHeight: 16,
            }}
          >
            {canManage
              ? 'Changes are applied to the backend service catalog used by the web app and customer service request flow.'
              : 'Dispatcher access is read-only, matching the web application service catalog permission.'}
          </Text>
        </Card>
      </ScreenScroll>

      {/* --------------------------------------------------
          CREATE SERVICE MODAL
      -------------------------------------------------- */}

      <Modal
        visible={formOpen}
        transparent
        animationType="fade"
        statusBarTranslucent
        onRequestClose={closeForm}
      >
        <KeyboardAvoidingView
          style={{
            flex: 1,
            backgroundColor: 'rgba(7,25,16,.60)',
            justifyContent: 'center',
            paddingHorizontal: 16,
            paddingVertical: 24,
          }}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <View
            style={{
              backgroundColor: colors.canvas,
              borderRadius: 22,
              width: '100%',
              maxHeight: '88%',
              overflow: 'hidden',
            }}
          >
            {/* MODAL HEADER */}

            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                paddingHorizontal: 18,
                paddingVertical: 15,
                borderBottomWidth: 1,
                borderBottomColor: colors.softBorder,
                gap: 10,
              }}
            >
              <View
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 13,
                  backgroundColor: colors.mint,
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Wrench size={20} color={colors.forest} />
              </View>

              <View style={{ flex: 1, gap: 3 }}>
                <Text
                  style={{
                    color: colors.ink,
                    fontSize: 18,
                    fontWeight: '900',
                  }}
                >
                  Add catalog service
                </Text>

                <Text
                  style={{
                    color: colors.muted,
                    fontSize: 10,
                  }}
                >
                  Create a new service taxonomy entry.
                </Text>
              </View>

              <PrimaryButton
                title="Cancel"
                compact
                variant="ghost"
                onPress={closeForm}
              />
            </View>

            {/* SCROLLABLE FORM CONTENT */}

            <ScrollView
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator
              contentContainerStyle={{
                padding: 18,
                paddingBottom: 24,
                gap: 14,
              }}
            >
              {/* SERVICE TYPE */}

              <View style={{ gap: 8 }}>
                <Field
                  label="SERVICE TYPE"
                  value={form.service_type}
                  onChangeText={service_type =>
                    setForm(p => ({
                      ...p,
                      service_type,
                      category: '',
                      issue: '',
                    }))
                  }
                  placeholder="e.g. Electrical"
                />

                {serviceTypes.length > 0 ? (
                  <View
                    style={{
                      flexDirection: 'row',
                      flexWrap: 'wrap',
                    }}
                  >
                    {serviceTypes.map(value => (
                      <Suggestion
                        key={value}
                        value={value}
                        selected={form.service_type === value}
                        onPress={() =>
                          setForm(p => ({
                            ...p,
                            service_type: value,
                            category: '',
                            issue: '',
                          }))
                        }
                      />
                    ))}
                  </View>
                ) : null}
              </View>

              {/* CATEGORY */}

              <View style={{ gap: 8 }}>
                <Field
                  label="CATEGORY"
                  value={form.category}
                  onChangeText={category =>
                    setForm(p => ({
                      ...p,
                      category,
                      issue: '',
                    }))
                  }
                  placeholder="e.g. Wiring & Switchboards"
                />

                {categories.length > 0 ? (
                  <View
                    style={{
                      flexDirection: 'row',
                      flexWrap: 'wrap',
                    }}
                  >
                    {categories.map(value => (
                      <Suggestion
                        key={value}
                        value={value}
                        selected={form.category === value}
                        onPress={() =>
                          setForm(p => ({
                            ...p,
                            category: value,
                            issue: '',
                          }))
                        }
                      />
                    ))}
                  </View>
                ) : null}
              </View>

              {/* ISSUE */}

              <View style={{ gap: 8 }}>
                <Field
                  label="ISSUE / SERVICE"
                  value={form.issue}
                  onChangeText={issue =>
                    setForm(p => ({
                      ...p,
                      issue,
                    }))
                  }
                  placeholder="Specific issue handled"
                />

                {issues.length > 0 ? (
                  <View
                    style={{
                      flexDirection: 'row',
                      flexWrap: 'wrap',
                    }}
                  >
                    {issues.map((entry: any, index: number) => {
                      const value =
                        typeof entry === 'string'
                          ? entry
                          : entry.issue;

                      if (!value) return null;

                      return (
                        <Suggestion
                          key={`${value}-${index}`}
                          value={value}
                          selected={form.issue === value}
                          onPress={() =>
                            setForm(p => ({
                              ...p,
                              issue: value,
                            }))
                          }
                        />
                      );
                    })}
                  </View>
                ) : null}
              </View>

              {/* DESCRIPTION */}

              <Field
                label="DESCRIPTION (OPTIONAL)"
                value={form.description}
                onChangeText={description =>
                  setForm(p => ({
                    ...p,
                    description,
                  }))
                }
                placeholder="What is included in this service?"
                multiline
                numberOfLines={3}
              />

              {/* PRIORITY */}

              <View style={{ gap: 8 }}>
                <Text
                  style={{
                    color: colors.muted,
                    fontSize: 10,
                    fontWeight: '900',
                  }}
                >
                  PRIORITY
                </Text>

                <View
                  style={{
                    flexDirection: 'row',
                    gap: 8,
                  }}
                >
                  <View style={{ flex: 1 }}>
                    <PrimaryButton
                      title="Normal"
                      compact
                      variant={
                        form.priority === 'NORMAL'
                          ? 'primary'
                          : 'secondary'
                      }
                      onPress={() =>
                        setForm(p => ({
                          ...p,
                          priority: 'NORMAL',
                        }))
                      }
                    />
                  </View>

                  <View style={{ flex: 1 }}>
                    <PrimaryButton
                      title="High"
                      compact
                      variant={
                        form.priority === 'High Priority'
                          ? 'primary'
                          : 'secondary'
                      }
                      onPress={() =>
                        setForm(p => ({
                          ...p,
                          priority: 'High Priority',
                        }))
                      }
                    />
                  </View>
                </View>
              </View>

              {/* ACTIONS */}

              <View
                style={{
                  gap: 9,
                  paddingTop: 5,
                }}
              >
                <PrimaryButton
                  title="Create service"
                  onPress={save}
                  loading={saving}
                />

                <PrimaryButton
                  title="Cancel"
                  variant="ghost"
                  onPress={closeForm}
                />
              </View>
            </ScrollView>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </>
  );
}
