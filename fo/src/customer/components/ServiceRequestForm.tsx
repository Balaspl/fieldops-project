import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, BackHandler, Platform, Text, View, Pressable, ActivityIndicator, ScrollView, Image } from "react-native";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import * as Location from "expo-location";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../api/customer";
import { getApiErrorMessage } from "../api/client";
import { AppButton, Card, ChoiceChips, Field, Header, LoadingView, Screen, sharedStyles } from "./ui";
import type { CustomerProfile, LocationSearchResult, ServiceCatalogItem, ServiceRequest } from "../types/api";
import { colors } from "../theme";
import { formatDate } from "../utils/format";
import { consumePickedServiceLocation } from "../utils/locationSelection";
import { SERVICE_CATALOGUE_TAXONOMY, type TaxonomyServiceType } from "../data/serviceCatalogueTaxonomy";
import { getCategoryCardImage, getIssueCardImage } from "../data/categoryImages";

const priorities = ["LOW", "MEDIUM", "HIGH", "CRITICAL", "URGENT"] as const;
const SERVICE_ASSETS_URL = "https://raw.githubusercontent.com/ryeswanthkumar/fieldops-project/feature/current-work/frontend/public";

function mobileServiceImage(image: string): string {
  return image.startsWith("/") ? `${SERVICE_ASSETS_URL}${image}` : image;
}

function mobileCategoryImage(categoryId: string, serviceTypeId: string): string {
  return mobileServiceImage(getCategoryCardImage(categoryId, serviceTypeId));
}

function localDateKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(date: Date, days: number): Date {
  const result = new Date(date);
  result.setDate(result.getDate() + days);
  return result;
}

function formatBookingDate(dateKey: string): string {
  const date = new Date(`${dateKey}T12:00:00`);
  return date.toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "short",
  });
}

function isPastTimeSlot(dateKey: string, timeKey: string): boolean {
  if (!dateKey || dateKey !== localDateKey(new Date()) || !timeKey) return false;
  const [hours, minutes] = timeKey.split(":").map(Number);
  const slot = new Date();
  slot.setHours(hours, minutes, 0, 0);
  return slot.getTime() <= Date.now();
}

function matchesHomeCategory(
  item: ServiceCatalogItem,
  homeCategory: string,
): boolean {
  const serviceText = [
    item.service_type,
    item.category,
    item.issue,
  ]
    .map((value) => String(value ?? "").trim().toLowerCase())
    .join(" ");

  const category = homeCategory.trim().toLowerCase();

  if (!category) return true;

  const includesAny = (...keywords: string[]) =>
    keywords.some((keyword) => serviceText.includes(keyword));

  if (category.includes("electr")) {
    return includesAny(
      "electr",
      "wiring",
      "switchboard",
      "mcb",
      "lighting",
    );
  }

  if (category.includes("plumb")) {
    return includesAny(
      "plumb",
      "leak",
      "tap",
      "drain",
      "water pump",
      "faucet",
      "pipe",
      "toilet",
    );
  }

  if (category.includes("appliance")) {
    return (
      includesAny(
        "appliance",
        "hvac",
        "air condition",
        "refrigerator",
        "fridge",
        "washing machine",
        "washer",
        "dishwasher",
        "microwave",
        "oven",
        "dryer",
        "cooler",
      ) || /\bac\b/.test(serviceText)
    );
  }

  if (category.includes("security") || category.includes("smart")) {
    return includesAny(
      "security",
      "smart",
      "cctv",
      "wifi",
      "video doorbell",
      "doorbell",
      "camera",
      "alarm",
    );
  }

  if (category.includes("carpent") || category.includes("wood")) {
    return includesAny(
      "carpent",
      "woodwork",
      "furniture",
      "modular kitchen",
      "cabinet",
      "wooden door",
    );
  }

  if (category.includes("clean") || category.includes("maintenance")) {
    return includesAny(
      "clean",
      "paint",
      "pest control",
      "waterproof",
      "maintenance",
      "housekeeping",
    );
  }

  return serviceText.includes(category);
}

function matchesTaxonomyType(item: ServiceCatalogItem, type: TaxonomyServiceType): boolean {
  const normalize = (value?: string) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const itemType = normalize(item.service_type);
  const typeName = normalize(type.name);
  const typeId = normalize(type.id);
  if (itemType === typeName || itemType === typeId || itemType.includes(typeId) || typeName.includes(itemType)) return true;
  const itemCategory = normalize(item.category);
  return type.categories.some((category) => {
    const categoryName = normalize(category.name);
    const categoryId = normalize(category.id);
    return itemCategory === categoryName || itemCategory === categoryId || itemCategory.includes(categoryName) || categoryName.includes(itemCategory);
  });
}

function findCatalogIssue(items: ServiceCatalogItem[], type: TaxonomyServiceType, category: string, issue: string): ServiceCatalogItem | undefined {
  const normalize = (value?: string) => String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const issueName = normalize(issue);
  const cleaningCategoryAliases: Record<string, string> = {
    sofacarpetmattressandcurtain: "sofacarpetmattresscurtaincleaning",
    watertankandsumpcleaning: "watertanksumpcleaning",
    kitchencleaning: "kitchendeepcleaning",
    bathroomcleaning: "bathroomdeepcleaning",
    officeandcommercialcleaning: "officecommercialcleaning",
    specialisedcleaning: "specialisedcleaningservices",
  };
  const requestedCategory = normalize(category);
  return items.find((item) => {
    if (item.is_active === false) return false;
    const itemCategory = normalize(item.category);
    const categoryMatches = !itemCategory || itemCategory === requestedCategory || cleaningCategoryAliases[itemCategory] === requestedCategory || itemCategory.includes(requestedCategory) || requestedCategory.includes(itemCategory);
    const itemIssue = normalize(item.issue);
    const issueMatches = itemIssue === issueName || itemIssue.includes(issueName) || issueName.includes(itemIssue);
    return categoryMatches && issueMatches && matchesTaxonomyType(item, type);
  });
}

export default function ServiceRequestForm({ requestId }: { requestId?: number }) {
  const editing = typeof requestId === "number";
  const [catalog, setCatalog] = useState<ServiceCatalogItem[]>([]);
  const [request, setRequest] = useState<ServiceRequest | null>(null);
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [locationBusy, setLocationBusy] = useState(false);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [serviceType, setServiceType] = useState("");
  const [category, setCategory] = useState("");
  const [issue, setIssue] = useState("");
  const [priority, setPriority] = useState<(typeof priorities)[number]>("MEDIUM");
  const [todayKey, setTodayKey] = useState(() => localDateKey(new Date()));
  const [preferredDate, setPreferredDate] = useState(() =>
    localDateKey(addDays(new Date(), 1)),
  );
  const [preferredTime, setPreferredTime] = useState("");
  const [location, setLocation] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const [showLocationSuggestions, setShowLocationSuggestions] = useState(false);
  const [locationResults, setLocationResults] = useState<LocationSearchResult[]>([]);
  const [locationSearchBusy, setLocationSearchBusy] = useState(false);
  const [locationSearchError, setLocationSearchError] = useState("");
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [taxonomyBrowseLevel, setTaxonomyBrowseLevel] = useState<"categories" | "issues">("categories");
  const { serviceType: serviceTypeParam } =
    useLocalSearchParams<{
      serviceType?: string | string[];
    }>();

  // Keep the booking calendar in sync when the app stays open across midnight.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;

    const scheduleMidnightRefresh = () => {
      const now = new Date();
      const nextMidnight = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate() + 1,
        0,
        0,
        1,
      );

      timer = setTimeout(() => {
        if (cancelled) return;
        setTodayKey(localDateKey(new Date()));
        scheduleMidnightRefresh();
      }, Math.max(1000, nextMidnight.getTime() - now.getTime()));
    };

    scheduleMidnightRefresh();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  // If the previously selected tomorrow becomes today at midnight,
  // move the selection forward and clear the old time slot.
  useEffect(() => {
    if (editing || !preferredDate || preferredDate > todayKey) return;

    const tomorrow = addDays(new Date(`${todayKey}T12:00:00`), 1);
    setPreferredDate(localDateKey(tomorrow));
    setPreferredTime("");
  }, [editing, preferredDate, todayKey]);

  // Receive the confirmed location when the Ola Maps picker returns to this form.
  // Also refresh the calendar date whenever the form regains focus.
  useFocusEffect(
    useCallback(() => {
      setTodayKey(localDateKey(new Date()));
      const selectedLocation = consumePickedServiceLocation();
      if (!selectedLocation) return;

      setLocation(selectedLocation.address);
      setLatitude(selectedLocation.latitude.toFixed(6));
      setLongitude(selectedLocation.longitude.toFixed(6));
      setLocationConfirmed(true);
      setLocationResults([]);
      setLocationSearchError("");
      setShowLocationSuggestions(false);
      setError("");
    }, []),
  );

  useEffect(() => {
    if (editing || !showLocationSuggestions || location.trim().length < 2) {
      setLocationResults([]);
      setLocationSearchBusy(false);
      setLocationSearchError("");
      return;
    }
    let active = true;
    const timer = setTimeout(async () => {
      setLocationSearchBusy(true);
      setLocationSearchError("");
      try {
        const results = await customerApi.searchLocations(location.trim());
        if (active) setLocationResults(results.slice(0, 6));
      } catch {
        if (active) {
          setLocationResults([]);
          setLocationSearchError("Address search is unavailable. Try again or use your current location.");
        }
      } finally {
        if (active) setLocationSearchBusy(false);
      }
    }, 350);
    return () => { active = false; clearTimeout(timer); };
  }, [editing, location, showLocationSuggestions]);

const homeCategoryName = (
  Array.isArray(serviceTypeParam)
    ? serviceTypeParam[0]
    : serviceTypeParam
)?.trim() || "";
const homeTaxonomy = SERVICE_CATALOGUE_TAXONOMY.find((type) => type.id === homeCategoryName || type.name === homeCategoryName) || null;

const visibleCatalog = useMemo(
  () =>
    catalog.filter(
      (item) =>
        item.is_active !== false &&
        (homeTaxonomy ? matchesTaxonomyType(item, homeTaxonomy) : matchesHomeCategory(item, homeCategoryName)),
    ),
  [catalog, homeCategoryName, homeTaxonomy],
);

const availableTaxonomies = useMemo(
  () => SERVICE_CATALOGUE_TAXONOMY.filter((type) =>
    type.categories.some((entry) =>
      entry.issues.some((issueName) => findCatalogIssue(visibleCatalog, type, entry.name, issueName)),
    ),
  ),
  [visibleCatalog],
);
const selectedTaxonomy = homeTaxonomy || availableTaxonomies.find((type) =>
  type.name.toLowerCase().replace(/[^a-z0-9]/g, "") === serviceType.toLowerCase().replace(/[^a-z0-9]/g, "") ||
  type.id.toLowerCase().replace(/[^a-z0-9]/g, "") === serviceType.toLowerCase().replace(/[^a-z0-9]/g, ""),
) || null;

  // Treat the form's internal screens as real navigation history on Android.
  useFocusEffect(
    useCallback(() => {
      if (Platform.OS !== "android") return;
      const subscription = BackHandler.addEventListener("hardwareBackPress", () => {
        if (step === 3) {
          setError("");
          setStep(2);
          return true;
        }
        if (step === 2) {
          setError("");
          setStep(1);
          return true;
        }
        if (selectedTaxonomy && taxonomyBrowseLevel === "issues") {
          setTaxonomyBrowseLevel("categories");
          return true;
        }
        return false;
      });
      return () => subscription.remove();
    }, [selectedTaxonomy, step, taxonomyBrowseLevel]),
  );

  const types = useMemo(() => availableTaxonomies.map((type) => type.name), [availableTaxonomies]);

  const availableDates = useMemo(() => {
    const start = new Date(`${todayKey}T12:00:00`);
    return Array.from({ length: 5 }, (_, offset) => {
      const date = addDays(start, offset);
      return {
        key: localDateKey(date),
        day: date.toLocaleDateString("en-IN", { weekday: "short" }),
        number: date.getDate(),
        month: date.toLocaleDateString("en-IN", { month: "short" }),
        shortLabel:
          offset === 0 ? "Today" : offset === 1 ? "Tomorrow" : date.toLocaleDateString("en-IN", { weekday: "short" }),
      };
    });
  }, [todayKey]);
  const firstAvailableDate = availableDates[1]?.key || localDateKey(addDays(new Date(), 1));
  const lastAvailableDate = availableDates[availableDates.length - 1]?.key || firstAvailableDate;
  const availableTimes = useMemo(
    () =>
      Array.from({ length: 23 }, (_, index) => {
        const totalMinutes = 8 * 60 + index * 30;
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;
        const hourLabel = hours % 12 || 12;
        return {
          key: `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:00`,
          label: `${hourLabel}:${String(minutes).padStart(2, "0")} ${hours >= 12 ? "PM" : "AM"}`,
        };
      }),
    [],
  );

  const categories = useMemo(
    () =>
      selectedTaxonomy && !editing
        ? selectedTaxonomy.categories
            .filter((entry) => entry.issues.some((issueName) => findCatalogIssue(visibleCatalog, selectedTaxonomy, entry.name, issueName)))
            .map((entry) => entry.name)
        : Array.from(
        new Set(
          visibleCatalog
            .filter(
              (item) => item.service_type === serviceType,
            )
            .map((item) => item.category)
            .filter(Boolean),
        ),
      ),
    [visibleCatalog, serviceType, selectedTaxonomy, editing],
  );

  const issues = useMemo(
    () =>
      selectedTaxonomy && !editing
        ? (selectedTaxonomy.categories.find((entry) => entry.name === category)?.issues || []).flatMap((issueName) => {
            const item = findCatalogIssue(visibleCatalog, selectedTaxonomy, category, issueName);
            return item
              ? [{ ...item, service_type: selectedTaxonomy.name, category, issue: issueName }]
              : [];
          })
        : visibleCatalog.filter(
        (item) =>
          item.service_type === serviceType &&
          item.category === category,
      ),
    [visibleCatalog, serviceType, category, selectedTaxonomy, editing],
  );

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true); setError("");
      try {
        const [items, profileResult] = await Promise.all([customerApi.catalog(), customerApi.profile().catch(() => null)]);
        if (!active) return;
        setCatalog(items);
        setProfile(profileResult);
        if (editing && requestId != null) {
          const existing = await customerApi.request(requestId);
          if (!active) return;
          setRequest(existing);
          setTitle(existing.title || "");
          setDescription(existing.description || "");
          setServiceType(existing.service_type || "");
          setPriority((priorities as readonly string[]).includes(existing.priority) ? existing.priority as (typeof priorities)[number] : "MEDIUM");
          setPreferredDate(existing.preferred_visit_date || "");
          setLocation(existing.location || "");
          setContactNumber(existing.contact_number || profileResult?.mobile_number || "");
          const matching = items.find((item) => item.service_type === existing.service_type);
          if (matching) { setCategory(matching.category); setIssue(matching.issue); }
        } else {
          setContactNumber(profileResult?.mobile_number || "");
          setLocation([profileResult?.address, profileResult?.city, profileResult?.state, profileResult?.pincode].filter(Boolean).join(", "));

          const matchingItems = items.filter(
            (item) =>
              item.is_active !== false &&
              matchesHomeCategory(item, homeCategoryName),
          );

          if (matchingItems.length === 0) {
            setServiceType("");
            setCategory("");
            setIssue("");
            setTitle("");
            setDescription("");
            if (homeCategoryName) {
              setError(`No active services are currently available for ${homeCategoryName}.`);
            }
            return;
          }

          const first = matchingItems[0];
          const firstTaxonomy = SERVICE_CATALOGUE_TAXONOMY.find((type) => matchesTaxonomyType(first, type));
          setServiceType(homeTaxonomy?.name || firstTaxonomy?.name || first.service_type);
          setCategory("");
          setIssue("");
          setTitle("");
          setDescription("");
        }
      } catch (e) { setError(getApiErrorMessage(e, "Could not load the service catalog.")); }
      finally { if (active) setLoading(false); }
    }
    void load();
    return () => { active = false; };
  }, [editing, requestId, homeCategoryName]);

  const chooseServiceType = (value: string) => {
    setServiceType(value);
    setTaxonomyBrowseLevel("categories");
    setLocationConfirmed(false);
    setCategory("");
    setIssue("");
    if (!editing) { setTitle(""); setDescription(""); }
  };

  const chooseCategory = (value: string) => {
    setCategory(value);
    const first = selectedTaxonomy
      ? undefined
      : visibleCatalog.find((item) => item.service_type === serviceType && item.category === value);
    setIssue(first?.issue || "");
    if (!editing && first) {
      setTitle(first.issue);
      setDescription(first.description?.trim() || `${first.issue} service request`);
    }
  };

  const chooseIssue = (value: string) => {
    setIssue(value);
    const item = issues.find((entry) => entry.issue === value);
    if (!editing) {
      setTitle(value);
      setDescription(item?.description?.trim() || `${value} service request`);
    }
  };

  const chooseLocation = (result: LocationSearchResult) => {
    setLocation(result.formatted_address);
    setLatitude(result.latitude.toFixed(6));
    setLongitude(result.longitude.toFixed(6));
    setLocationConfirmed(true);
    setLocationResults([]);
    setLocationSearchError("");
    setShowLocationSuggestions(false);
  };

  const captureLocation = async () => {
    setLocationBusy(true);
    setError("");
    setShowLocationSuggestions(false);

    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        throw new Error("Allow location access to fill in your current address.");
      }

      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;

      if (
        !Number.isFinite(lat) ||
        !Number.isFinite(lon) ||
        lat < -90 || lat > 90 || lon < -180 || lon > 180 ||
        (lat === 0 && lon === 0)
      ) {
        throw new Error("Your device did not return a valid current location. Please try again.");
      }

      let address = "";
      try {
        const resolved = await customerApi.reverseLocation(lat, lon);
        address =
          resolved.address ||
          resolved.display_name ||
          resolved.formatted_address ||
          resolved.name ||
          "";
      } catch {
        // Fall back to the device's reverse-geocoding service.
      }

      if (!address) {
        try {
          const results = await Location.reverseGeocodeAsync({
            latitude: lat,
            longitude: lon,
          });
          const result = results[0];
          if (result) {
            const street = [result.streetNumber, result.street]
              .filter(Boolean)
              .join(" ");
            address = [
              street,
              result.district,
              result.city,
              result.region,
              result.postalCode,
              result.country,
            ]
              .filter(Boolean)
              .filter((part, index, all) => all.indexOf(part) === index)
              .join(", ");
          }
        } catch {
          // Report a clear error below if the address cannot be resolved.
        }
      }

      if (!address.trim()) {
        throw new Error(
          "We found your location but could not get its address. Enter the address or choose a suggested address instead.",
        );
      }

      setLatitude(lat.toFixed(6));
      setLongitude(lon.toFixed(6));
      setLocation(address.trim());
      setLocationConfirmed(true);
      setLocationResults([]);
      setLocationSearchError("");
      setShowLocationSuggestions(false);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : getApiErrorMessage(e, "Unable to get your current address."),
      );
    } finally {
      setLocationBusy(false);
    }
  };

  const validateLocationDetails = (): string | null => {
    if (!location.trim()) return "Enter the service address.";
    if (!contactNumber.trim().match(/^\d{10}$/)) return "Enter a 10-digit contact number.";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(preferredDate.trim())) {
      return "Choose a preferred service date.";
    }
    if (!editing && preferredDate <= todayKey) {
      return "Today's booking is closed. Choose tomorrow or a later date.";
    }
    if (!editing && (preferredDate < firstAvailableDate || preferredDate > lastAvailableDate)) {
      return "Choose a service date from tomorrow through the next 3 days.";
    }
    if (!editing && !preferredTime) {
      return "Choose an available service time slot.";
    }
    if (!editing && !availableTimes.some((slot) => slot.key === preferredTime)) {
      return "Choose a service time between 8:00 AM and 7:00 PM.";
    }
    if (!editing && isPastTimeSlot(preferredDate, preferredTime)) {
      return "Choose an available future time slot.";
    }
    if (!editing && !locationConfirmed) {
      return "Choose an address suggestion or use your current location to confirm the service address.";
    }
    if (!editing) {
      const lat = Number(latitude);
      const lon = Number(longitude);
      if (
        !Number.isFinite(lat) || !Number.isFinite(lon) ||
        lat < -90 || lat > 90 || lon < -180 || lon > 180 ||
        (lat === 0 && lon === 0)
      ) {
        return "Confirm the service address by selecting a suggestion or using your current location.";
      }
    }
    return null;
  };

  const validate = (): string | null => {
    if (editing && title.trim().length < 10) return "Title must be at least 10 characters to update a request.";
    if (!editing && title.trim().length > 0 && title.trim().length < 3) return "Request title must be at least 3 characters when supplied.";
    if (description.trim().length < (editing ? 25 : 10)) return editing ? "Description must be at least 25 characters to update a request." : "Description must be at least 10 characters.";
    if (!serviceType.trim()) return "Choose a service type.";
    if (!editing && (!category || !issue)) return "Choose a service category and issue.";
    return validateLocationDetails();
  };

  const continueToLocation = () => {
    setError("");
    if (!serviceType.trim()) {
      setError("Choose a service type.");
      return;
    }
    if (!category || !issue) {
      setError("Choose a service category and issue.");
      return;
    }
    if (title.trim() && title.trim().length < 3) {
      setError("Request title must be at least 3 characters when supplied.");
      return;
    }
    setStep(2);
  };

  const continueToReview = () => {
    const validation = validateLocationDetails();
    if (validation) {
      setError(validation);
      return;
    }
    setError("");
    setStep(3);
  };

  const submit = async () => {
    const validation = validate();
    if (validation) {
      setError(validation);
      if (validation.includes("service type") || validation.includes("service category") || validation.includes("Request title") || validation.includes("Title must")) {
        setStep(1);
      } else if (validation.includes("Description")) {
        setStep(3);
      } else {
        setStep(2);
      }
      return;
    }
    setSaving(true); setError("");
    try {
      const basePayload: Record<string, unknown> = {
        title: title.trim() || issue.trim(), description: description.trim(), service_type: serviceType,
        priority, preferred_visit_date: preferredDate.trim(), location: location.trim(), contact_number: contactNumber.trim(),
      };
      let result: ServiceRequest;
      if (editing && requestId != null) {
        result = await customerApi.updateRequest(requestId, basePayload);
        Alert.alert("Request updated", "Your service request was updated.", [{ text: "Continue", onPress: () => router.replace({ pathname: "/customer/requests/[requestId]", params: { requestId: String(requestId) } }) }]);
      } else {
        const payload = {
          ...basePayload,
          category,
          issue,
          images: [],
          site_latitude: Number(latitude),
          site_longitude: Number(longitude),
          preferred_service_time: preferredTime,
        };
        result = await customerApi.createRequest(payload);
        const detailId = result.id;
        Alert.alert("Booking request submitted", "Your service request has been sent to FieldOps.", [{ text: "View request", onPress: () => router.replace({ pathname: "/customer/requests/[requestId]", params: { requestId: String(detailId) } }) }]);
      }
    } catch (e) { setError(getApiErrorMessage(e, "Could not save this service request.")); }
    finally { setSaving(false); }
  };

  if (loading) return <Screen><LoadingView message={editing ? "Loading your request…" : "Loading service options…"} /></Screen>;

  const serviceIcon: keyof typeof Ionicons.glyphMap =
    /hvac|air|cool|refrigerat|appliance|ac /.test(serviceType.toLowerCase()) ? "snow-outline" :
    /electr|wiring|power/.test(serviceType.toLowerCase()) ? "flash-outline" :
    /plumb|water|pipe/.test(serviceType.toLowerCase()) ? "water-outline" :
    /security|smart|camera/.test(serviceType.toLowerCase()) ? "shield-checkmark-outline" :
    "construct-outline";

  const addressSuggestions = !editing && showLocationSuggestions && location.trim().length >= 2 ? (
    <View style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 14, overflow: "hidden", backgroundColor: "#FFFFFF", gap: 0 }}>
      {locationSearchBusy ? <View style={{ padding: 12, flexDirection: "row", alignItems: "center", gap: 8 }}><ActivityIndicator color={colors.brand} /><Text style={{ color: colors.muted, fontSize: 12 }}>Searching verified address results…</Text></View> : null}
      {!locationSearchBusy && locationResults.map((result, index) => <Pressable key={result.place_id || `${result.latitude}-${result.longitude}-${index}`} onPress={() => chooseLocation(result)} style={{ padding: 12, borderBottomWidth: index === locationResults.length - 1 ? 0 : 1, borderBottomColor: colors.border, flexDirection: "row", alignItems: "flex-start", gap: 10 }}><Ionicons name="location-outline" color={colors.brandMid} size={19} /><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.text, fontSize: 13, fontWeight: "800" }}>{result.name || result.formatted_address}</Text>{result.name && result.formatted_address !== result.name ? <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 17 }}>{result.formatted_address}</Text> : null}<Text style={{ color: colors.muted, fontSize: 10 }}>Tap to select this service address</Text></View></Pressable>)}
      {!locationSearchBusy && locationResults.length === 0 && !locationSearchError ? <Text style={{ padding: 12, fontSize: 12, lineHeight: 18, color: colors.muted }}>No address matches yet. Try adding a locality, street or landmark.</Text> : null}
      {locationSearchError ? <Text style={{ padding: 12, fontSize: 12, lineHeight: 18, color: colors.warning }}>{locationSearchError}</Text> : null}
      <Pressable onPress={() => setShowLocationSuggestions(false)} style={{ padding: 10, alignItems: "center", borderTopWidth: 1, borderTopColor: colors.border }}><Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "800" }}>Close suggestions</Text></Pressable>
    </View>
  ) : null;

  const locationActions = (
    <View style={{ gap: 9 }}>
      <AppButton
        title={locationBusy ? "Getting current address…" : "Use current location"}
        icon="locate-outline"
        onPress={() => void captureLocation()}
        loading={locationBusy}
        kind="secondary"
      />
      <AppButton
        title="Change location"
        icon="map-outline"
        kind="secondary"
        onPress={() => {
          setError("");
          setLocationSearchError("");
          setShowLocationSuggestions(false);
          router.push({
            pathname: "/customer/location-picker",
            params: {
              address: location,
              latitude,
              longitude,
            },
          });
        }}
      />
      {locationConfirmed ? (
        <View style={{ flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 2 }}>
          <Ionicons name="checkmark-circle" size={17} color={colors.success} />
          <Text style={{ color: colors.success, fontSize: 12, fontWeight: "800", flex: 1 }}>
            Service address selected and verified
          </Text>
        </View>
      ) : (
        <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>
          Select an address suggestion above, or use your current location to fill in the address automatically.
        </Text>
      )}
    </View>
  );

  const dateSelector = (
    <View style={{ gap: 10 }}>
      <View style={{ gap: 3 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Text style={{ color: colors.text, fontSize: 13, fontWeight: "800" }}>Choose a service date</Text>
          <Text style={{ color: colors.danger, fontSize: 13, fontWeight: "900" }}>*</Text>
        </View>
        <Text style={{ color: colors.muted, fontSize: 11 }}>Today is closed · Book tomorrow or a later date</Text>
      </View>
      <View style={{ flexDirection: "row", flexWrap: "nowrap", columnGap: 8, rowGap: 8, paddingVertical: 2 }}>
        {availableDates.map((date) => {
          const selected = preferredDate === date.key;
          const closed = date.key === todayKey;
          return (
            <Pressable
              key={date.key}
              accessibilityRole="radio"
              accessibilityLabel={`${date.shortLabel}, ${date.number} ${date.month}${closed ? ", booking closed" : ""}`}
              accessibilityState={{ checked: selected, disabled: closed }}
              disabled={closed}
              onPress={() => {
                setPreferredDate(date.key);
                setPreferredTime("");
                setError("");
              }}
              style={{ flex: 1, minWidth: 0, minHeight: 78, alignItems: "center", justifyContent: "center", gap: 3, borderRadius: 12, borderWidth: 1, borderColor: selected ? colors.brand : colors.border, backgroundColor: selected ? colors.brand : closed ? "#EEF1EF" : "#FFFFFF", paddingHorizontal: 3, paddingVertical: 7, opacity: closed ? 0.72 : 1 }}
            >
              <Text style={{ color: selected ? "#FFFFFF" : colors.muted, fontSize: 9, fontWeight: "800" }}>{date.shortLabel}</Text>
              <Text style={{ color: selected ? "#FFFFFF" : closed ? colors.muted : colors.text, fontSize: 20, lineHeight: 23, fontWeight: "900" }}>{date.number}</Text>
              <Text style={{ color: selected ? "#FFFFFF" : colors.muted, fontSize: 9, fontWeight: "700" }}>{closed ? "Closed" : date.month}</Text>
            </Pressable>
          );
        })}
      </View>
      {!editing ? (
        <View style={{ gap: 8, paddingTop: 3 }}>
          <View style={{ gap: 3 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: "800" }}>Choose a time slot</Text>
              <Text style={{ color: colors.danger, fontSize: 13, fontWeight: "900" }}>*</Text>
            </View>
            <Text style={{ color: colors.muted, fontSize: 11 }}>8:00 AM – 7:00 PM · Every 30 minutes</Text>
          </View>
          {preferredDate && preferredDate <= todayKey ? (
            <View style={{ padding: 12, borderRadius: 12, backgroundColor: "#F0F2F1" }}>
              <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18, fontWeight: "700" }}>
                Today's time slots are closed. Please choose tomorrow or a later date.
              </Text>
            </View>
          ) : preferredDate ? (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
              {availableTimes.map((slot) => {
                const selected = preferredTime === slot.key;
                const disabled = isPastTimeSlot(preferredDate, slot.key);
                return (
                  <Pressable
                    key={slot.key}
                    accessibilityRole="radio"
                    accessibilityLabel={slot.label}
                    accessibilityState={{ checked: selected, disabled }}
                    disabled={disabled}
                    onPress={() => {
                      setPreferredTime(slot.key);
                      setError("");
                    }}
                    style={{ width: "31%", minHeight: 40, alignItems: "center", justifyContent: "center", paddingHorizontal: 5, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: selected ? colors.brand : colors.border, backgroundColor: selected ? colors.brand : disabled ? "#F0F2F1" : "#FFFFFF", opacity: disabled ? 0.45 : 1 }}
                  >
                    <Text style={{ color: selected ? "#FFFFFF" : disabled ? colors.muted : colors.text, fontSize: 12, fontWeight: selected ? "900" : "700" }}>{slot.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          ) : (
            <Text style={{ color: colors.muted, fontSize: 12 }}>Select a date above to see its available time slots.</Text>
          )}
        </View>
      ) : null}
    </View>
  );

  if (editing) return <Screen>
    <Header title="Edit request" subtitle="Update the details for your unassigned request" />
    {error ? <Card style={{ backgroundColor: "#FDECEA", borderColor: "#F1C4C0" }}><Text style={{ color: colors.danger, fontSize: 13, lineHeight: 20 }}>{error}</Text></Card> : null}
    {request ? <Card style={{ backgroundColor: colors.accentLight, borderColor: "#D5E9DB" }}><Text style={{ color: colors.brand, fontWeight: "800" }}>{request.request_number}</Text><Text style={{ color: colors.muted, fontSize: 12 }}>Created {formatDate(request.created_at)} · editing is available only while the request is unassigned.</Text></Card> : null}
    <Card>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>Service details</Text>
      <View style={{ gap: 8 }}><Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>Service type</Text><View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>{types.map((value) => <Pressable key={value} onPress={() => chooseServiceType(value)} style={{ backgroundColor: serviceType === value ? colors.brand : "#F5F7F6", borderWidth: 1, borderColor: serviceType === value ? colors.brand : colors.border, borderRadius: 99, paddingHorizontal: 12, paddingVertical: 10 }}><Text style={{ color: serviceType === value ? "white" : colors.text, fontWeight: "700", fontSize: 12 }}>{value}</Text></Pressable>)}</View></View>
      <Field label="Request title" value={title} onChangeText={setTitle} placeholder="Describe the service needed" maxLength={200} />
      <Field label="Description" value={description} onChangeText={setDescription} placeholder="Add the symptoms, affected area and helpful details" multiline maxLength={2500} />
      <ChoiceChips label="Priority" value={priority} options={priorities} onChange={setPriority} />
      {dateSelector}
    </Card>
    <Card>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>Service address</Text>
      <Field label="Service address" value={location} editable={false} multiline />
      <Field label="Contact phone" value={contactNumber} onChangeText={(value) => setContactNumber(value.replace(/\D/g, "").slice(0, 10))} placeholder="10-digit phone number" keyboardType="phone-pad" maxLength={10} />
      <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>The address on an existing request cannot be changed here. Contact support if the service location needs to be updated.</Text>
    </Card>
    <AppButton title="Save changes" icon="checkmark-circle-outline" onPress={() => void submit()} loading={saving} />
    <AppButton title="Cancel" kind="ghost" onPress={() => router.back()} />
  </Screen>;

  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0, gap: 0 }}>
    <View style={{ flex: 1 }}>
      <ScrollView contentContainerStyle={{ paddingHorizontal: 18, paddingTop: 12, paddingBottom: 18, gap: 17 }} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Pressable accessibilityRole="button" accessibilityLabel={step === 1 ? "Go back" : "Previous step"} onPress={() => step === 1 ? selectedTaxonomy && taxonomyBrowseLevel === "issues" ? setTaxonomyBrowseLevel("categories") : router.back() : setStep((step - 1) as 1 | 2 | 3)} style={{ width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: colors.border }}><Ionicons name="arrow-back" size={21} color={colors.brand} /></Pressable>
          <View style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" }}><Ionicons name="construct" size={25} color={colors.brand} /></View>
          <View style={{ gap: 1, flex: 1 }}><Text style={{ color: colors.brand, fontSize: 20, fontWeight: "900", letterSpacing: -0.5 }}>FieldOps</Text><Text style={{ color: colors.muted, fontSize: 11, fontWeight: "600" }}>Customer</Text></View>
        </View>

        <View style={{ gap: 5 }}>
          <Text style={{ color: colors.text, fontSize: 28, lineHeight: 33, fontWeight: "900", letterSpacing: -0.7 }}>{step === 1 ? "Book a service" : step === 2 ? "Service location" : "Review request"}</Text>
          <Text style={{ color: colors.muted, fontSize: 14, lineHeight: 20 }}>{step === 1 ? "Tell us what needs fixing" : step === 2 ? "Where should we come?" : "Check everything before you book"}</Text>
        </View>

        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          {([ { id: 1, label: "Service" }, { id: 2, label: "Location" }, { id: 3, label: "Review" } ] as const).map((entry, index) => (
            <View key={entry.id} style={{ flexDirection: "row", alignItems: "center", flex: index === 2 ? 0 : 1, gap: 6 }}>
              <View style={{ width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", backgroundColor: entry.id < step ? colors.brandMid : entry.id === step ? colors.brand : "#FFFFFF", borderWidth: entry.id <= step ? 0 : 1.5, borderColor: colors.border }}>
                {entry.id < step ? <Ionicons name="checkmark" size={17} color="#FFFFFF" /> : <Text style={{ color: entry.id === step ? "#FFFFFF" : colors.muted, fontSize: 13, fontWeight: "800" }}>{entry.id}</Text>}
              </View>
              <Text style={{ color: entry.id === step || entry.id < step ? colors.brand : colors.muted, fontSize: 12, fontWeight: entry.id === step ? "800" : "600" }}>{entry.label}</Text>
              {index < 2 ? <View style={{ flex: 1, minWidth: 10, height: 1.5, backgroundColor: entry.id < step ? colors.brandMid : colors.border, marginHorizontal: 2 }} /> : null}
            </View>
          ))}
        </View>

        {error ? <Card style={{ backgroundColor: colors.dangerSoft, borderColor: "#F1C4C0", padding: 12 }}><View style={{ flexDirection: "row", alignItems: "flex-start", gap: 8 }}><Ionicons name="alert-circle-outline" size={20} color={colors.danger} /><Text style={{ color: colors.danger, fontSize: 13, lineHeight: 19, flex: 1 }}>{error}</Text></View></Card> : null}

        {step === 1 ? <>
          <Card style={{ gap: 16 }}>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: "900" }}>Choose a service</Text>
            {catalog.length === 0 || visibleCatalog.length === 0 ? <Text style={{ color: colors.warning, fontSize: 13, lineHeight: 19 }}>No active services are available for this category right now. Please go back and choose another service category.</Text> : null}

            {types.length > 1 ? <View style={{ gap: 8 }}>
                  <Text style={{ color: colors.text, fontSize: 13, fontWeight: "800" }}>Available service types</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>{types.map((value) => <Pressable key={value} onPress={() => chooseServiceType(value)} style={{ backgroundColor: serviceType === value ? colors.brand : "#FFFFFF", borderWidth: 1, borderColor: serviceType === value ? colors.brand : colors.border, borderRadius: 99, paddingHorizontal: 13, paddingVertical: 9 }}><Text style={{ color: serviceType === value ? "#FFFFFF" : colors.text, fontWeight: "700", fontSize: 12 }}>{value}</Text></Pressable>)}</View>
            </View> : null}

            {serviceType ? <View style={{ flexDirection: "row", alignItems: "center", gap: 12, padding: 13, borderRadius: 17, backgroundColor: colors.brandSoft }}>
              <View style={{ width: 58, height: 58, borderRadius: 15, backgroundColor: "#D2ECE2", alignItems: "center", justifyContent: "center" }}><Ionicons name={serviceIcon} size={31} color={colors.brand} /></View>
              <View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.text, fontSize: 15, fontWeight: "900" }}>{serviceType}</Text><Text style={{ color: colors.muted, fontSize: 12, lineHeight: 17 }}>Choose a category and tell us what needs fixing.</Text></View>
              <Ionicons name="chevron-forward" size={20} color={colors.brand} />
            </View> : null}

            {!editing ? <>
              <View style={{ gap: 9 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  {selectedTaxonomy && taxonomyBrowseLevel === "issues" ? <Pressable accessibilityRole="button" accessibilityLabel="Back to categories" onPress={() => setTaxonomyBrowseLevel("categories")}><Ionicons name="arrow-back-circle" size={25} color={colors.brand} /></Pressable> : null}
                  <Text style={{ color: colors.text, fontSize: 15, fontWeight: "900", flex: 1 }}>{selectedTaxonomy && taxonomyBrowseLevel === "issues" ? category : "Available categories"}</Text>
                </View>
                {selectedTaxonomy && taxonomyBrowseLevel === "categories" ? <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10 }}>{categories.map((categoryName) => {
                  const entry = selectedTaxonomy.categories.find((item) => item.name === categoryName)!;
                  const activeCount = entry.issues.filter((issueName) => findCatalogIssue(visibleCatalog, selectedTaxonomy, entry.name, issueName)).length;
                  const selected = category === entry.name;
                  return <Pressable key={entry.id} onPress={() => { chooseCategory(entry.name); setTaxonomyBrowseLevel("issues"); }} style={{ width: "48.5%", borderRadius: 14, overflow: "hidden", backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: selected ? colors.brand : colors.border }}><Image source={{ uri: mobileCategoryImage(entry.id, selectedTaxonomy.id) }} style={{ width: "100%", height: 84, backgroundColor: "#F1F5F9" }} resizeMode="contain" /><View style={{ padding: 9, gap: 4 }}><Text style={{ color: colors.text, fontSize: 12, lineHeight: 16, fontWeight: "800" }}>{entry.name}</Text><Text style={{ color: colors.muted, fontSize: 10 }}>{activeCount} available services</Text></View></Pressable>;
                })}</View> : !selectedTaxonomy ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>{categories.map((value) => <Pressable key={value} onPress={() => chooseCategory(value)} style={{ backgroundColor: category === value ? colors.brand : "#FFFFFF", borderWidth: 1, borderColor: category === value ? colors.brand : colors.border, borderRadius: 99, paddingHorizontal: 13, paddingVertical: 10 }}><Text style={{ color: category === value ? "#FFFFFF" : colors.muted, fontWeight: "700", fontSize: 12 }}>{value}</Text></Pressable>)}</View> : null}
              </View>
              {selectedTaxonomy?.id === "painting" && taxonomyBrowseLevel === "issues" ? <Text style={{ color: colors.text, fontSize: 15, fontWeight: "900" }}>{({
                "Interior Painting": "Select Interior Painting Service",
                "Exterior Painting": "Select Exterior Painting Service",
                "Wood & Metal Painting": "Select Painting Service",
                "Wall Repair & Crack Filling": "Select Wall Problem",
                "Waterproofing Services": "Select Waterproofing Service",
                "Special Finishes": "Select Special Finish",
              } as Record<string, string>)[category] || "Select Painting Service"}</Text> : null}
              {(!selectedTaxonomy || taxonomyBrowseLevel === "issues") ? <View style={{ gap: 9 }}>
                {!selectedTaxonomy ? <Text style={{ color: colors.text, fontSize: 15, fontWeight: "900" }}>Choose an issue</Text> : null}
                <View style={{ flexDirection: "row", flexWrap: "wrap", justifyContent: "space-between", rowGap: 10 }}>{issues.map((item, index) => {
                  const active = item.is_active !== false;
                  const selected = issue === item.issue;
                  const taxonomyCategory = selectedTaxonomy?.categories.find((entry) => entry.name === category);
                  return <Pressable key={`${item.service_type}-${item.category}-${item.issue}`} accessibilityRole="radio" accessibilityState={{ checked: selected, disabled: !active }} onPress={() => { if (!active) { Alert.alert("Service unavailable", `${item.issue} is not currently offered. Please choose another issue.`); return; } chooseIssue(item.issue); if (homeTaxonomy) { setError(""); setStep(2); } }} style={{ width: "48.5%", borderRadius: 15, borderWidth: 1.2, borderColor: selected ? colors.brandMid : colors.border, backgroundColor: selected ? colors.brandSoft : "#FFFFFF", overflow: "hidden", opacity: active ? 1 : 0.52 }}>
                    {selectedTaxonomy && taxonomyCategory ? <Image source={{ uri: mobileServiceImage(getIssueCardImage(item.issue, taxonomyCategory.id, selectedTaxonomy.id, index)) }} style={{ width: "100%", height: 96, backgroundColor: "#F1F5F9" }} resizeMode="contain" /> : null}
                    <View style={{ gap: 5, padding: 10 }}><View style={{ flexDirection: "row", alignItems: "flex-start", gap: 5 }}><Text style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: "800", lineHeight: 16 }}>{item.issue}</Text><Ionicons name={selected ? "checkmark-circle" : active ? "chevron-forward" : "lock-closed"} size={16} color={selected ? colors.brandMid : colors.muted} /></View>{item.description ? <Text style={{ color: colors.muted, fontSize: 11, lineHeight: 15 }} numberOfLines={3}>{item.description}</Text> : null}<Text style={{ color: active ? colors.brandMid : colors.muted, fontSize: 10, fontWeight: "700" }}>{active ? "Available" : "Currently unavailable"}</Text></View>
                  </Pressable>;
                })}</View>
              </View> : null}
            </> : null}

            <Field label="Request title (optional)" value={title} onChangeText={setTitle} placeholder="e.g. AC not cooling" maxLength={200} />
          </Card>
        </> : null}

        {step === 2 ? <>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 11, padding: 12, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: "#FFFFFF" }}>
            <View style={{ width: 48, height: 48, borderRadius: 13, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" }}><Ionicons name={serviceIcon} size={25} color={colors.brand} /></View>
            <View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.text, fontSize: 13, fontWeight: "900" }} numberOfLines={2}>{serviceType} · {issue}</Text><Text style={{ color: colors.muted, fontSize: 12 }}>{category}</Text></View>
            <Pressable onPress={() => { setError(""); setStep(1); }}><Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "900", textDecorationLine: "underline" }}>Edit</Text></Pressable>
          </View>

          <Card style={{ gap: 15 }}>
            <Text style={{ color: colors.text, fontSize: 17, fontWeight: "900" }}>Service address</Text>
            <Field label="Search / enter service address" value={location} editable={!editing} onFocus={() => { if (!editing) setShowLocationSuggestions(true); }} onChangeText={(value) => { setLocation(value); setLatitude(""); setLongitude(""); setLocationConfirmed(false); setShowLocationSuggestions(true); }} placeholder="Street, area or landmark" multiline />
            {addressSuggestions}
            {locationActions}
            <Field label="Contact phone" value={contactNumber} onChangeText={(value) => setContactNumber(value.replace(/\D/g, "").slice(0, 10))} placeholder="10-digit phone number" keyboardType="phone-pad" maxLength={10} />
            {dateSelector}
            <View style={{ gap: 8 }}>
              <Text style={{ color: colors.text, fontSize: 13, fontWeight: "800" }}>Priority</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 7 }}>
                {priorities.map((value) => {
                  const selected = priority === value;
                  const label = value.charAt(0) + value.slice(1).toLowerCase();
                  return <Pressable key={value} onPress={() => setPriority(value)} style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 999, borderWidth: 1, borderColor: selected ? colors.brand : colors.border, backgroundColor: selected ? colors.brand : "#FFFFFF" }}><Text style={{ color: selected ? "#FFFFFF" : colors.muted, fontSize: 12, fontWeight: "800" }}>{label}</Text></Pressable>;
                })}
              </View>
            </View>
          </Card>

        </> : null}

        {step === 3 ? <>
          <Card style={{ gap: 13 }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}><Text style={{ color: colors.text, fontSize: 17, fontWeight: "900" }}>Service details</Text><Pressable onPress={() => setStep(1)}><Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "900", textDecorationLine: "underline" }}>Edit</Text></Pressable></View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}><View style={{ width: 48, height: 48, borderRadius: 14, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" }}><Ionicons name={serviceIcon} size={25} color={colors.brand} /></View><View style={{ flex: 1, gap: 3 }}><Text style={{ color: colors.text, fontSize: 14, fontWeight: "900" }}>{serviceType}</Text><Text style={{ color: colors.muted, fontSize: 12 }}>{category}</Text><Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>{issue}</Text></View></View>
            <View style={{ height: 1, backgroundColor: colors.border }} />
            <View style={{ gap: 5 }}><Text style={{ color: colors.muted, fontSize: 12, fontWeight: "700" }}>Request title</Text><Text style={{ color: colors.text, fontSize: 14, fontWeight: "800" }}>{title.trim() || issue}</Text></View>
            <Field label="Description" value={description} onChangeText={setDescription} placeholder="Add symptoms, affected area and helpful details" multiline maxLength={2500} />
          </Card>

          <Card style={{ gap: 13 }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 }}><Text style={{ color: colors.text, fontSize: 17, fontWeight: "900" }}>Service location</Text><Pressable onPress={() => setStep(2)}><Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "900", textDecorationLine: "underline" }}>Edit</Text></Pressable></View>
            <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 10 }}><Ionicons name="location-outline" size={21} color={colors.brandMid} /><Text style={{ flex: 1, color: colors.text, fontSize: 13, lineHeight: 19 }}>{location}</Text></View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}><Ionicons name="call-outline" size={19} color={colors.brandMid} /><Text style={{ color: colors.text, fontSize: 13 }}>{contactNumber}</Text></View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}><Ionicons name="checkmark-circle" size={18} color={colors.success} /><Text style={{ color: colors.success, fontSize: 12, fontWeight: "800" }}>Service address confirmed</Text></View>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
              <View style={{ flex: 1, gap: 7 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}><Ionicons name="calendar-outline" size={18} color={colors.brandMid} /><Text style={{ color: colors.muted, fontSize: 12 }}>{preferredDate ? formatBookingDate(preferredDate) : "No service date selected"}</Text></View>
                {!editing ? <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}><Ionicons name="time-outline" size={18} color={colors.brandMid} /><Text style={{ color: colors.muted, fontSize: 12 }}>{availableTimes.find((slot) => slot.key === preferredTime)?.label || "No time slot selected"}</Text></View> : null}
              </View>
              <View style={{ paddingHorizontal: 11, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: priority === "MEDIUM" ? colors.brand : colors.border, backgroundColor: priority === "MEDIUM" ? colors.brand : "#FFFFFF" }}><Text style={{ color: priority === "MEDIUM" ? "#FFFFFF" : colors.text, fontSize: 11, fontWeight: "800" }}>{priority.charAt(0) + priority.slice(1).toLowerCase()}</Text></View>
            </View>
          </Card>
        </> : null}
      </ScrollView>

      <View style={{ paddingHorizontal: 18, paddingTop: 10, paddingBottom: 12, gap: 9, backgroundColor: colors.background, borderTopWidth: 1, borderTopColor: colors.border }}>
        {step === 1 && !homeTaxonomy ? <AppButton title="Continue to location" icon="arrow-forward" onPress={continueToLocation} disabled={!serviceType || !category || !issue} /> : null}
        {step === 2 ? <View style={{ flexDirection: "row", gap: 10 }}><AppButton title="Back" icon="arrow-back" kind="secondary" onPress={() => { setError(""); setStep(1); }} style={{ flex: 1 }} /><AppButton title="Review request" icon="arrow-forward" onPress={continueToReview} style={{ flex: 1.35 }} /></View> : null}
        {step === 3 ? <><AppButton title="Submit service request" icon="checkmark-circle-outline" onPress={() => void submit()} loading={saving} /><AppButton title="Back to location" kind="ghost" onPress={() => { setError(""); setStep(2); }} /></> : null}
        <Text style={{ color: colors.muted, fontSize: 11, fontWeight: "600", textAlign: "center" }}>Step {step} of 3</Text>
      </View>
    </View>
  </Screen>;
}
