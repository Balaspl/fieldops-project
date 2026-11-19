import React from "react";
import { ShieldAlert } from "lucide-react";

interface ForceAssignButtonProps {
  onClick: () => void;
  currentUserRole?: string;
  className?: string;
  label?: string;
}

export default function ForceAssignButton({
  onClick,
  currentUserRole = "dispatcher",
  className = "",
  label = "Force Assign"
}: ForceAssignButtonProps) {
  // Check if role is authorized (admin/dispatcher/manager)
  const isAuthorized = 
    currentUserRole.toLowerCase() === "admin" || 
    currentUserRole.toLowerCase() === "dispatcher" || 
    currentUserRole.toLowerCase() === "manager";

  // Hide button if not authorized to meet "Button visible to authorized roles only" requirement
  if (!isAuthorized) {
    return null;
  }

  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition shadow-sm ${className}`}
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      <ShieldAlert size={14} className="shrink-0 animate-pulse" />
      <span>{label}</span>
    </button>
  );
}
