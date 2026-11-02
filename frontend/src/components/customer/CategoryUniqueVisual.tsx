import React from "react";
import {
  Lightbulb,
  Fan,
  ToggleRight,
  Zap,
  ShieldAlert,
  Activity,
  BatteryCharging,
  Plug,
  Bell,
  CheckCircle2,
  Droplets,
  Pipette,
  Waves,
  Bath,
  UtensilsCrossed,
  Flame,
  ShowerHead,
  Gauge,
  AlertTriangle,
  Radio,
  Snowflake,
  Wind,
  Layers,
  Wrench,
  Tv,
  Microwave,
  Laptop,
  Wifi,
  Printer,
  Server,
  Lock,
  DoorClosed,
  Grid,
  Sun,
  Hammer,
  Paintbrush,
  Sparkles,
  Bug,
  Camera,
  Scissors,
  Move,
  FileCheck,
} from "lucide-react";

interface Props {
  categoryId: string;
  categoryName: string;
}

export default function CategoryUniqueVisual({ categoryId, categoryName }: Props) {
  const cid = categoryId.toLowerCase();
  const cname = categoryName.toLowerCase();

  // Helper to render distinct visual badges for each category
  const renderVisual = () => {
    // 1. Electrical
    if (cid.includes("light") || cname.includes("light")) {
      return {
        bg: "linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)",
        border: "#F59E0B",
        icon: <Lightbulb size={36} color="#D97706" strokeWidth={2.2} />,
        accent: "rgba(245, 158, 11, 0.15)",
        label: "Lighting & Fixtures",
      };
    }
    if (cid.includes("fan") || cname.includes("fan")) {
      return {
        bg: "linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)",
        border: "#0284C7",
        icon: <Fan size={36} color="#0284C7" strokeWidth={2.2} />,
        accent: "rgba(2, 132, 199, 0.15)",
        label: "Fans & Air Flow",
      };
    }
    if (cid.includes("switch") || cid.includes("socket") || cname.includes("switch")) {
      return {
        bg: "linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)",
        border: "#4F46E5",
        icon: <ToggleRight size={36} color="#4F46E5" strokeWidth={2.2} />,
        accent: "rgba(79, 70, 229, 0.15)",
        label: "Switches & Sockets",
      };
    }
    if (cid.includes("wiring") || cid.includes("cable") || cname.includes("wiring")) {
      return {
        bg: "linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)",
        border: "#EA580C",
        icon: <Zap size={36} color="#EA580C" strokeWidth={2.2} />,
        accent: "rgba(234, 88, 12, 0.15)",
        label: "Wiring & Conduits",
      };
    }
    if (cid.includes("mcb") || cid.includes("fuse") || cname.includes("mcb")) {
      return {
        bg: "linear-gradient(135deg, #FEE2E2 0%, #FECACA 100%)",
        border: "#DC2626",
        icon: <ShieldAlert size={36} color="#DC2626" strokeWidth={2.2} />,
        accent: "rgba(220, 38, 38, 0.15)",
        label: "Distribution Board",
      };
    }
    if (cid.includes("inverter") || cid.includes("ups") || cid.includes("battery")) {
      return {
        bg: "linear-gradient(135deg, #F3E8FF 0%, #E9D5FF 100%)",
        border: "#9333EA",
        icon: <BatteryCharging size={36} color="#9333EA" strokeWidth={2.2} />,
        accent: "rgba(147, 51, 234, 0.15)",
        label: "Inverter Backup",
      };
    }
    if (cid.includes("appliance_point") || cname.includes("point")) {
      return {
        bg: "linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)",
        border: "#059669",
        icon: <Plug size={36} color="#059669" strokeWidth={2.2} />,
        accent: "rgba(5, 150, 105, 0.15)",
        label: "Power Sockets",
      };
    }
    if (cid.includes("doorbell") || cname.includes("bell")) {
      return {
        bg: "linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)",
        border: "#CA8A04",
        icon: <Bell size={36} color="#CA8A04" strokeWidth={2.2} />,
        accent: "rgba(202, 138, 4, 0.15)",
        label: "Chimes & Intercom",
      };
    }
    if (cid.includes("earthing") || cname.includes("earthing") || cname.includes("safety")) {
      return {
        bg: "linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%)",
        border: "#16A34A",
        icon: <CheckCircle2 size={36} color="#16A34A" strokeWidth={2.2} />,
        accent: "rgba(22, 163, 74, 0.15)",
        label: "Electrical Safety",
      };
    }

    // 2. Plumbing
    if (cid.includes("tap") || cid.includes("faucet") || cname.includes("tap")) {
      return {
        bg: "linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)",
        border: "#0284C7",
        icon: <Droplets size={36} color="#0284C7" strokeWidth={2.2} />,
        accent: "rgba(2, 132, 199, 0.15)",
        label: "Chrome Taps & Mixers",
      };
    }
    if (cid.includes("pipe") || cname.includes("pipe")) {
      return {
        bg: "linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)",
        border: "#16A34A",
        icon: <Pipette size={36} color="#16A34A" strokeWidth={2.2} />,
        accent: "rgba(22, 163, 74, 0.15)",
        label: "CPVC & Water Pipes",
      };
    }
    if (cid.includes("drainage") || cid.includes("block") || cname.includes("drain")) {
      return {
        bg: "linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 100%)",
        border: "#475569",
        icon: <Waves size={36} color="#475569" strokeWidth={2.2} />,
        accent: "rgba(71, 85, 105, 0.15)",
        label: "Drain Cleaning",
      };
    }
    if (cid.includes("toilet") || cid.includes("sanitary") || cname.includes("toilet")) {
      return {
        bg: "linear-gradient(135deg, #CCFBF1 0%, #99F6E4 100%)",
        border: "#0D9488",
        icon: <Bath size={36} color="#0D9488" strokeWidth={2.2} />,
        accent: "rgba(13, 148, 136, 0.15)",
        label: "Sanitaryware Fixtures",
      };
    }
    if (cid.includes("basin") || cid.includes("sink") || cname.includes("sink")) {
      return {
        bg: "linear-gradient(135deg, #EFF6FF 0%, #DBEAFE 100%)",
        border: "#2563EB",
        icon: <UtensilsCrossed size={36} color="#2563EB" strokeWidth={2.2} />,
        accent: "rgba(37, 99, 235, 0.15)",
        label: "Kitchen Sink & Basin",
      };
    }
    if (cid.includes("tank") || cid.includes("motor") || cid.includes("pump")) {
      return {
        bg: "linear-gradient(135deg, #DBEAFE 0%, #BFDBFE 100%)",
        border: "#1D4ED8",
        icon: <Gauge size={36} color="#1D4ED8" strokeWidth={2.2} />,
        accent: "rgba(29, 78, 216, 0.15)",
        label: "Water Motor & Pump",
      };
    }
    if (cid.includes("geyser") || cname.includes("geyser") || cname.includes("heater")) {
      return {
        bg: "linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)",
        border: "#EA580C",
        icon: <Flame size={36} color="#EA580C" strokeWidth={2.2} />,
        accent: "rgba(234, 88, 12, 0.15)",
        label: "Water Heater",
      };
    }
    if (cid.includes("shower") || cname.includes("shower")) {
      return {
        bg: "linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)",
        border: "#0284C7",
        icon: <ShowerHead size={36} color="#0284C7" strokeWidth={2.2} />,
        accent: "rgba(2, 132, 199, 0.15)",
        label: "Shower Fittings",
      };
    }

    // 3. Air Conditioning & Refrigeration
    if (cid.includes("split_ac") || cname.includes("split ac")) {
      return {
        bg: "linear-gradient(135deg, #ECFDF5 0%, #A7F3D0 100%)",
        border: "#059669",
        icon: <Snowflake size={36} color="#059669" strokeWidth={2.2} />,
        accent: "rgba(5, 150, 105, 0.15)",
        label: "Inverter Split AC",
      };
    }
    if (cid.includes("window_ac") || cname.includes("window ac")) {
      return {
        bg: "linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)",
        border: "#0284C7",
        icon: <Wind size={36} color="#0284C7" strokeWidth={2.2} />,
        accent: "rgba(2, 132, 199, 0.15)",
        label: "Window Air Conditioner",
      };
    }
    if (cid.includes("refrigerator") || cname.includes("refrigerator") || cname.includes("fridge")) {
      return {
        bg: "linear-gradient(135deg, #EFF6FF 0%, #BFDBFE 100%)",
        border: "#2563EB",
        icon: <Layers size={36} color="#2563EB" strokeWidth={2.2} />,
        accent: "rgba(37, 99, 235, 0.15)",
        label: "Double Door Refrigerator",
      };
    }

    // 4. Home Appliances
    if (cid.includes("washing") || cname.includes("washing")) {
      return {
        bg: "linear-gradient(135deg, #F3E8FF 0%, #DDD6FE 100%)",
        border: "#7C3AED",
        icon: <Waves size={36} color="#7C3AED" strokeWidth={2.2} />,
        accent: "rgba(124, 58, 237, 0.15)",
        label: "Front-Load Washer",
      };
    }
    if (cid.includes("television") || cname.includes("tv")) {
      return {
        bg: "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)",
        border: "#334155",
        icon: <Tv size={36} color="#38BDF8" strokeWidth={2.2} />,
        accent: "rgba(56, 189, 248, 0.15)",
        label: "Smart OLED TV",
      };
    }
    if (cid.includes("microwave") || cname.includes("microwave") || cname.includes("oven")) {
      return {
        bg: "linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)",
        border: "#D97706",
        icon: <Microwave size={36} color="#D97706" strokeWidth={2.2} />,
        accent: "rgba(217, 119, 6, 0.15)",
        label: "Convection Oven",
      };
    }

    // 5. IT & Networking
    if (cid.includes("laptop") || cid.includes("desktop") || cname.includes("computer")) {
      return {
        bg: "linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%)",
        border: "#4F46E5",
        icon: <Laptop size={36} color="#4F46E5" strokeWidth={2.2} />,
        accent: "rgba(79, 70, 229, 0.15)",
        label: "Laptop & PC",
      };
    }
    if (cid.includes("wifi") || cid.includes("internet") || cname.includes("wifi")) {
      return {
        bg: "linear-gradient(135deg, #E0F2FE 0%, #BAE6FD 100%)",
        border: "#0284C7",
        icon: <Wifi size={36} color="#0284C7" strokeWidth={2.2} />,
        accent: "rgba(2, 132, 199, 0.15)",
        label: "Mesh Wi-Fi Router",
      };
    }

    // 6. Security
    if (cid.includes("cctv") || cid.includes("camera") || cname.includes("cctv")) {
      return {
        bg: "linear-gradient(135deg, #DBEAFE 0%, #93C5FD 100%)",
        border: "#2563EB",
        icon: <Camera size={36} color="#2563EB" strokeWidth={2.2} />,
        accent: "rgba(37, 99, 235, 0.15)",
        label: "Surveillance Camera",
      };
    }
    if (cid.includes("lock") || cname.includes("lock")) {
      return {
        bg: "linear-gradient(135deg, #FEF9C3 0%, #FEF08A 100%)",
        border: "#CA8A04",
        icon: <Lock size={36} color="#CA8A04" strokeWidth={2.2} />,
        accent: "rgba(202, 138, 4, 0.15)",
        label: "Digital Smart Lock",
      };
    }

    // 7. Painting & Carpentry
    if (cid.includes("paint") || cname.includes("paint")) {
      return {
        bg: "linear-gradient(135deg, #FFE4E6 0%, #FECDD3 100%)",
        border: "#E11D48",
        icon: <Paintbrush size={36} color="#E11D48" strokeWidth={2.2} />,
        accent: "rgba(225, 29, 72, 0.15)",
        label: "Emulsion Painting",
      };
    }
    if (cid.includes("furniture") || cid.includes("carpent") || cname.includes("furniture")) {
      return {
        bg: "linear-gradient(135deg, #FFEDD5 0%, #FED7AA 100%)",
        border: "#B45309",
        icon: <Hammer size={36} color="#B45309" strokeWidth={2.2} />,
        accent: "rgba(180, 83, 9, 0.15)",
        label: "Woodwork & Fitting",
      };
    }

    // 8. Pest Control, Solar, Purifier, Gardening
    if (cid.includes("pest") || cid.includes("insect") || cname.includes("pest")) {
      return {
        bg: "linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%)",
        border: "#16A34A",
        icon: <Bug size={36} color="#16A34A" strokeWidth={2.2} />,
        accent: "rgba(22, 163, 74, 0.15)",
        label: "Pest Shield Protection",
      };
    }
    if (cid.includes("solar") || cname.includes("solar")) {
      return {
        bg: "linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)",
        border: "#D97706",
        icon: <Sun size={36} color="#D97706" strokeWidth={2.2} />,
        accent: "rgba(217, 119, 6, 0.15)",
        label: "Solar Panels",
      };
    }
    if (cid.includes("purifier") || cid.includes("ro_") || cname.includes("purifier")) {
      return {
        bg: "linear-gradient(135deg, #CCFBF1 0%, #99F6E4 100%)",
        border: "#0D9488",
        icon: <Droplets size={36} color="#0D9488" strokeWidth={2.2} />,
        accent: "rgba(13, 148, 136, 0.15)",
        label: "RO Water Treatment",
      };
    }
    if (cid.includes("garden") || cid.includes("lawn") || cname.includes("garden")) {
      return {
        bg: "linear-gradient(135deg, #DCFCE7 0%, #BBF7D0 100%)",
        border: "#16A34A",
        icon: <Scissors size={36} color="#16A34A" strokeWidth={2.2} />,
        accent: "rgba(22, 163, 74, 0.15)",
        label: "Lawn & Gardening",
      };
    }

    // Default Fallback
    return {
      bg: "linear-gradient(135deg, #F1F5F9 0%, #E2E8F0 100%)",
      border: "#64748B",
      icon: <Wrench size={36} color="#0F172A" strokeWidth={2.2} />,
      accent: "rgba(15, 23, 42, 0.1)",
      label: categoryName,
    };
  };

  const item = renderVisual();

  return (
    <div
      style={{
        height: "125px",
        background: item.bg,
        position: "relative",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "12px",
      }}
    >
      {/* Decorative radial circles */}
      <div
        style={{
          position: "absolute",
          width: "90px",
          height: "90px",
          borderRadius: "50%",
          background: item.accent,
          top: "-15px",
          right: "-15px",
        }}
      />
      <div
        style={{
          position: "absolute",
          width: "60px",
          height: "60px",
          borderRadius: "50%",
          background: item.accent,
          bottom: "-10px",
          left: "-10px",
        }}
      />

      {/* Visual Icon Badge */}
      <div
        style={{
          width: "56px",
          height: "56px",
          borderRadius: "14px",
          background: "#FFFFFF",
          boxShadow: "0 6px 16px rgba(0, 0, 0, 0.1)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          marginBottom: "6px",
          zIndex: 1,
        }}
      >
        {item.icon}
      </div>

      <span
        style={{
          fontSize: "11px",
          fontWeight: 700,
          color: "#0F172A",
          zIndex: 1,
          background: "rgba(255, 255, 255, 0.8)",
          padding: "2px 8px",
          borderRadius: "999px",
        }}
      >
        {item.label}
      </span>
    </div>
  );
}

