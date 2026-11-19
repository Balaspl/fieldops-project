import React, { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { 
  X, 
  Search, 
  User, 
  MapPin, 
  Briefcase, 
  Clock, 
  AlertCircle, 
  CheckCircle, 
  ShieldAlert 
} from "lucide-react";
import { getAvailableTechnicians, forceAssignJob, getJob } from "../../services/planningService";
import EmptyState from "../ui/EmptyState";

interface OverrideModalProps {
  jobId: number;
  jobTitle: string;
  initialJobLocation?: string;
  currentUserRole?: string;
  onClose: () => void;
  onSuccess: () => void;
}

interface Technician {
  technician_id: number;
  technician: string;
  skill: string;
  location: string;
  status: string;
  current_jobs: number;
  max_jobs: number;
  eligible_for_assignment: boolean;
}

interface FormValues {
  technicianId: string;
  justification: string;
  actorName: string;
  actorRole: string;
}

// Haversine distance calculator in km
function calculateDistance(loc1?: string, loc2?: string): number | null {
  if (!loc1 || !loc2) return null;
  const parts1 = loc1.split(",");
  const parts2 = loc2.split(",");
  if (parts1.length !== 2 || parts2.length !== 2) return null;
  
  const lat1 = parseFloat(parts1[0].trim());
  const lon1 = parseFloat(parts1[1].trim());
  const lat2 = parseFloat(parts2[0].trim());
  const lon2 = parseFloat(parts2[1].trim());
  
  if (isNaN(lat1) || isNaN(lon1) || isNaN(lat2) || isNaN(lon2)) return null;

  const R = 6371; // Earth radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export default function OverrideModal({
  jobId,
  jobTitle,
  initialJobLocation,
  currentUserRole = "dispatcher",
  onClose,
  onSuccess
}: OverrideModalProps) {
  const [jobLocation, setJobLocation] = useState(initialJobLocation || "");
  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [loadingTechs, setLoadingTechs] = useState(true);
  const [submitError, setSubmitError] = useState("");
  const [submitSuccess, setSubmitSuccess] = useState("");

  // Filters state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSkill, setSelectedSkill] = useState("all");
  const [selectedZone, setSelectedZone] = useState("all");
  const [selectedStatus, setSelectedStatus] = useState("all");

  // React Hook Form
  const { register, handleSubmit, watch, setValue, formState: { errors, isValid, isSubmitting } } = useForm<FormValues>({
    mode: "onChange",
    defaultValues: {
      technicianId: "",
      justification: "",
      actorName: currentUserRole === "admin" ? "Admin Rajesh" : currentUserRole === "manager" ? "Manager Priya" : "Dispatcher John",
      actorRole: currentUserRole
    }
  });

  const watchedTechId = watch("technicianId");
  const watchedJustification = watch("justification") || "";
  const watchedRole = watch("actorRole") || "dispatcher";

  // Fetch job location if needed
  useEffect(() => {
    if (!jobLocation) {
      getJob(jobId)
        .then(res => {
          if (res.data && res.data.location) {
            setJobLocation(res.data.location);
          }
        })
        .catch(err => console.warn("Failed to fetch location", err));
    }
  }, [jobId, jobLocation]);

  // Fetch technicians
  useEffect(() => {
    getAvailableTechnicians()
      .then(res => {
        if (res && res.data) {
          setTechnicians(res.data);
        }
      })
      .catch(() => setSubmitError("Failed to fetch available technicians list."))
      .finally(() => setLoadingTechs(false));
  }, []);

  // Update default actor name when role is simulated
  useEffect(() => {
    if (watchedRole === "admin") {
      setValue("actorName", "Admin Rajesh");
    } else if (watchedRole === "manager") {
      setValue("actorName", "Manager Priya");
    } else {
      setValue("actorName", "Dispatcher John");
    }
  }, [watchedRole, setValue]);

  // Check if simulated role is authorized
  const isRoleAuthorized = 
    watchedRole === "admin" || 
    watchedRole === "manager" || 
    watchedRole === "dispatcher";

  // Filter technicians lists
  const filteredTechs = technicians.filter(tech => {
    // 1. Text Search query (matches name, skill, or location coordinates)
    const matchesSearch = searchQuery.trim() === "" || 
      tech.technician.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tech.skill.toLowerCase().includes(searchQuery.toLowerCase()) ||
      tech.location.toLowerCase().includes(searchQuery.toLowerCase());

    // 2. Skill Filter
    const matchesSkill = selectedSkill === "all" || tech.skill.toLowerCase() === selectedSkill.toLowerCase();

    // 3. Zone/Location Filter (matches coords or substrings)
    const matchesZone = selectedZone === "all" || tech.location.toLowerCase().includes(selectedZone.toLowerCase());

    // 4. Status Filter
    const matchesStatus = selectedStatus === "all" || tech.status.toLowerCase() === selectedStatus.toLowerCase();

    return matchesSearch && matchesSkill && matchesZone && matchesStatus;
  });

  // Extract unique values for filter selections
  const skillsList = Array.from(new Set(technicians.map(t => t.skill)));
  const statusesList = Array.from(new Set(technicians.map(t => t.status)));

  const onSubmit = async (data: FormValues) => {
    if (!isRoleAuthorized) {
      setSubmitError("Unauthorized role. Manual override is restricted to Dispatchers, Managers, and Admins.");
      return;
    }
    try {
      setSubmitError("");
      setSubmitSuccess("");
      
      const res = await forceAssignJob(
        jobId,
        parseInt(data.technicianId),
        data.justification,
        data.actorRole
      );

      if (res && res.status >= 200 && res.status < 300) {
        setSubmitSuccess("Manual override applied successfully!");
        setTimeout(() => {
          onSuccess();
          onClose();
        }, 1000);
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || "Failed to commit manual assignment.";
      setSubmitError(msg);
    }
  };

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-slate-900/60 backdrop-blur-sm p-4 animate-fadeIn">
      <div 
        className="w-full max-w-4xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-100 flex flex-col max-h-[90vh]"
        style={{ fontFamily: "'Inter', sans-serif" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="override-modal-title"
      >
        {/* Header */}
        <div className="p-5 bg-gradient-to-r from-slate-900 to-slate-800 text-white flex justify-between items-center shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <ShieldAlert className="text-amber-500 w-5 h-5 shrink-0" />
              <h2 id="override-modal-title" className="text-lg font-bold tracking-tight">Manual Override</h2>
            </div>
            <p className="text-slate-300 text-xs mt-1">
              Job: <span className="font-semibold text-slate-100">{jobTitle}</span> (ID: #{jobId})
            </p>
          </div>
          <button 
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-white/10 text-slate-300 hover:text-white transition"
            aria-label="Close modal"
          >
            <X size={20} />
          </button>
        </div>

        {/* Role and Name simulation inputs */}
        <div className="bg-slate-100 border-b border-slate-200 px-6 py-2.5 flex flex-wrap items-center justify-between gap-4 text-xs font-semibold text-slate-700 shrink-0">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Role:</span>
              <select
                {...register("actorRole")}
                className="bg-white border border-slate-300 rounded px-2 py-1 font-bold focus:outline-none"
                aria-label="Simulated role selector"
              >
                <option value="dispatcher">Dispatcher (Authorized)</option>
                <option value="manager">Manager (Authorized)</option>
                <option value="admin">Admin (Authorized)</option>
                <option value="technician">Technician (Unauthorized)</option>
              </select>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Actor Name:</span>
              <input
                type="text"
                {...register("actorName", { required: true })}
                className="bg-white border border-slate-300 rounded px-2 py-1 font-semibold focus:outline-none w-36"
                placeholder="Actor Name"
              />
            </div>
          </div>
          {!isRoleAuthorized && (
            <span className="text-rose-600 flex items-center gap-1">
              <AlertCircle size={14} /> Role check failed: only managers, dispatchers, and admins are authorized.
            </span>
          )}
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit(onSubmit)} className="flex-1 overflow-y-auto p-6 space-y-6 flex flex-col min-h-0">
          {submitError && (
            <div className="p-3 bg-rose-50 border border-rose-100 text-rose-700 rounded-xl text-xs font-bold flex items-start gap-2 animate-shake">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{submitError}</span>
            </div>
          )}

          {submitSuccess && (
            <div className="p-3 bg-emerald-50 border border-emerald-100 text-emerald-700 rounded-xl text-xs font-bold flex items-start gap-2">
              <CheckCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{submitSuccess}</span>
            </div>
          )}

          {/* Technician Search Section */}
          <div className="flex-1 min-h-[220px] flex flex-col min-h-0">
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider mb-2">
              Select Technician
            </h3>
            
            {/* Search and Filters Bar */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-2 mb-3 shrink-0">
              <div className="relative">
                <Search size={14} className="absolute left-2.5 top-2.5 text-slate-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search by name..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-8 pr-2.5 py-1.5 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-slate-800"
                  aria-label="Search technicians"
                />
              </div>

              {/* Skill Filter */}
              <select
                value={selectedSkill}
                onChange={(e) => setSelectedSkill(e.target.value)}
                className="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-700 focus:outline-none"
                aria-label="Filter by skill"
              >
                <option value="all">All Skills</option>
                {skillsList.map(skill => (
                  <option key={skill} value={skill}>{skill}</option>
                ))}
              </select>

              {/* Zone Filter */}
              <select
                value={selectedZone}
                onChange={(e) => setSelectedZone(e.target.value)}
                className="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-700 focus:outline-none"
                aria-label="Filter by zone"
              >
                <option value="all">All Zones</option>
                <option value="13.08">Central Chennai (13.08)</option>
                <option value="13.00">South Chennai (13.00)</option>
              </select>

              {/* Status Filter */}
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="bg-slate-50 border border-slate-200 rounded-lg px-2 py-1.5 text-xs font-semibold text-slate-700 focus:outline-none"
                aria-label="Filter by status"
              >
                <option value="all">All Statuses</option>
                {statusesList.map(status => (
                  <option key={status} value={status}>{status}</option>
                ))}
              </select>
            </div>

            {loadingTechs ? (
              <div className="flex-1 flex flex-col items-center justify-center py-10">
                <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
                <p className="text-xs text-slate-500 font-semibold mt-3">Loading available technicians...</p>
              </div>
            ) : filteredTechs.length === 0 ? (
              <EmptyState
                title="No matching technicians found"
                description="Try refining search parameters."
              />
            ) : (
              <div className="flex-1 overflow-y-auto border border-slate-100 rounded-xl shadow-sm min-h-0">
                <table className="min-w-full bg-white divide-y divide-slate-100 text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider sticky top-0 z-10">
                    <tr>
                      <th className="px-4 py-2.5 w-10"></th>
                      <th className="px-4 py-2.5">Technician</th>
                      <th className="px-4 py-2.5">Skill</th>
                      <th className="px-4 py-2.5 text-center">Workload</th>
                      <th className="px-4 py-2.5 text-center">Distance</th>
                      <th className="px-4 py-2.5 text-center">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-semibold text-slate-700">
                    {filteredTechs.map(tech => {
                      const isSelected = watchedTechId === String(tech.technician_id);
                      const distance = calculateDistance(jobLocation, tech.location);
                      const displayDist = distance !== null ? `${distance.toFixed(1)} km` : "-";

                      return (
                        <tr 
                          key={tech.technician_id} 
                          onClick={() => setValue("technicianId", String(tech.technician_id), { shouldValidate: true })}
                          className={`cursor-pointer transition ${
                            isSelected 
                              ? "bg-slate-900 text-white hover:bg-slate-800" 
                              : "hover:bg-slate-50"
                          }`}
                        >
                          <td className="px-4 py-3 text-center">
                            <input
                              type="radio"
                              value={tech.technician_id}
                              {...register("technicianId", { required: "Please select a technician" })}
                              checked={isSelected}
                              onChange={() => setValue("technicianId", String(tech.technician_id), { shouldValidate: true })}
                              className="accent-slate-900 cursor-pointer"
                              aria-label={`Select ${tech.technician}`}
                            />
                          </td>
                          <td className="px-4 py-3 font-bold">
                            {tech.technician}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                              isSelected ? "bg-slate-800 text-white" : "bg-slate-100 text-slate-700"
                            }`}>
                              {tech.skill}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-center font-bold">
                            <span>{tech.current_jobs}</span>
                            <span className={isSelected ? "text-slate-400" : "text-slate-400"}>/{tech.max_jobs} jobs</span>
                          </td>
                          <td className="px-4 py-3 text-center">
                            {displayDist}
                          </td>
                          <td className="px-4 py-3 text-center">
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                              tech.status.toLowerCase() === "available" 
                                ? "bg-emerald-100 text-emerald-800 border border-emerald-200" 
                                : "bg-sky-100 text-sky-800 border border-sky-200"
                            }`}>
                              {tech.status}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {errors.technicianId && (
              <span className="text-[10px] text-rose-500 font-bold mt-1 block">
                {errors.technicianId.message}
              </span>
            )}
          </div>

          {/* Justification Section */}
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2 shrink-0">
            <div className="flex justify-between items-center">
              <label 
                htmlFor="override-justification-textarea"
                className="block text-xs font-bold text-slate-700 uppercase tracking-wider"
              >
                Justification (Requirement FR-025)
              </label>
              <span className={`text-xs font-bold ${watchedJustification.length >= 50 && watchedJustification.length <= 500 ? "text-emerald-600" : "text-amber-600"}`}>
                {watchedJustification.length} / 500 characters (min 50)
              </span>
            </div>

            <textarea
              id="override-justification-textarea"
              {...register("justification", {
                required: "Justification is required",
                minLength: { value: 50, message: "Justification must be at least 50 characters." },
                maxLength: { value: 500, message: "Justification cannot exceed 500 characters." }
              })}
              placeholder="Enter details on why this automatic planning rules override is required (min 50 chars)..."
              rows={3}
              className={`w-full bg-white border rounded-lg p-3 text-xs font-semibold focus:outline-none transition ${
                errors.justification ? "border-rose-400 focus:ring-1 focus:ring-rose-500" : "border-slate-200 focus:ring-1 focus:ring-slate-800"
              }`}
            />

            {errors.justification && (
              <p className="text-[10px] text-rose-500 font-bold flex items-center gap-1 mt-0.5">
                <AlertCircle size={10} />
                <span>{errors.justification.message}</span>
              </p>
            )}
          </div>

          {/* Footer Buttons */}
          <div className="flex gap-3 justify-end pt-2 border-t border-slate-100 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-bold transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isValid || !isRoleAuthorized || isSubmitting}
              className="px-5 py-2 bg-slate-950 hover:bg-slate-800 text-white rounded-lg text-xs font-bold transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              {isSubmitting ? "Applying Override..." : "Confirm Override"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
