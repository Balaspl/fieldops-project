import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Image,
  ImageBackground,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import Feather from "@expo/vector-icons/Feather";
import { customerApi } from "../../../src/customer/api/customer";
import type { ServiceCatalogItem } from "../../../src/customer/types/api";
import { useFocusedAutoRefresh } from "../../../src/customer/hooks/useFocusedAutoRefresh";
import { SERVICE_CATALOGUE_TAXONOMY, type TaxonomyServiceType } from "../../../src/customer/data/serviceCatalogueTaxonomy";

const ASSETS =
  "https://raw.githubusercontent.com/ryeswanthkumar/fieldops-project/feature/current-work/frontend/public/services";

const HERO_IMAGE = `${ASSETS}/banner_clean_perfect.png`;

type ServiceCategory = {
  id: string;
  title: string;
  description: string;
  image: string;
  badgeBackground: string;
  badgeColor: string;
  taxonomy: TaxonomyServiceType;
};

const CATEGORIES: ServiceCategory[] = SERVICE_CATALOGUE_TAXONOMY.map((taxonomy) => ({
  id: taxonomy.id,
  title: taxonomy.name,
  description: taxonomy.description,
  image: `${ASSETS}/${taxonomy.image.split("/").pop()}`,
  badgeBackground: taxonomy.theme.bg,
  badgeColor: taxonomy.theme.color,
  taxonomy,
}));

function normalizeCatalogValue(value?: string | null): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

/**
 * Match a catalogue item to one category using exact normalized values.
 * Avoid substring matching: for example, "electrical" must not accidentally
 * match an unrelated value that merely contains the same text.
 */
function catalogItemMatchesCategory(
  item: ServiceCatalogItem,
  category: ServiceCategory,
): boolean {
  const itemType = normalizeCatalogValue(item.service_type);
  const itemCategory = normalizeCatalogValue(item.category);

  const categoryTypeValues = [
    category.taxonomy.id,
    category.taxonomy.name,
  ]
    .map(normalizeCatalogValue)
    .filter(Boolean);

  const taxonomyCategoryValues = category.taxonomy.categories
    .flatMap((entry) => [entry.id, entry.name])
    .map(normalizeCatalogValue)
    .filter(Boolean);

  return (
    (itemType.length > 0 && categoryTypeValues.includes(itemType)) ||
    (itemCategory.length > 0 && taxonomyCategoryValues.includes(itemCategory))
  );
}

/**
 * A catalogue API response should contain one record per service.
 * Prefer the backend ID when available; otherwise use the service fields
 * as a stable fallback so repeated copies of the same record are not counted.
 */
function getCatalogItemIdentity(item: ServiceCatalogItem): string {
  const rawItem = item as ServiceCatalogItem & {
    id?: string | number;
    service_id?: string | number;
    catalog_item_id?: string | number;
    name?: string;
    title?: string;
  };

  const id = rawItem.id ?? rawItem.service_id ?? rawItem.catalog_item_id;
  if (id !== undefined && id !== null && String(id).trim() !== "") {
    return `id:${String(id).trim()}`;
  }

  return [
    rawItem.service_type,
    rawItem.category,
    rawItem.issue,
    rawItem.name ?? rawItem.title,
  ]
    .map((value) => normalizeCatalogValue(value))
    .join("|");
}

export default function CustomerHomeScreen() {
  const router = useRouter();
  const [searchText, setSearchText] = useState("");
  const [serviceCatalog, setServiceCatalog] = useState<ServiceCatalogItem[]>([]);
  const [catalogLoaded, setCatalogLoaded] = useState(false);
  const [catalogLoadFailed, setCatalogLoadFailed] = useState(false);

  const refreshCatalog = useCallback(async () => {
    try {
      const items = await customerApi.catalog();
      setServiceCatalog(items.filter((item) => item.is_active !== false));
      setCatalogLoadFailed(false);
      setCatalogLoaded(true);
    } catch {
      setCatalogLoadFailed(true);
      setCatalogLoaded(true);
    }
  }, []);

  useEffect(() => {
    void refreshCatalog();
  }, [refreshCatalog]);

  useFocusedAutoRefresh(refreshCatalog);

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = {};

    for (const category of CATEGORIES) {
      const matchingServices = serviceCatalog.filter(
        (item) => catalogItemMatchesCategory(item, category),
      );

      counts[category.id] = new Set(
        matchingServices.map(getCatalogItemIdentity),
      ).size;
    }

    return counts;
  }, [serviceCatalog]);

  const openRequests = (params?: {
    category?: string;
    search?: string;
  }) => {
    router.push({
      pathname: "/customer/(tabs)/requests",
      params: {
        ...(params?.category
          ? { category: params.category }
          : {}),
        ...(params?.search ? { search: params.search } : {}),
      },
    } as never);
  };

  const handleSearch = () => {
    const query = searchText.trim();

    if (!query) {
      Alert.alert(
        "Find a service",
        "Enter a service name, such as AC repair, plumbing or electrical work.",
      );
      return;
    }

    openRequests({ search: query });
  };

  const handleCategoryPress = (category: ServiceCategory) => {
    router.push({
      pathname: "/customer/requests/new",
      params: {
        serviceType: category.id,
      },
    } as never);
  };

  return (
    <SafeAreaView
      style={styles.safeArea}
      edges={["top", "left", "right"]}
    >
      <StatusBar
        barStyle="dark-content"
        backgroundColor="#FFFFFF"
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
      >
        {/* Premium FieldOps header */}
        <View style={styles.header}>
          <Image
            source={require("../../../assets/customer/images/fieldops-logo.png")}
            style={styles.logo}
            resizeMode="contain"
            accessibilityLabel="FieldOps Commander"
          />

          <View style={styles.headerActions}>
            <Pressable
              style={styles.locationButton}
              onPress={() =>
                Alert.alert(
                  "Service location",
                  "You can confirm your service address when booking a service.",
                )
              }
              accessibilityRole="button"
              accessibilityLabel="Service location"
            >
              <Feather
                name="map-pin"
                size={17}
                color="#00865F"
              />

              <Text
                style={styles.locationText}
                numberOfLines={1}
              >
                Chennai, Tamil Nadu
              </Text>

              <Feather
                name="chevron-down"
                size={15}
                color="#168366"
              />
            </Pressable>

            <Pressable
              style={styles.notificationButton}
              onPress={() => router.push("/customer/notifications" as never)}
              accessibilityRole="button"
              accessibilityLabel="Notifications"
              hitSlop={8}
            >
              <Feather
                name="bell"
                size={22}
                color="#183454"
              />
            </Pressable>
          </View>
        </View>

        {/* Main service search banner */}
        <ImageBackground
          source={{ uri: HERO_IMAGE }}
          style={styles.hero}
          imageStyle={styles.heroImage}
          resizeMode="cover"
        >
          <View style={styles.heroOverlay}>
            <Text style={styles.heroTitle}>
              What service do you need today?
            </Text>

            <Text style={styles.heroSubtitle}>
              Find trusted professionals for your home
            </Text>

            <View style={styles.searchBar}>
              <Feather
                name="search"
                size={21}
                color="#00865F"
              />

              <TextInput
                value={searchText}
                onChangeText={setSearchText}
                onSubmitEditing={handleSearch}
                placeholder="Search AC repair, plumbing, electrical..."
                placeholderTextColor="#8995A8"
                style={styles.searchInput}
                returnKeyType="search"
                accessibilityLabel="Search for a service"
              />

              <Pressable
                onPress={handleSearch}
                style={({ pressed }) => [
                  styles.searchButton,
                  pressed && styles.pressed,
                ]}
                accessibilityRole="button"
              >
                <Text style={styles.searchButtonText}>
                  Search
                </Text>
              </Pressable>
            </View>
          </View>
        </ImageBackground>

        {/* Category section heading */}
        <View style={styles.sectionHeader}>
          <View style={styles.sectionTitleGroup}>
            <View style={styles.categoryIconBox}>
              <Feather
                name="grid"
                size={24}
                color="#07875F"
              />
            </View>

            <Text style={styles.sectionTitle}>
              Browse Service Categories
            </Text>
          </View>

          <Pressable
            onPress={() => openRequests()}
            style={styles.viewAllButton}
            accessibilityRole="button"
          >
            <Text style={styles.viewAllText}>
              View all
            </Text>

            <Feather
              name="chevron-right"
              size={18}
              color="#00865F"
            />
          </Pressable>
        </View>

        {/* Two-column image card grid */}
        <View style={styles.categoryGrid}>
          {CATEGORIES.map((category) => (
            <Pressable
              key={category.id}
              style={({ pressed }) => [
                styles.categoryCard,
                pressed && styles.cardPressed,
              ]}
              onPress={() => handleCategoryPress(category)}
              accessibilityRole="button"
              accessibilityLabel={`Browse ${category.title}`}
            >
              <Image
                source={{ uri: category.image }}
                style={styles.categoryImage}
                resizeMode="cover"
              />

              <Text
                style={styles.categoryTitle}
                numberOfLines={2}
              >
                {category.title}
              </Text>

              <Text
                style={styles.categoryDescription}
                numberOfLines={2}
              >
                {category.description}
              </Text>

              <View
                style={[
                  styles.serviceBadge,
                  {
                    backgroundColor: category.badgeBackground,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.serviceBadgeText,
                    { color: category.badgeColor },
                  ]}
                >
                  {!catalogLoaded
                    ? "Loading services"
                    : catalogLoadFailed
                      ? "Unavailable"
                      : `${categoryCounts[category.id] ?? 0} ${(categoryCounts[category.id] ?? 0) === 1 ? "Service" : "Services"}`}
                </Text>

                <Feather
                  name="chevron-right"
                  size={17}
                  color={category.badgeColor}
                />
              </View>
            </Pressable>
          ))}
        </View>

        <Text style={styles.footerText}>
          Trusted services for your home, powered by FieldOps Commander.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: "#FFFFFF",
  },

  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC",
  },

  content: {
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 28,
  },

  header: {
    minHeight: 62,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 14,
  },

  logo: {
    width: 116,
    height: 46,
  },

  headerActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    flexShrink: 1,
  },

  locationButton: {
    maxWidth: 164,
    minHeight: 40,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingHorizontal: 9,
    borderRadius: 24,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E4EAF0",
    elevation: 2,
    shadowColor: "#102A43",
    shadowOpacity: 0.05,
    shadowRadius: 6,
    shadowOffset: { width: 0, height: 2 },
  },

  locationText: {
    flexShrink: 1,
    fontSize: 11,
    fontWeight: "600",
    color: "#183454",
  },

  notificationButton: {
    width: 34,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },

  hero: {
    minHeight: 226,
    borderRadius: 22,
    overflow: "hidden",
    marginBottom: 26,
    backgroundColor: "#DFF3EA",
  },

  heroImage: {
    borderRadius: 22,
  },

  heroOverlay: {
    flex: 1,
    minHeight: 226,
    justifyContent: "center",
    padding: 19,
    backgroundColor: "rgba(222, 245, 234, 0.60)",
  },

  heroTitle: {
    maxWidth: "88%",
    color: "#10243F",
    fontSize: 27,
    lineHeight: 32,
    fontWeight: "800",
    letterSpacing: -0.6,
  },

  heroSubtitle: {
    maxWidth: "88%",
    marginTop: 9,
    color: "#40596A",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "500",
  },

  searchBar: {
    minHeight: 53,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginTop: 19,
    paddingLeft: 13,
    paddingRight: 5,
    borderRadius: 30,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#EDF2F5",
    elevation: 4,
    shadowColor: "#173C35",
    shadowOpacity: 0.10,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 3 },
  },

  searchInput: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 10,
    color: "#183454",
    fontSize: 12,
  },

  searchButton: {
    minHeight: 43,
    minWidth: 76,
    paddingHorizontal: 13,
    borderRadius: 25,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#07825D",
  },

  searchButtonText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },

  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 15,
    gap: 6,
  },

  sectionTitleGroup: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
  },

  categoryIconBox: {
    width: 35,
    height: 35,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#E7F8F0",
  },

  sectionTitle: {
    flexShrink: 1,
    color: "#10243F",
    fontSize: 17,
    fontWeight: "800",
    letterSpacing: -0.3,
  },

  viewAllButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 1,
    paddingVertical: 7,
  },

  viewAllText: {
    color: "#07825D",
    fontSize: 12,
    fontWeight: "700",
  },

  categoryGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: 13,
  },

  categoryCard: {
    width: "48.5%",
    minHeight: 238,
    padding: 9,
    borderRadius: 18,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#EDF1F5",
    elevation: 2,
    shadowColor: "#10243F",
    shadowOpacity: 0.055,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 3 },
  },

  cardPressed: {
    opacity: 0.88,
    transform: [{ scale: 0.985 }],
  },

  categoryImage: {
    width: "100%",
    height: 100,
    borderRadius: 12,
    backgroundColor: "#F0F5F3",
  },

  categoryTitle: {
    minHeight: 40,
    marginTop: 10,
    color: "#10243F",
    fontSize: 15,
    lineHeight: 19,
    fontWeight: "800",
  },

  categoryDescription: {
    minHeight: 37,
    marginTop: 2,
    color: "#687991",
    fontSize: 11,
    lineHeight: 16,
  },

  serviceBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    marginTop: 9,
    paddingLeft: 10,
    paddingRight: 6,
    paddingVertical: 6,
    borderRadius: 20,
  },

  serviceBadgeText: {
    fontSize: 11,
    fontWeight: "800",
  },

  footerText: {
    marginTop: 24,
    color: "#8290A2",
    textAlign: "center",
    fontSize: 11,
    lineHeight: 17,
  },

  pressed: {
    opacity: 0.85,
  },
});
