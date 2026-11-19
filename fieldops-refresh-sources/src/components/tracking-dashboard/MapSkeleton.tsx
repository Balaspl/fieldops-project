import React, { useState, useEffect } from 'react';
import { MapPin, Radio, Satellite, Wifi, Shield } from 'lucide-react';

/**
 * MapSkeleton — Premium full-screen loading state shown while
 * the Google Maps API initialises and technician data is being fetched.
 *
 * Features:
 *  • Animated grid lines mimicking a map
 *  • Pulsing radar sweep animation
 *  • Multi-step progress indicator
 *  • Floating ghost markers
 *  • Smooth stagger animations via CSS keyframes
 */

/* ---------- progress steps ---------- */
const LOAD_STEPS = [
  { id: 'auth',   label: 'Authenticating session',  icon: Shield,    duration: 800  },
  { id: 'maps',   label: 'Loading map engine',      icon: Satellite,  duration: 1200 },
  { id: 'data',   label: 'Fetching technician data', icon: Radio,     duration: 1400 },
  { id: 'ws',     label: 'Connecting live feed',     icon: Wifi,      duration: 1000 },
];

/* ---------- ghost marker positions ---------- */
const GHOST_MARKERS = [
  { top: '22%', left: '18%', delay: 0 },
  { top: '35%', left: '55%', delay: 0.3 },
  { top: '55%', left: '30%', delay: 0.6 },
  { top: '40%', left: '75%', delay: 0.9 },
  { top: '65%', left: '60%', delay: 1.2 },
  { top: '28%', left: '42%', delay: 0.5 },
];

export const MapSkeleton: React.FC = () => {
  const [activeStep, setActiveStep] = useState(0);

  /* Cycle through loading steps */
  useEffect(() => {
    if (activeStep >= LOAD_STEPS.length) return;
    const timer = setTimeout(() => {
      setActiveStep((s) => s + 1);
    }, LOAD_STEPS[activeStep].duration);
    return () => clearTimeout(timer);
  }, [activeStep]);

  const progress = Math.min((activeStep / LOAD_STEPS.length) * 100, 100);

  return (
    <div
      className="skel-root"
      data-testid="map-skeleton"
      role="status"
      aria-label="Loading tracking dashboard"
    >
      {/* ---------- injected CSS keyframes ---------- */}
      <style>{skeletonCSS}</style>

      {/* ── background gradient ── */}
      <div className="skel-bg" />

      {/* ── animated grid lines ── */}
      <svg className="skel-grid" viewBox="0 0 1000 1000" preserveAspectRatio="none">
        {Array.from({ length: 12 }).map((_, i) => (
          <line
            key={`h-${i}`}
            x1="0" y1={80 * i + 40} x2="1000" y2={80 * i + 40}
            stroke="rgba(148,163,184,0.12)"
            strokeWidth="1"
            className="skel-grid-line-h"
            style={{ animationDelay: `${i * 0.08}s` }}
          />
        ))}
        {Array.from({ length: 14 }).map((_, i) => (
          <line
            key={`v-${i}`}
            x1={72 * i + 36} y1="0" x2={72 * i + 36} y2="1000"
            stroke="rgba(148,163,184,0.10)"
            strokeWidth="1"
            className="skel-grid-line-v"
            style={{ animationDelay: `${i * 0.06}s` }}
          />
        ))}
      </svg>

      {/* ── pulsing radar rings (center) ── */}
      <div className="skel-radar">
        <div className="skel-radar-ring skel-ring-1" />
        <div className="skel-radar-ring skel-ring-2" />
        <div className="skel-radar-ring skel-ring-3" />
        <div className="skel-radar-dot" />
      </div>

      {/* ── ghost markers ── */}
      {GHOST_MARKERS.map((m, i) => (
        <div
          key={i}
          className="skel-ghost-marker"
          style={{ top: m.top, left: m.left, animationDelay: `${m.delay}s` }}
        >
          <MapPin size={18} />
        </div>
      ))}

      {/* ── simulated toolbar skeletons ── */}
      <div className="skel-toolbar-top">
        <div className="skel-pill skel-w-32" />
        <div className="skel-pill skel-w-24" />
        <div className="skel-pill skel-w-20" />
      </div>
      <div className="skel-toolbar-right">
        <div className="skel-pill-sq" />
      </div>
      <div className="skel-toolbar-bottom">
        <div className="skel-pill skel-w-36" />
      </div>

      {/* ── centered loading card ── */}
      <div className="skel-center">
        <div className="skel-card">
          {/* logo / icon */}
          <div className="skel-logo">
            <Radio size={28} className="skel-logo-icon" />
          </div>

          <h2 className="skel-title">FieldOps Commander</h2>
          <p className="skel-subtitle">Initializing Live Tracking Grid</p>

          {/* progress bar */}
          <div className="skel-progress-track">
            <div className="skel-progress-fill" style={{ width: `${progress}%` }} />
            <div className="skel-progress-glow" style={{ left: `${progress}%` }} />
          </div>

          {/* step list */}
          <div className="skel-steps">
            {LOAD_STEPS.map((step, i) => {
              const Icon = step.icon;
              const done = i < activeStep;
              const active = i === activeStep;

              return (
                <div
                  key={step.id}
                  className={`skel-step ${done ? 'skel-step-done' : ''} ${active ? 'skel-step-active' : ''}`}
                >
                  <div className={`skel-step-icon ${done ? 'done' : ''} ${active ? 'active' : ''}`}>
                    {done ? (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2.5 7L5.5 10L11.5 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    ) : (
                      <Icon size={14} />
                    )}
                  </div>
                  <span className="skel-step-label">{step.label}</span>
                  {active && <div className="skel-step-spinner" />}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

/* ===================== CSS ===================== */
const skeletonCSS = `
/* ── root ── */
.skel-root {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #0f172a;
  z-index: 50;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}

/* ── background ── */
.skel-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 50% 45%, rgba(16,185,129,0.06) 0%, transparent 70%),
    radial-gradient(ellipse 60% 50% at 30% 30%, rgba(59,130,246,0.04) 0%, transparent 60%),
    linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}

/* ── grid ── */
.skel-grid {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.5;
}

.skel-grid-line-h, .skel-grid-line-v {
  animation: skel-grid-fade 2.4s ease-in-out infinite alternate;
}

@keyframes skel-grid-fade {
  0% { opacity: 0.15; }
  100% { opacity: 0.45; }
}

/* ── radar ── */
.skel-radar {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 340px;
  height: 340px;
  pointer-events: none;
}

.skel-radar-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(16, 185, 129, 0.15);
  animation: skel-radar-pulse 3s ease-out infinite;
}

.skel-ring-1 {
  inset: 30%;
  animation-delay: 0s;
}
.skel-ring-2 {
  inset: 15%;
  animation-delay: 0.6s;
}
.skel-ring-3 {
  inset: 0;
  animation-delay: 1.2s;
}

@keyframes skel-radar-pulse {
  0% { transform: scale(0.6); opacity: 0.8; border-color: rgba(16,185,129,0.3); }
  100% { transform: scale(1.4); opacity: 0; border-color: rgba(16,185,129,0); }
}

.skel-radar-dot {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 8px;
  height: 8px;
  background: #10b981;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 16px 4px rgba(16,185,129,0.4);
  animation: skel-dot-glow 1.5s ease-in-out infinite alternate;
}

@keyframes skel-dot-glow {
  0% { box-shadow: 0 0 8px 2px rgba(16,185,129,0.3); }
  100% { box-shadow: 0 0 24px 8px rgba(16,185,129,0.6); }
}

/* ── ghost markers ── */
.skel-ghost-marker {
  position: absolute;
  color: rgba(148,163,184,0.2);
  animation: skel-ghost 2.5s ease-in-out infinite alternate;
  filter: drop-shadow(0 0 4px rgba(148,163,184,0.1));
}

@keyframes skel-ghost {
  0% { opacity: 0.15; transform: translateY(0); }
  100% { opacity: 0.4; transform: translateY(-4px); }
}

/* ── toolbar skeletons ── */
.skel-toolbar-top {
  position: absolute;
  top: 16px;
  left: 16px;
  display: flex;
  gap: 8px;
  z-index: 10;
}

.skel-toolbar-right {
  position: absolute;
  top: 16px;
  right: 16px;
  z-index: 10;
}

.skel-toolbar-bottom {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
}

.skel-pill {
  height: 38px;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(51, 65, 85, 0.5);
  backdrop-filter: blur(8px);
  animation: skel-shimmer 2s ease-in-out infinite alternate;
}

.skel-pill-sq {
  height: 38px;
  width: 38px;
  border-radius: 12px;
  background: rgba(30, 41, 59, 0.8);
  border: 1px solid rgba(51, 65, 85, 0.5);
  backdrop-filter: blur(8px);
  animation: skel-shimmer 2s ease-in-out infinite alternate;
}

.skel-w-20 { width: 80px; }
.skel-w-24 { width: 96px; }
.skel-w-32 { width: 128px; }
.skel-w-36 { width: 144px; }

@keyframes skel-shimmer {
  0% { opacity: 0.5; }
  100% { opacity: 0.8; }
}

/* ── center card ── */
.skel-center {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
  padding: 24px;
}

.skel-card {
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(24px);
  border: 1px solid rgba(51, 65, 85, 0.6);
  border-radius: 20px;
  padding: 36px 40px 32px;
  max-width: 380px;
  width: 100%;
  box-shadow:
    0 0 0 1px rgba(16,185,129,0.05),
    0 8px 40px rgba(0,0,0,0.4),
    0 0 80px rgba(16,185,129,0.06);
  animation: skel-card-in 0.5s ease-out both;
}

@keyframes skel-card-in {
  0% { opacity: 0; transform: translateY(16px) scale(0.97); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* ── logo ── */
.skel-logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 16px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(16,185,129,0.15), rgba(59,130,246,0.1));
  border: 1px solid rgba(16,185,129,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}

.skel-logo-icon {
  color: #10b981;
  animation: skel-logo-pulse 2s ease-in-out infinite;
}

@keyframes skel-logo-pulse {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

/* ── typography ── */
.skel-title {
  text-align: center;
  font-size: 18px;
  font-weight: 700;
  color: #f1f5f9;
  margin: 0 0 4px;
  letter-spacing: -0.02em;
}

.skel-subtitle {
  text-align: center;
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  margin: 0 0 24px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* ── progress bar ── */
.skel-progress-track {
  position: relative;
  height: 4px;
  background: rgba(51, 65, 85, 0.5);
  border-radius: 4px;
  margin-bottom: 24px;
  overflow: visible;
}

.skel-progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, #10b981, #34d399);
  transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

.skel-progress-glow {
  position: absolute;
  top: -4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 12px 4px rgba(16,185,129,0.4);
  transform: translateX(-50%);
  transition: left 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── steps ── */
.skel-steps {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skel-step {
  display: flex;
  align-items: center;
  gap: 12px;
  opacity: 0.35;
  transition: opacity 0.4s ease;
}

.skel-step-done {
  opacity: 0.6;
}

.skel-step-active {
  opacity: 1;
}

.skel-step-icon {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: rgba(51, 65, 85, 0.4);
  color: #64748b;
  border: 1px solid rgba(51, 65, 85, 0.5);
  transition: all 0.4s ease;
}

.skel-step-icon.done {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  border-color: rgba(16, 185, 129, 0.3);
}

.skel-step-icon.active {
  background: rgba(16, 185, 129, 0.1);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.3);
  box-shadow: 0 0 8px rgba(16,185,129,0.2);
}

.skel-step-label {
  font-size: 13px;
  font-weight: 500;
  color: #94a3b8;
  flex: 1;
}

.skel-step-done .skel-step-label {
  color: #64748b;
}

.skel-step-active .skel-step-label {
  color: #e2e8f0;
}

.skel-step-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(16,185,129,0.2);
  border-top-color: #10b981;
  border-radius: 50%;
  animation: skel-spin 0.8s linear infinite;
  flex-shrink: 0;
}

@keyframes skel-spin {
  to { transform: rotate(360deg); }
}

/* ── responsive ── */
@media (max-width: 480px) {
  .skel-card {
    padding: 28px 24px 24px;
  }
  .skel-title { font-size: 16px; }
  .skel-step-label { font-size: 12px; }
}
`;

export default MapSkeleton;
