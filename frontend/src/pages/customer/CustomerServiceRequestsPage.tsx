import { useState, useEffect, useRef } from "react";
import {
  FileText,
  PlusCircle,
  XCircle,
  Edit3,
  AlertCircle,
  CheckCircle,
  X,
  Clock,
  Send,
  MapPin,
} from "lucide-react";

import {
  getServiceRequests,
  createServiceRequest,
  updateServiceRequest,
  cancelServiceRequest,
} from "../../services/customerPortalService";

import api from "../../services/api";
import { OlaMaps } from "olamaps-web-sdk";

const OLA_STYLE =
  "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

const badge = (status: string) => {
  const c: Record<string, string> = {
    UNASSIGNED: "#DD6B20",
    "AWAITING ACCEPTANCE": "#1E40AF",
    ASSIGNED: "#1E40AF",
    "EN ROUTE": "#7C3AED",
    IN_PROGRESS: "#92400E",
    COMPLETED: "#065F46",
    CANCELLED: "#991B1B",
  };

  const displayStatus =
    status === "CREATED"
      ? "UNASSIGNED"
      : status === "ASSIGNED"
      ? "AWAITING ACCEPTANCE"
      : status === "ACCEPTED"
      ? "ASSIGNED"
      : status === "EN_ROUTE"
      ? "EN ROUTE"
      : status === "IN_PROGRESS"
      ? "IN_PROGRESS"
      : status;

  return {
    fontSize: "11px",
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: "20px",
    background: (c[displayStatus] || "#6B7280") + "18",
    color: c[displayStatus] || "#6B7280",
    display: "inline-block",
  };
};

interface CustomerServiceRequestsPageProps {
  createOnly?: boolean;
  onNavigate?: (tab: string) => void;
}

export default function CustomerServiceRequestsPage({
  createOnly = false,
  onNavigate,
}: CustomerServiceRequestsPageProps) {
  const [requests, setRequests] = useState<any[]>([]);
  const [loading, setLoading] = useState(!createOnly);

  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);

  const [form, setForm] = useState({
    title: "",
    description: "",
    service_type: "",
    priority: "select priority",
    preferred_visit_date: "",
    location: "",
    contact_number: "",
  });

  const [siteLatitude, setSiteLatitude] =
    useState<number | null>(null);

  const [siteLongitude, setSiteLongitude] =
    useState<number | null>(null);

  const [isGettingLocation, setIsGettingLocation] =
    useState(false);

  const [locationSearch, setLocationSearch] =
    useState("");

  const [locationResults, setLocationResults] =
    useState<any[]>([]);

  const [isSearchingLocations, setIsSearchingLocations] =
    useState(false);

  const [locationSearchError, setLocationSearchError] =
    useState("");

  const [selectedLocationName, setSelectedLocationName] =
    useState("");

  const [locationConfirmed, setLocationConfirmed] =
    useState(false);

  const [mapVisible, setMapVisible] =
    useState(false);

  const [mapError, setMapError] =
    useState(false);

  const [mapTarget, setMapTarget] =
    useState<{
      latitude: number;
      longitude: number;
    } | null>(null);

  const [isResolvingMapCenter, setIsResolvingMapCenter] =
    useState(false);

  const mapContainerRef =
    useRef<HTMLDivElement | null>(null);

  const olaMapRef =
    useRef<any>(null);

  const programmaticMapMove =
    useRef(false);

  const reverseGeocodeSequence =
    useRef(0);

  const mapRequestId =
    useRef(0);

  const selectedLocationSearch =
    useRef("");

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState("");

  const [loadError, setLoadError] =
    useState("");

  const [success, setSuccess] =
    useState("");

  useEffect(() => {
    const query = locationSearch.trim();

    if (
      query ===
      selectedLocationSearch.current
    ) {
      selectedLocationSearch.current =
        "";
      setLocationResults([]);
      setIsSearchingLocations(false);
      setLocationSearchError("");
      return;
    }

    if (query.length < 2) {
      setLocationResults([]);
      setIsSearchingLocations(false);
      setLocationSearchError("");
      return;
    }

    let active = true;

    const timer = window.setTimeout(
      async () => {
        const requestId =
          ++mapRequestId.current;

        setIsSearchingLocations(true);
        setLocationSearchError("");

        try {
          const apiKey =
            import.meta.env.VITE_OLA_MAPS_API_KEY;

          if (!apiKey) {
            if (
              active &&
              requestId === mapRequestId.current
            ) {
              setLocationResults([]);
              setLocationSearchError(
                "Map search is not configured."
              );
            }
            return;
          }

          const params = new URLSearchParams({
            input: query,
            api_key: apiKey,
          });

          const response = await fetch(
            `https://api.olamaps.io/places/v1/autocomplete?${params.toString()}`
          );

          if (!response.ok) {
            throw new Error(
              `Autocomplete request failed with status ${response.status}`
            );
          }

          const data = await response.json();

          if (
            active &&
            requestId === mapRequestId.current
          ) {
            const results =
              data?.predictions ||
              data?.results ||
              [];

            setLocationResults(
              Array.isArray(results)
                ? results
                : []
            );
          }
        } catch {
          if (
            active &&
            requestId === mapRequestId.current
          ) {
            setLocationResults([]);
            setLocationSearchError(
              "Unable to search locations."
            );
          }
        } finally {
          if (
            active &&
            requestId === mapRequestId.current
          ) {
            setIsSearchingLocations(false);
          }
        }
      },
      350
    );

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [locationSearch]);

  useEffect(() => {
    if (
      !mapVisible ||
      !mapContainerRef.current ||
      mapTarget === null
    ) {
      return;
    }

    let disposed = false;

    const initialiseMap = async () => {
      try {
        const apiKey =
          import.meta.env.VITE_OLA_MAPS_API_KEY;

        if (!apiKey) {
          setMapError(true);
          return;
        }

        const olaMaps = new OlaMaps({
          apiKey,
        });

        if (disposed) {
          return;
        }

        const instance = await olaMaps.init({
          style: OLA_STYLE,
          container: mapContainerRef.current,
          center: [
            mapTarget.longitude,
            mapTarget.latitude,
          ],
          zoom: 16,
        });

        if (disposed) {
          instance?.remove?.();
          return;
        }

        olaMapRef.current =
          instance;

        const addCustomerLocationPoint =
          () => {
            try {
              if (
                !instance.getSource(
                  "customer-location"
                )
              ) {
                instance.addSource(
                  "customer-location",
                  {
                    type: "geojson",
                    data: {
                      type: "Feature",
                      properties: {},
                      geometry: {
                        type: "Point",
                        coordinates: [
                          mapTarget.longitude,
                          mapTarget.latitude,
                        ],
                      },
                    },
                  }
                );
              }

              if (
                !instance.getLayer(
                  "customer-location-point"
                )
              ) {
                instance.addLayer({
                  id:
                    "customer-location-point",
                  type: "circle",
                  source:
                    "customer-location",
                  paint: {
                    "circle-radius": 9,
                    "circle-color":
                      "#DC2626",
                    "circle-stroke-width":
                      3,
                    "circle-stroke-color":
                      "#FFFFFF",
                  },
                });
              }

              setMapError(false);
            } catch {
              setMapError(false);
            }
          };

        if (
          instance.isStyleLoaded?.()
        ) {
          addCustomerLocationPoint();
        } else {
          instance.once(
            "load",
            addCustomerLocationPoint
          );
        }

        instance.on(
          "click",
          async (event: any) => {
            const longitude =
              event?.lngLat?.lng;

            const latitude =
              event?.lngLat?.lat;

            if (
              typeof longitude !== "number" ||
              typeof latitude !== "number"
            ) {
              return;
            }

            setSiteLatitude(latitude);
            setSiteLongitude(longitude);

            setMapTarget({
              latitude,
              longitude,
            });

            setLocationConfirmed(true);

            const coordinatesLabel =
              `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;

            setSelectedLocationName(
              coordinatesLabel
            );

            setForm((current) => ({
              ...current,
              location: coordinatesLabel,
            }));

            const requestId =
              ++reverseGeocodeSequence.current;

            setIsResolvingMapCenter(true);

            try {
              const reverseResponse =
                await api.get(
                  "/organizations/location-reverse",
                  {
                    params: {
                      latitude,
                      longitude,
                    },
                  }
                );

              if (
                requestId ===
                reverseGeocodeSequence.current
              ) {
                const name =
                  reverseResponse?.data
                    ?.display_name ||
                  reverseResponse?.data
                    ?.name ||
                  "";

                if (name) {
                  setSelectedLocationName(
                    name
                  );

                  setForm((current) => ({
                    ...current,
                    location: name,
                  }));
                }
              }
            } catch {
              // Reverse geocoding is optional.
              // The map itself is already loaded, so do not
              // show a map-load error when address lookup fails.
            } finally {
              if (
                requestId ===
                reverseGeocodeSequence.current
              ) {
                setIsResolvingMapCenter(false);
              }
            }
          }
        );

        setMapError(false);
      } catch {
        if (!disposed) {
          setMapError(true);
        }
      }
    };

    void initialiseMap();

    return () => {
      disposed = true;

      try {
        olaMapRef.current?.remove?.();
      } catch {
        // Ignore map cleanup errors.
      }

      olaMapRef.current = null;
    };
  }, [mapVisible, mapTarget]);

  const getCurrentLocation =
    () => {
      if (
        !navigator.geolocation
      ) {
        setMapError(true);
        return;
      }

      setIsGettingLocation(true);
      setMapError(false);

      navigator.geolocation.getCurrentPosition(
        async (position) => {
          const latitude =
            position.coords.latitude;

          const longitude =
            position.coords.longitude;

          setSiteLatitude(latitude);
          setSiteLongitude(longitude);

          setMapTarget({
            latitude,
            longitude,
          });

          setLocationConfirmed(true);
          setMapVisible(true);

          setIsGettingLocation(false);

          const coordinatesLabel =
            `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;

          setSelectedLocationName(
            coordinatesLabel
          );

          selectedLocationSearch.current =
            coordinatesLabel;

          setLocationSearch(
            coordinatesLabel
          );

          setForm((current) => ({
            ...current,
            location: coordinatesLabel,
          }));

          const requestId =
            ++reverseGeocodeSequence.current;

          setIsResolvingMapCenter(true);

          try {
            const response =
              await api.get(
                "/organizations/location-reverse",
                {
                  params: {
                    latitude,
                    longitude,
                  },
                }
              );

            if (
              requestId ===
              reverseGeocodeSequence.current
            ) {
              const name =
                response?.data
                  ?.display_name ||
                response?.data?.name ||
                "";

              if (name) {
                setSelectedLocationName(
                  name
                );

                setForm((current) => ({
                  ...current,
                  location: name,
                }));
              }
            }
          } catch {
            // Reverse geocoding is optional.
            // The map itself is already loaded, so do not
            // show a map-load error when address lookup fails.
          } finally {
            if (
              requestId ===
              reverseGeocodeSequence.current
            ) {
              setIsResolvingMapCenter(false);
            }
          }
        },
        () => {
          setIsGettingLocation(false);
          setMapError(true);
        },
        {
          enableHighAccuracy: true,
          maximumAge: 0,
          timeout: 15000,
        }
      );
    };

  const selectLocation =
    async (result: any) => {
      let latitude =
        Number(
          result?.latitude ??
          result?.geometry?.location?.lat ??
          result?.geometry?.coordinates?.[1]
        );

      let longitude =
        Number(
          result?.longitude ??
          result?.geometry?.location?.lng ??
          result?.geometry?.coordinates?.[0]
        );

      let name =
        result?.description ||
        result?.display_name ||
        result?.name ||
        result?.place_name ||
        result?.formatted_address ||
        locationSearch;

      const placeId =
        result?.place_id;

      const apiKey =
        import.meta.env.VITE_OLA_MAPS_API_KEY;

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude)
      ) {
        if (
          !placeId ||
          !apiKey
        ) {
          setLocationSearchError(
            "Unable to determine the selected location."
          );
          return;
        }

        try {
          const params =
            new URLSearchParams({
              place_id: placeId,
              api_key: apiKey,
            });

          const response =
            await fetch(
              `https://api.olamaps.io/places/v1/details?${params.toString()}`
            );

          if (!response.ok) {
            throw new Error(
              `Place details request failed with status ${response.status}`
            );
          }

          const data =
            await response.json();

          const place =
            data?.result ||
            data;

          latitude =
            Number(
              place?.geometry?.location?.lat ??
              place?.geometry?.coordinates?.[1]
            );

          longitude =
            Number(
              place?.geometry?.location?.lng ??
              place?.geometry?.coordinates?.[0]
            );

          name =
            place?.name ||
            place?.display_name ||
            place?.formatted_address ||
            name;
        } catch {
          setLocationSearchError(
            "Unable to load the selected location."
          );
          return;
        }
      }

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude)
      ) {
        setLocationSearchError(
          "Unable to determine the selected location."
        );
        return;
      }

      selectedLocationSearch.current =
        name;

      setSiteLatitude(latitude);
      setSiteLongitude(longitude);

      setSelectedLocationName(name);
      setLocationConfirmed(true);

      setForm((current) => ({
        ...current,
        location: name,
      }));

      setMapTarget({
        latitude,
        longitude,
      });

      setLocationSearch(name);
      setLocationResults([]);
      setLocationSearchError("");
      setMapError(false);
      setMapVisible(true);
    };

  const load = () => {
    setLoading(true);
    setLoadError("");

    getServiceRequests()
      .then((r) => {
        setRequests(
          Array.isArray(r.data)
            ? r.data
            : []
        );

        setLoadError("");
      })
      .catch((e: any) => {
        const status =
          e?.response?.status;

        if (status === 401) {
          setLoadError(
            "Your session has expired. Please sign in again."
          );
        } else if (status === 403) {
          setLoadError(
            "You do not have permission to view your service requests."
          );
        } else {
          setLoadError(
            "We couldn't load your service requests. Please try again."
          );
        }

        /*
         * Do not leave stale customer data visible
         * after a failed reload.
         *
         * The backend remains authoritative for
         * customer/tenant/object access.
         */
        setRequests([]);
      })
      .finally(() =>
        setLoading(false)
      );
  };

  useEffect(() => {
    if (!createOnly) {
      load();
    }
  }, [createOnly]);

  const reset = () => {
    setForm({
      title: "",
      description: "",
      service_type: "",
      priority: "select priority",
      preferred_visit_date: "",
      location: "",
      contact_number: "",
    });

    setShowCreate(false);
    setEditId(null);

    setSiteLatitude(null);
    setSiteLongitude(null);

    setLocationSearch("");
    setLocationResults([]);
    setLocationSearchError("");

    setSelectedLocationName("");
    setLocationConfirmed(false);

    setMapVisible(false);
    setMapError(false);
    setMapTarget(null);

    setError("");
    setSuccess("");
    setLoadError("");
  };

  const validate =
    () => {
      const title =
        form.title.trim();

      const description =
        form.description.trim();

      const serviceType =
        form.service_type.trim();

      const priority =
        form.priority.trim();

      const location =
        form.location.trim();

      const contactNumber =
        form.contact_number.trim();

      if (!title) {
        setError(
          "Please enter a title."
        );
        return false;
      }

      if (!description) {
        setError(
          "Please enter a description."
        );
        return false;
      }

      if (!serviceType) {
        setError(
          "Please select a service type."
        );
        return false;
      }

      if (
        !priority ||
        priority ===
          "select priority"
      ) {
        setError(
          "Please select a priority."
        );
        return false;
      }

      if (!location) {
        setError(
          "Please enter or select a location."
        );
        return false;
      }

      if (!locationConfirmed) {
        setError(
          "Please confirm the service location."
        );
        return false;
      }

      if (!/^\d{10}$/.test(contactNumber)) {
        setError(
          "Contact number must be exactly 10 digits."
        );
        return false;
      }

      setError("");
      return true;
    };

  const handleSubmit =
    async (
      event?: React.FormEvent
    ) => {
      event?.preventDefault();

      if (saving) {
        return;
      }

      if (!validate()) {
        return;
      }

      setSaving(true);
      setError("");
      setSuccess("");

      try {
        const title =
          form.title.trim();

        const description =
          form.description.trim();

        const location =
          form.location.trim();

        const contactNumber =
          form.contact_number.trim();

        const payload = {
          ...form,
          title,
          description,
          location,
          contact_number:
            contactNumber,
          preferred_visit_date:
            form.preferred_visit_date ||
            null,
          site_latitude:
            siteLatitude,
          site_longitude:
            siteLongitude,
        };

        if (editId) {
          await updateServiceRequest(
            editId,
            payload
          );

          setSuccess(
            "Request updated!"
          );

          setShowCreate(false);
          setEditId(null);

          setForm({
            title: "",
            description: "",
            service_type: "",
            priority:
              "select priority",
            preferred_visit_date:
              "",
            location: "",
            contact_number: "",
          });

          load();
        } else {
          await createServiceRequest(
            payload
          );

          if (createOnly) {
            onNavigate?.(
              "cust_requests"
            );
            return;
          }

          setSuccess(
            "Request created!"
          );

          reset();
          load();
        }
      } catch (e: any) {
        const status =
          e?.response?.status;

        if (status === 401) {
          setError(
            "Your session has expired. Please sign in again."
          );
        } else if (
          status === 403
        ) {
          setError(
            "You do not have permission to update this service request."
          );
        } else {
          const detail =
            e?.response?.data?.detail;

          setError(
            typeof detail ===
              "string"
              ? detail
              : "Failed to save service request."
          );
        }
      } finally {
        setSaving(false);
      }
    };

  const handleCancel =
    async (
      id: number
    ) => {
      if (
        !confirm(
          "Cancel this service request?"
        )
      ) {
        return;
      }

      try {
        await cancelServiceRequest(
          id
        );

        load();
      } catch (e: any) {
        const status =
          e?.response?.status;

        if (status === 401) {
          alert(
            "Your session has expired. Please sign in again."
          );
        } else if (
          status === 403
        ) {
          alert(
            "You do not have permission to cancel this service request."
          );
        } else {
          const detail =
            e?.response?.data?.detail;

          alert(
            typeof detail ===
              "string"
              ? detail
              : "Failed to cancel service request."
          );
        }
      }
    };

  const startEdit =
    (sr: any) => {
      setForm({
        title:
          sr.title || "",
        description:
          sr.description || "",
        service_type:
          sr.service_type || "",
        priority:
          sr.priority ||
          "select priority",
        preferred_visit_date:
          sr.preferred_visit_date
            ? String(
                sr.preferred_visit_date
              ).slice(0, 10)
            : "",
        location:
          sr.location || "",
        contact_number:
          sr.contact_number ||
          "",
      });

      setSiteLatitude(
        sr.site_latitude ??
          null
      );

      setSiteLongitude(
        sr.site_longitude ??
          null
      );

      setSelectedLocationName(
        sr.location || ""
      );

      setEditId(sr.id);

      setLocationConfirmed(
        Boolean(
          sr.site_latitude !=
            null &&
          sr.site_longitude !=
            null
        )
      );

      setShowCreate(true);
      setError("");
      setSuccess("");
    };

  const upd = (
    k: string,
    v: string
  ) => {
    setForm((f) => ({
      ...f,
      [k]: v,
    }));
  };

  const inputStyle = {
    width: "100%",
    padding: "10px 12px",
    border:
      "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    boxSizing:
      "border-box" as const,
    outline: "none",
    fontFamily:
      "'Inter', sans-serif",
  };

  const labelStyle = {
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "4px",
    display:
      "block" as const,
  };

  const requiredStar = {
    color: "#DC2626",
  };

  if (createOnly) {
    return (
      <div
        style={{
          padding: "24px",
          height: "100%",
          overflowY: "auto",
          background: "#EEF4F1",
          fontFamily:
            "'Inter', sans-serif",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "760px",
            margin: "0 auto",
            padding:
              "10px 0 40px",
          }}
        >
          <h2
            style={{
              fontSize: "26px",
              fontWeight: 700,
              color: "#1F2933",
              marginBottom:
                "28px",
            }}
          >
            Create Service Request
          </h2>

          {error && (
            <div
              style={{
                background:
                  "#FEF2F2",
                border:
                  "1px solid #FECACA",
                borderRadius: "8px",
                padding: "10px",
                color: "#991B1B",
                fontSize: "13px",
                marginBottom:
                  "14px",
                display: "flex",
                alignItems:
                  "center",
                gap: "6px",
              }}
            >
              <AlertCircle
                size={14}
              />
              {error}
            </div>
          )}

          <div
            style={{
              display: "flex",
              flexDirection:
                "column",
              gap: "18px",
            }}
          >
            <div>
              <label
                style={
                  labelStyle
                }
              >
                Title{" "}
                <span
                  style={
                    requiredStar
                  }
                >
                  *
                </span>
              </label>

              <input
                style={inputStyle}
                value={
                  form.title
                }
                onChange={(e) =>
                  upd(
                    "title",
                    e.target.value
                  )
                }
                placeholder="Brief title for your request"
              />
            </div>

            <div>
              <label
                style={
                  labelStyle
                }
              >
                Description{" "}
                <span
                  style={
                    requiredStar
                  }
                >
                  *
                </span>
              </label>

              <textarea
                style={{
                  ...inputStyle,
                  minHeight: "120px",
                  resize:
                    "vertical",
                }}
                value={
                  form.description
                }
                onChange={(e) =>
                  upd(
                    "description",
                    e.target.value
                  )
                }
                placeholder="Describe the issue in detail..."
              />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "1fr 1fr",
                gap: "16px",
              }}
            >
              <div>
                <label
                  style={
                    labelStyle
                  }
                >
                  Service Type{" "}
                  <span
                    style={{
                      color: "red",
                    }}
                  >
                    *
                  </span>
                </label>

                <select
                  required
                  style={{
                    ...inputStyle,
                    color:
                      form.service_type
                        ? "#111827"
                        : "#9CA3AF",
                  }}
                  value={
                    form.service_type
                  }
                  onChange={(e) =>
                    upd(
                      "service_type",
                      e.target.value
                    )
                  }
                >
                  <option value="">
                    select service
                  </option>
                  <option value="HVAC Repair">
                    HVAC Repair
                  </option>
                  <option value="Electrical">
                    Electrical
                  </option>
                  <option value="Plumbing">
                    Plumbing
                  </option>
                  <option value="General Maintenance">
                    General Maintenance
                  </option>
                </select>
              </div>

              <div>
                <label
                  style={
                    labelStyle
                  }
                >
                  Priority{" "}
                  <span
                    style={{
                      color: "red",
                    }}
                  >
                    *
                  </span>
                </label>

                <select
                  required
                  style={{
                    ...inputStyle,
                    color:
                      form.priority !==
                      "select priority"
                        ? "#111827"
                        : "#9CA3AF",
                  }}
                  value={
                    form.priority
                  }
                  onChange={(e) =>
                    upd(
                      "priority",
                      e.target.value
                    )
                  }
                >
                  <option value="select priority">
                    select priority
                  </option>
                  <option value="LOW">
                    LOW
                  </option>
                  <option value="MEDIUM">
                    MEDIUM
                  </option>
                  <option value="HIGH">
                    HIGH
                  </option>
                  <option value="URGENT">
                    URGENT
                  </option>
                </select>
              </div>
            </div>

            <div>
              <label
                style={
                  labelStyle
                }
              >
                Preferred Visit Date
              </label>

              <input
                type="date"
                style={inputStyle}
                value={
                  form.preferred_visit_date
                }
                onChange={(e) =>
                  upd(
                    "preferred_visit_date",
                    e.target.value
                  )
                }
              />
            </div>

            <div>
              <label
                style={
                  labelStyle
                }
              >
                Contact Number{" "}
                <span
                  style={
                    requiredStar
                  }
                >
                  *
                </span>
              </label>

              <input
                type="tel"
                style={inputStyle}
                value={
                  form.contact_number
                }
                onChange={(e) =>
                  upd(
                    "contact_number",
                    e.target.value
                      .replace(/\D/g, "")
                      .slice(0, 10)
                  )
                }
                maxLength={10}
                placeholder="Enter contact number"
              />
            </div>

            <div>
              <label
                style={
                  labelStyle
                }
              >
                Service Location{" "}
                <span
                  style={
                    requiredStar
                  }
                >
                  *
                </span>
              </label>

              <div
                style={{
                  display: "flex",
                  gap: "8px",
                  marginBottom:
                    "8px",
                }}
              >
                <input
                  style={{
                    ...inputStyle,
                    flex: 1,
                  }}
                  value={
                    locationSearch
                  }
                  onChange={(e) => {
                    setLocationSearch(
                      e.target.value
                    );
                    setLocationConfirmed(
                      false
                    );
                  }}
                  placeholder="Search service location"
                />

                <button
                  type="button"
                  onClick={
                    getCurrentLocation
                  }
                  disabled={
                    isGettingLocation
                  }
                  style={{
                    border:
                      "1px solid #D1D5DB",
                    background:
                      "#FFFFFF",
                    borderRadius:
                      "8px",
                    padding:
                      "0 12px",
                    cursor:
                      isGettingLocation
                        ? "not-allowed"
                        : "pointer",
                    display:
                      "flex",
                    alignItems:
                      "center",
                    gap: "6px",
                    whiteSpace:
                      "nowrap",
                  }}
                >
                  <MapPin
                    size={15}
                  />
                  {isGettingLocation
                    ? "Locating..."
                    : "Use my location"}
                </button>
              </div>

              {locationSearchError && (
                <div
                  style={{
                    color:
                      "#991B1B",
                    fontSize:
                      "12px",
                    marginBottom:
                      "8px",
                  }}
                >
                  {
                    locationSearchError
                  }
                </div>
              )}

              {isSearchingLocations && (
                <div
                  style={{
                    color:
                      "#6B7280",
                    fontSize:
                      "12px",
                    marginBottom:
                      "8px",
                  }}
                >
                  Searching...
                </div>
              )}

              {locationResults.length >
                0 && (
                <div
                  style={{
                    border:
                      "1px solid #E5E7EB",
                    borderRadius:
                      "8px",
                    background:
                      "#FFFFFF",
                    overflow:
                      "hidden",
                    marginBottom:
                      "8px",
                  }}
                >
                  {locationResults.map(
                    (
                      result,
                      index
                    ) => (
                      <button
                        type="button"
                        key={
                          result.id ||
                          result.place_id ||
                          index
                        }
                        onClick={() =>
                          void selectLocation(
                            result
                          )
                        }
                        style={{
                          display:
                            "block",
                          width:
                            "100%",
                          border:
                            "none",
                          borderBottom:
                            index ===
                            locationResults.length -
                              1
                              ? "none"
                              : "1px solid #F3F4F6",
                          background:
                            "#FFFFFF",
                          textAlign:
                            "left",
                          padding:
                            "10px 12px",
                          cursor:
                            "pointer",
                          fontSize:
                            "13px",
                          color:
                            "#374151",
                        }}
                      >
                        {result.description ||
                          result.display_name ||
                          result.name ||
                          result.place_name ||
                          result.formatted_address ||
                          "Location"}
                      </button>
                    )
                  )}
                </div>
              )}

              <div
                style={{
                  display:
                    "flex",
                  justifyContent:
                    "space-between",
                  alignItems:
                    "center",
                  marginBottom:
                    "8px",
                  gap:
                    "10px",
                }}
              >
                <span
                  style={{
                    fontSize:
                      "12px",
                    color:
                      locationConfirmed
                        ? "#166534"
                        : "#6B7280",
                    fontWeight:
                      locationConfirmed
                        ? 600
                        : 400,
                  }}
                >
                  {locationConfirmed
                    ? `Location confirmed${
                        selectedLocationName
                          ? `: ${selectedLocationName}`
                          : ""
                      }`
                    : "Select a location and confirm it on the map."}
                </span>

                <button
                  type="button"
                  onClick={() =>
                    setMapVisible(
                      (value) =>
                        !value
                    )
                  }
                  style={{
                    border:
                      "1px solid #D1D5DB",
                    background:
                      "#FFFFFF",
                    borderRadius:
                      "8px",
                    padding:
                      "6px 10px",
                    fontSize:
                      "12px",
                    fontWeight:
                      600,
                    cursor:
                      "pointer",
                  }}
                >
                  {mapVisible
                    ? "Hide Map"
                    : "Show Map"}
                </button>
              </div>

              {mapVisible && (
                <div>
                  {mapError && (
                    <div
                      style={{
                        background:
                          "#FEF2F2",
                        border:
                          "1px solid #FECACA",
                        color:
                          "#991B1B",
                        borderRadius:
                          "8px",
                        padding:
                          "8px 10px",
                        fontSize:
                          "12px",
                        marginBottom:
                          "8px",
                      }}
                    >
                      Map could not
                      be loaded.
                      You can still
                      enter the
                      location manually
                      and continue if
                      coordinates are
                      already available.
                    </div>
                  )}

                  <div
                    ref={
                      mapContainerRef
                    }
                    style={{
                      height:
                        "280px",
                      border:
                        "1px solid #D1D5DB",
                      borderRadius:
                        "10px",
                      overflow:
                        "hidden",
                      background:
                        "#F3F4F6",
                    }}
                  />

                  {isResolvingMapCenter && (
                    <div
                      style={{
                        fontSize:
                          "12px",
                        color:
                          "#6B7280",
                        marginTop:
                          "6px",
                      }}
                    >
                      Resolving selected
                      location...
                    </div>
                  )}
                </div>
              )}
            </div>

            <div
              style={{
                display: "flex",
                justifyContent:
                  "flex-end",
                gap: "10px",
                marginTop: "4px",
              }}
            >
              <button
                type="button"
                onClick={
                  reset
                }
                disabled={
                  saving
                }
                style={{
                  padding:
                    "10px 20px",
                  border:
                    "1px solid #D1D5DB",
                  borderRadius:
                    "8px",
                  background:
                    "#FFFFFF",
                  color:
                    "#374151",
                  fontSize:
                    "13px",
                  fontWeight:
                    700,
                  cursor:
                    saving
                      ? "not-allowed"
                      : "pointer",
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={() =>
                  void handleSubmit()
                }
                disabled={
                  saving
                }
                style={{
                  padding:
                    "10px 24px",
                  border:
                    "none",
                  borderRadius:
                    "8px",
                  background:
                    "#7AAE8A",
                  color:
                    "#fff",
                  fontSize:
                    "13px",
                  fontWeight:
                    700,
                  cursor:
                    saving
                      ? "not-allowed"
                      : "pointer",
                  display:
                    "flex",
                  alignItems:
                    "center",
                  gap:
                    "6px",
                  opacity:
                    saving
                      ? 0.7
                      : 1,
                }}
              >
                <Send
                  size={14}
                />
                {saving
                  ? "Submitting..."
                  : "Submit"}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily:
          "'Inter', sans-serif",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent:
            "space-between",
          alignItems: "center",
          marginBottom:
            "20px",
        }}
      >
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            display: "flex",
            alignItems:
              "center",
            gap: "8px",
          }}
        >
          <FileText
            size={22}
            color="#7AAE8A"
          />
          My Requests
        </h2>

        <button
          onClick={() => {
            onNavigate?.(
              "cust_create_request"
            );
          }}
          style={{
            padding:
              "10px 20px",
            border: "none",
            borderRadius:
              "10px",
            background:
              "#7AAE8A",
            color: "#fff",
            fontSize:
              "13px",
            fontWeight: 700,
            cursor:
              "pointer",
            display:
              "flex",
            alignItems:
              "center",
            gap:
              "6px",
          }}
        >
          <PlusCircle
            size={16}
          />
          New Request
        </button>
      </div>

      {/* Success */}
      {success && (
        <div
          style={{
            background:
              "#F0FFF4",
            border:
              "1px solid #C6F6D5",
            borderRadius:
              "8px",
            padding:
              "10px 14px",
            color:
              "#22543D",
            fontSize:
              "13px",
            marginBottom:
              "16px",
            display:
              "flex",
            alignItems:
              "center",
            gap:
              "8px",
          }}
        >
          <CheckCircle
            size={16}
          />
          {success}
        </div>
      )}

      {/* Request Cards */}
      {loading ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "48px",
            color:
              "#9CA3AF",
          }}
          role="status"
          aria-live="polite"
        >
          Loading...
        </div>
      ) : loadError ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "36px",
            background:
              "#fff",
            borderRadius:
              "14px",
            border:
              "1px solid #E3ECE7",
          }}
          role="alert"
        >
          <div
            style={{
              fontSize:
                "14px",
              fontWeight:
                600,
              color:
                "#374151",
              marginBottom:
                "14px",
            }}
          >
            {loadError}
          </div>

          <button
            type="button"
            onClick={load}
            style={{
              border:
                "none",
              borderRadius:
                "8px",
              background:
                "#7AAE8A",
              color:
                "#fff",
              padding:
                "9px 16px",
              fontSize:
                "12px",
              fontWeight:
                700,
              cursor:
                "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      ) : requests.length ===
        0 ? (
        <div
          style={{
            textAlign:
              "center",
            padding:
              "48px",
            color:
              "#9CA3AF",
          }}
        >
          No service requests yet.
          Create your first one!
        </div>
      ) : (
        <div
          style={{
            display:
              "grid",
            gridTemplateColumns:
              "repeat(3, 1fr)",
            gap:
              "12px",
          }}
        >
          {requests.map(
            (sr) => (
              <div
                key={sr.id}
                style={{
                  background:
                    "#fff",
                  borderRadius:
                    "14px",
                  padding:
                    "18px",
                  boxShadow:
                    "0 2px 8px rgba(0,0,0,0.05)",
                  border:
                    "1px solid #E3ECE7",
                }}
              >
                {/* Request Header */}
                <div
                  style={{
                    display:
                      "flex",
                    justifyContent:
                      "space-between",
                    alignItems:
                      "flex-start",
                    marginBottom:
                      "8px",
                    gap:
                      "10px",
                  }}
                >
                  <div
                    style={{
                      minWidth:
                        0,
                    }}
                  >
                    <span
                      style={{
                        fontSize:
                          "11px",
                        color:
                          "#9CA3AF",
                      }}
                    >
                      {
                        sr.request_number
                      }
                    </span>

                    <div
                      style={{
                        fontSize:
                          "15px",
                        fontWeight:
                          600,
                        color:
                          "#1F2933",
                        marginTop:
                          "3px",
                        whiteSpace:
                          "nowrap",
                        overflow:
                          "hidden",
                        textOverflow:
                          "ellipsis",
                      }}
                      title={
                        sr.title
                      }
                    >
                      {
                        sr.title
                      }
                    </div>
                  </div>

                  <span
                    style={badge(
                      sr.status
                    )}
                  >
                    {sr.status ===
                    "CREATED"
                      ? "UNASSIGNED"
                      : sr.status ===
                        "ASSIGNED"
                      ? "AWAITING ACCEPTANCE"
                      : sr.status ===
                        "ACCEPTED"
                      ? "ASSIGNED"
                      : sr.status ===
                        "EN_ROUTE"
                      ? "EN ROUTE"
                      : sr.status}
                  </span>
                </div>

                {/* Description */}
                <div
                  style={{
                    fontSize:
                      "12px",
                    lineHeight:
                      1.5,
                    color:
                      "#6B7280",
                    marginBottom:
                      "14px",
                    minHeight:
                      "36px",
                  }}
                >
                  {
                    sr.description
                  }
                </div>

                {/* Details */}
                <div
                  style={{
                    display:
                      "flex",
                    flexDirection:
                      "column",
                    gap:
                      "7px",
                    fontSize:
                      "12px",
                    color:
                      "#4B5563",
                  }}
                >
                  {sr.service_type && (
                    <div
                      style={{
                        display:
                          "flex",
                        justifyContent:
                          "space-between",
                        gap:
                          "8px",
                      }}
                    >
                      <span>
                        Service
                      </span>
                      <strong>
                        {
                          sr.service_type
                        }
                      </strong>
                    </div>
                  )}

                  {sr.priority && (
                    <div
                      style={{
                        display:
                          "flex",
                        justifyContent:
                          "space-between",
                        gap:
                          "8px",
                      }}
                    >
                      <span>
                        Priority
                      </span>
                      <strong>
                        {
                          sr.priority
                        }
                      </strong>
                    </div>
                  )}

                  {sr.preferred_visit_date && (
                    <div
                      style={{
                        display:
                          "flex",
                        justifyContent:
                          "space-between",
                        gap:
                          "8px",
                      }}
                    >
                      <span
                        style={{
                          display:
                            "flex",
                          alignItems:
                            "center",
                          gap:
                            "4px",
                        }}
                      >
                        <Clock
                          size={
                            12
                          }
                        />
                        Preferred
                      </span>

                      <strong>
                        {new Date(
                          sr.preferred_visit_date
                        ).toLocaleDateString()}
                      </strong>
                    </div>
                  )}

                  {sr.location && (
                    <div
                      style={{
                        display:
                          "flex",
                        alignItems:
                          "flex-start",
                        gap:
                          "5px",
                        color:
                          "#6B7280",
                      }}
                    >
                      <MapPin
                        size={
                          12
                        }
                        style={{
                          marginTop:
                            "2px",
                          flexShrink:
                            0,
                        }}
                      />

                      <span
                        style={{
                          overflow:
                            "hidden",
                          textOverflow:
                            "ellipsis",
                          whiteSpace:
                            "nowrap",
                        }}
                        title={
                          sr.location
                        }
                      >
                        {
                          sr.location
                        }
                      </span>
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div
                  style={{
                    display:
                      "flex",
                    justifyContent:
                      "flex-end",
                    gap:
                      "6px",
                    marginTop:
                      "16px",
                    paddingTop:
                      "12px",
                    borderTop:
                      "1px solid #F3F4F6",
                  }}
                >
                  {[
                    "CREATED",
                    "UNASSIGNED",
                  ].includes(
                    sr.status
                  ) && (
                    <>
                      <button
                        type="button"
                        onClick={() =>
                          startEdit(
                            sr
                          )
                        }
                        style={{
                          border:
                            "1px solid #D1D5DB",
                          background:
                            "#FFFFFF",
                          borderRadius:
                            "7px",
                          padding:
                            "6px 9px",
                          fontSize:
                            "11px",
                          fontWeight:
                            600,
                          color:
                            "#374151",
                          cursor:
                            "pointer",
                          display:
                            "flex",
                          alignItems:
                            "center",
                          gap:
                            "4px",
                        }}
                      >
                        <Edit3
                          size={
                            12
                          }
                        />
                        Edit
                      </button>

                      <button
                        type="button"
                        onClick={() =>
                          void handleCancel(
                            sr.id
                          )
                        }
                        style={{
                          border:
                            "1px solid #FECACA",
                          background:
                            "#FEF2F2",
                          borderRadius:
                            "7px",
                          padding:
                            "6px 9px",
                          fontSize:
                            "11px",
                          fontWeight:
                            600,
                          color:
                            "#991B1B",
                          cursor:
                            "pointer",
                          display:
                            "flex",
                          alignItems:
                            "center",
                          gap:
                            "4px",
                        }}
                      >
                        <XCircle
                          size={
                            12
                          }
                        />
                        Cancel
                      </button>
                    </>
                  )}

                  {[
                    "CANCELLED",
                    "COMPLETED",
                  ].includes(
                    sr.status
                  ) && (
                    <span
                      style={{
                        fontSize:
                          "11px",
                        color:
                          "#9CA3AF",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        gap:
                          "4px",
                      }}
                    >
                      <CheckCircle
                        size={
                          12
                        }
                      />
                      Finalized
                    </span>
                  )}
                </div>
              </div>
            )
          )}
        </div>
      )}

      {/* Edit/Create Modal */}
      {showCreate && (
        <div
          style={{
            position:
              "fixed",
            inset: 0,
            background:
              "rgba(15,23,42,0.45)",
            display:
              "flex",
            alignItems:
              "center",
            justifyContent:
              "center",
            padding:
              "20px",
            zIndex:
              1000,
          }}
        >
          <div
            style={{
              width:
                "100%",
              maxWidth:
                "760px",
              maxHeight:
                "90vh",
              overflowY:
                "auto",
              background:
                "#FFFFFF",
              borderRadius:
                "16px",
              boxShadow:
                "0 20px 40px rgba(0,0,0,0.18)",
            }}
          >
            <div
              style={{
                display:
                  "flex",
                justifyContent:
                  "space-between",
                alignItems:
                  "center",
                padding:
                  "18px 20px",
                borderBottom:
                  "1px solid #E5E7EB",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize:
                      "17px",
                    fontWeight:
                      700,
                    color:
                      "#1F2933",
                  }}
                >
                  {editId
                    ? "Edit Service Request"
                    : "Create Service Request"}
                </div>

                <div
                  style={{
                    fontSize:
                      "12px",
                    color:
                      "#6B7280",
                    marginTop:
                      "4px",
                  }}
                >
                  Update the
                  request
                  details below.
                </div>
              </div>

              <button
                type="button"
                onClick={
                  reset
                }
                disabled={
                  saving
                }
                style={{
                  border:
                    "none",
                  background:
                    "transparent",
                  padding:
                    "6px",
                  cursor:
                    saving
                      ? "not-allowed"
                      : "pointer",
                  color:
                    "#6B7280",
                }}
                aria-label="Close"
              >
                <X
                  size={
                    20
                  }
                />
              </button>
            </div>

            <form
              onSubmit={(event) =>
                void handleSubmit(
                  event
                )
              }
              style={{
                padding:
                  "20px",
              }}
            >
              {error && (
                <div
                  style={{
                    background:
                      "#FEF2F2",
                    border:
                      "1px solid #FECACA",
                    borderRadius:
                      "8px",
                    padding:
                      "10px",
                    color:
                      "#991B1B",
                    fontSize:
                      "13px",
                    marginBottom:
                      "14px",
                    display:
                      "flex",
                    alignItems:
                      "center",
                    gap:
                      "6px",
                  }}
                >
                  <AlertCircle
                    size={
                      14
                    }
                  />
                  {error}
                </div>
              )}

              <div
                style={{
                  display:
                    "flex",
                  flexDirection:
                    "column",
                  gap:
                    "18px",
                }}
              >
                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Title{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <input
                    style={
                      inputStyle
                    }
                    value={
                      form.title
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "title",
                        e.target
                          .value
                      )
                    }
                    placeholder="Brief title for your request"
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Description{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <textarea
                    style={{
                      ...inputStyle,
                      minHeight:
                        "120px",
                      resize:
                        "vertical",
                    }}
                    value={
                      form.description
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "description",
                        e.target
                          .value
                      )
                    }
                    placeholder="Describe the issue in detail..."
                  />
                </div>

                <div
                  style={{
                    display:
                      "grid",
                    gridTemplateColumns:
                      "1fr 1fr",
                    gap:
                      "16px",
                  }}
                >
                  <div>
                    <label
                      style={
                        labelStyle
                      }
                    >
                      Service Type{" "}
                      <span
                        style={{
                          color:
                            "red",
                        }}
                      >
                        *
                      </span>
                    </label>

                    <select
                      required
                      style={{
                        ...inputStyle,
                        color:
                          form.service_type
                            ? "#111827"
                            : "#9CA3AF",
                      }}
                      value={
                        form.service_type
                      }
                      onChange={(
                        e
                      ) =>
                        upd(
                          "service_type",
                          e.target
                            .value
                        )
                      }
                    >
                      <option value="">
                        select service
                      </option>

                      <option value="HVAC Repair">
                        HVAC Repair
                      </option>

                      <option value="Electrical">
                        Electrical
                      </option>

                      <option value="Plumbing">
                        Plumbing
                      </option>

                      <option value="General Maintenance">
                        General Maintenance
                      </option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={
                        labelStyle
                      }
                    >
                      Priority{" "}
                      <span
                        style={{
                          color:
                            "red",
                        }}
                      >
                        *
                      </span>
                    </label>

                    <select
                      required
                      style={{
                        ...inputStyle,
                        color:
                          form.priority !==
                          "select priority"
                            ? "#111827"
                            : "#9CA3AF",
                      }}
                      value={
                        form.priority
                      }
                      onChange={(
                        e
                      ) =>
                        upd(
                          "priority",
                          e.target
                            .value
                        )
                      }
                    >
                      <option value="select priority">
                        select priority
                      </option>

                      <option value="LOW">
                        LOW
                      </option>

                      <option value="MEDIUM">
                        MEDIUM
                      </option>

                      <option value="HIGH">
                        HIGH
                      </option>

                      <option value="URGENT">
                        URGENT
                      </option>
                    </select>
                  </div>
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Preferred Visit Date
                  </label>

                  <input
                    type="date"
                    style={
                      inputStyle
                    }
                    value={
                      form.preferred_visit_date
                    }
                    onChange={(
                      e
                    ) =>
                      upd(
                        "preferred_visit_date",
                        e.target
                          .value
                      )
                    }
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Contact Number{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <input
                    type="tel"
                    style={
                      inputStyle
                    }
                    value={
                      form.contact_number
                    }
                    onChange={(e) =>
                      upd(
                        "contact_number",
                        e.target.value
                          .replace(/\D/g, "")
                          .slice(0, 10)
                      )
                    }
                    maxLength={10}
                    placeholder="Enter contact number"
                  />
                </div>

                <div>
                  <label
                    style={
                      labelStyle
                    }
                  >
                    Service Location{" "}
                    <span
                      style={
                        requiredStar
                      }
                    >
                      *
                    </span>
                  </label>

                  <div
                    style={{
                      display:
                        "flex",
                      gap:
                        "8px",
                      marginBottom:
                        "8px",
                    }}
                  >
                    <input
                      style={{
                        ...inputStyle,
                        flex: 1,
                      }}
                      value={
                        locationSearch
                      }
                      onChange={(
                        e
                      ) => {
                        setLocationSearch(
                          e.target.value
                        );
                        setLocationConfirmed(
                          false
                        );
                      }}
                      placeholder="Search service location"
                    />

                    <button
                      type="button"
                      onClick={
                        getCurrentLocation
                      }
                      disabled={
                        isGettingLocation
                      }
                      style={{
                        border:
                          "1px solid #D1D5DB",
                        background:
                          "#FFFFFF",
                        borderRadius:
                          "8px",
                        padding:
                          "0 12px",
                        cursor:
                          isGettingLocation
                            ? "not-allowed"
                            : "pointer",
                        display:
                          "flex",
                        alignItems:
                          "center",
                        gap:
                          "6px",
                        whiteSpace:
                          "nowrap",
                      }}
                    >
                      <MapPin
                        size={
                          15
                        }
                      />

                      {isGettingLocation
                        ? "Locating..."
                        : "Use my location"}
                    </button>
                  </div>

                  {locationSearchError && (
                    <div
                      style={{
                        color:
                          "#991B1B",
                        fontSize:
                          "12px",
                        marginBottom:
                          "8px",
                      }}
                    >
                      {
                        locationSearchError
                      }
                    </div>
                  )}

                  {isSearchingLocations && (
                    <div
                      style={{
                        color:
                          "#6B7280",
                        fontSize:
                          "12px",
                        marginBottom:
                          "8px",
                      }}
                    >
                      Searching...
                    </div>
                  )}

                  {locationResults.length >
                    0 && (
                    <div
                      style={{
                        border:
                          "1px solid #E5E7EB",
                        borderRadius:
                          "8px",
                        background:
                          "#FFFFFF",
                        overflow:
                          "hidden",
                        marginBottom:
                          "8px",
                      }}
                    >
                      {locationResults.map(
                        (
                          result,
                          index
                        ) => (
                          <button
                            type="button"
                            key={
                              result.id ||
                              result.place_id ||
                              index
                            }
                            onClick={() =>
                              void selectLocation(
                                result
                              )
                            }
                            style={{
                              display:
                                "block",
                              width:
                                "100%",
                              border:
                                "none",
                              borderBottom:
                                index ===
                                locationResults.length -
                                  1
                                  ? "none"
                                  : "1px solid #F3F4F6",
                              background:
                                "#FFFFFF",
                              textAlign:
                                "left",
                              padding:
                                "10px 12px",
                              cursor:
                                "pointer",
                              fontSize:
                                "13px",
                              color:
                                "#374151",
                            }}
                          >
                            {result.display_name ||
                              result.name ||
                              "Location"}
                          </button>
                        )
                      )}
                    </div>
                  )}

                  <div
                    style={{
                      display:
                        "flex",
                      justifyContent:
                        "space-between",
                      alignItems:
                        "center",
                      marginBottom:
                        "8px",
                      gap:
                        "10px",
                    }}
                  >
                    <span
                      style={{
                        fontSize:
                          "12px",
                        color:
                          locationConfirmed
                            ? "#166534"
                            : "#6B7280",
                        fontWeight:
                          locationConfirmed
                            ? 600
                            : 400,
                      }}
                    >
                      {locationConfirmed
                        ? `Location confirmed${
                            selectedLocationName
                              ? `: ${selectedLocationName}`
                              : ""
                          }`
                        : "Select a location and confirm it on the map."}
                    </span>

                    <button
                      type="button"
                      onClick={() =>
                        setMapVisible(
                          (value) =>
                            !value
                        )
                      }
                      style={{
                        border:
                          "1px solid #D1D5DB",
                        background:
                          "#FFFFFF",
                        borderRadius:
                          "8px",
                        padding:
                          "6px 10px",
                        fontSize:
                          "12px",
                        fontWeight:
                          600,
                        cursor:
                          "pointer",
                      }}
                    >
                      {mapVisible
                        ? "Hide Map"
                        : "Show Map"}
                    </button>
                  </div>

                  {mapVisible && (
                    <div>
                      {mapError && (
                        <div
                          style={{
                            background:
                              "#FEF2F2",
                            border:
                              "1px solid #FECACA",
                            color:
                              "#991B1B",
                            borderRadius:
                              "8px",
                            padding:
                              "8px 10px",
                            fontSize:
                              "12px",
                            marginBottom:
                              "8px",
                          }}
                        >
                          Map could not be loaded.
                          You can still enter the
                          location manually and
                          continue if coordinates
                          are already available.
                        </div>
                      )}

                      <div
                        ref={
                          mapContainerRef
                        }
                        style={{
                          height:
                            "280px",
                          border:
                            "1px solid #D1D5DB",
                          borderRadius:
                            "10px",
                          overflow:
                            "hidden",
                          background:
                            "#F3F4F6",
                        }}
                      />

                      {isResolvingMapCenter && (
                        <div
                          style={{
                            fontSize:
                              "12px",
                            color:
                              "#6B7280",
                            marginTop:
                              "6px",
                          }}
                        >
                          Resolving
                          selected
                          location...
                        </div>
                      )}
                    </div>
                  )}
                </div>

                <div
                  style={{
                    display:
                      "flex",
                    justifyContent:
                      "flex-end",
                    gap:
                      "10px",
                    marginTop:
                      "4px",
                  }}
                >
                  <button
                    type="button"
                    onClick={
                      reset
                    }
                    disabled={
                      saving
                    }
                    style={{
                      padding:
                        "10px 20px",
                      border:
                        "1px solid #D1D5DB",
                      borderRadius:
                        "8px",
                      background:
                        "#FFFFFF",
                      color:
                        "#374151",
                      fontSize:
                        "13px",
                      fontWeight:
                        700,
                      cursor:
                        saving
                          ? "not-allowed"
                          : "pointer",
                    }}
                  >
                    Cancel
                  </button>

                  <button
                    type="submit"
                    disabled={
                      saving
                    }
                    style={{
                      padding:
                        "10px 24px",
                      border:
                        "none",
                      borderRadius:
                        "8px",
                      background:
                        "#7AAE8A",
                      color:
                        "#fff",
                      fontSize:
                        "13px",
                      fontWeight:
                        700,
                      cursor:
                        saving
                          ? "not-allowed"
                          : "pointer",
                      display:
                        "flex",
                      alignItems:
                        "center",
                      gap:
                        "6px",
                      opacity:
                        saving
                          ? 0.7
                          : 1,
                    }}
                  >
                    <Send
                      size={
                        14
                      }
                    />

                    {saving
                      ? "Submitting..."
                      : editId
                      ? "Update"
                      : "Submit"}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}