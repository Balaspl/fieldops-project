import React from "react";

interface LoadingSpinnerProps {
  message?: string;
  fullPage?: boolean;
}

const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ message = "Loading...", fullPage = false }) => {
  const keyframes = `
    @keyframes orbit-spin {
      0% {
        transform: rotate(0deg) translateX(34px) rotate(0deg) scale(1, 2.83);
      }
      100% {
        transform: rotate(360deg) translateX(34px) rotate(-360deg) scale(1, 2.83);
      }
    }
    @keyframes opacity-front {
      0%, 49.9% { opacity: 1; }
      50%, 100% { opacity: 0; }
    }
    @keyframes opacity-back {
      0%, 49.9% { opacity: 0; }
      50%, 100% { opacity: 1; }
    }
    @keyframes globe-pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.95; }
    }
    @keyframes text-pulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.6; }
    }
  `;

  const size = 70;
  const center = size / 2;
  const radius = 28;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        padding: "40px 24px",
        width: "100%",
        height: fullPage ? "100%" : undefined,
        minHeight: fullPage ? "calc(100vh - 160px)" : undefined,
        boxSizing: "border-box",
        flex: fullPage ? 1 : undefined,
      }}
    >
      <style>{keyframes}</style>

      {/* Globe + Orbits container */}
      <div
        style={{
          position: "relative",
          width: `${size}px`,
          height: `${size}px`,
          marginBottom: "12px",
        }}
      >
        {/* Globe SVG */}
        <svg
          viewBox={`0 0 ${size} ${size}`}
          width={size}
          height={size}
          style={{
            position: "absolute",
            inset: 0,
            animation: "globe-pulse 3s ease-in-out infinite",
          }}
        >
          {/* 1. BACK ORBITS (rendered behind the globe circle) */}
          {/* Orbit 1 back (vertical-ish, rotated 75 deg) */}
          <g transform={`translate(${center}, ${center}) rotate(75) scale(1, 0.353)`}>
            <path d="M -34,0 A 34,34 0 0,1 34,0" fill="none" stroke="#2D3748" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2D3748" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 3.5s linear infinite, opacity-back 3.5s linear infinite",
              animationDelay: "-0.5s",
            }} />
          </g>

          {/* Orbit 2 back (diagonal, rotated -25 deg) */}
          <g transform={`translate(${center}, ${center}) rotate(-25) scale(1, 0.353)`}>
            <path d="M -34,0 A 34,34 0 0,1 34,0" fill="none" stroke="#2D3748" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2D3748" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 4.2s linear infinite, opacity-back 4.2s linear infinite",
              animationDelay: "-1.5s",
            }} />
          </g>

          {/* Orbit 3 back (diagonal, rotated 25 deg) */}
          <g transform={`translate(${center}, ${center}) rotate(25) scale(1, 0.353)`}>
            <path d="M -34,0 A 34,34 0 0,1 34,0" fill="none" stroke="#2D3748" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2D3748" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 4.8s linear infinite, opacity-back 4.8s linear infinite",
              animationDelay: "-2.5s",
            }} />
          </g>

          {/* 2. GLOBE BACKGROUND & LANDMASSES */}
          {/* Globe Circle Background */}
          <circle cx={center} cy={center} r={radius} fill="#EAF4EE" stroke="#2F4F3E" strokeWidth="1.5" />

          {/* Muted Gray-blue Landmasses */}
          {/* North America */}
          <polygon points="15,18 25,18 27,24 22,28 17,28 15,22" fill="#7AAE8A" />
          {/* South America */}
          <polygon points="18,36 24,36 28,42 26,48 22,54 20,48 16,42" fill="#7AAE8A" />
          {/* Greenland */}
          <polygon points="24,12 28,10 30,14 26,16" fill="#7AAE8A" />
          {/* Africa */}
          <polygon points="34,34 44,32 46,38 48,44 42,52 38,58 36,52 32,44" fill="#7AAE8A" />
          {/* Eurasia */}
          <polygon points="36,24 44,22 52,24 58,23 60,28 56,34 58,38 52,40 46,38 40,32" fill="#7AAE8A" />
          {/* Australia */}
          <polygon points="52,48 58,46 60,50 56,52 52,50" fill="#7AAE8A" />

          {/* 3. FRONT ORBITS (rendered in front of the globe circle) */}
          {/* Orbit 1 front */}
          <g transform={`translate(${center}, ${center}) rotate(75) scale(1, 0.353)`}>
            <path d="M 34,0 A 34,34 0 0,1 -34,0" fill="none" stroke="#7AAE8A" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2F4F3E" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 3.5s linear infinite, opacity-front 3.5s linear infinite",
              animationDelay: "-0.5s",
            }} />
          </g>

          {/* Orbit 2 front */}
          <g transform={`translate(${center}, ${center}) rotate(-25) scale(1, 0.353)`}>
            <path d="M 34,0 A 34,34 0 0,1 -34,0" fill="none" stroke="#7AAE8A" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2F4F3E" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 4.2s linear infinite, opacity-front 4.2s linear infinite",
              animationDelay: "-1.5s",
            }} />
          </g>

          {/* Orbit 3 front */}
          <g transform={`translate(${center}, ${center}) rotate(25) scale(1, 0.353)`}>
            <path d="M 34,0 A 34,34 0 0,1 -34,0" fill="none" stroke="#7AAE8A" strokeWidth="1.2" />
            <circle cx="0" cy="0" r="3" fill="#2F4F3E" style={{
              transformOrigin: "0px 0px",
              animation: "orbit-spin 4.8s linear infinite, opacity-front 4.8s linear infinite",
              animationDelay: "-2.5s",
            }} />
          </g>

          {/* Globe border outline (topmost edge for clean crisp visual line) */}
          <circle cx={center} cy={center} r={radius} fill="none" stroke="#2F4F3E" strokeWidth="1.5" />
        </svg>
      </div>

      {message && (
        <p
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "#2F4F3E",
            margin: 0,
            letterSpacing: "0.02em",
            fontFamily: "'Inter', sans-serif",
            animation: "text-pulse 1.5s ease-in-out infinite",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
};

export default LoadingSpinner;
