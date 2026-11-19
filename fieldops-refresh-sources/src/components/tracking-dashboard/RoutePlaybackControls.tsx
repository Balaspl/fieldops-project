import React, { useEffect } from 'react';
import { useRoutePlaybackStore } from '../../store/routePlaybackStore';

export const RoutePlaybackControls: React.FC = () => {
  const {
    activeTechId,
    activeTechName,
    historyPoints,
    currentProgress,
    isPlaying,
    playbackSpeed,
    dateRange,
    loading,
    error,
    play,
    pause,
    reset,
    setPlaybackSpeed,
    setProgress,
    setDateRange,
    loadHistory,
    exitPlayback,
    getDistanceTravelled,
    getElapsedTime,
  } = useRoutePlaybackStore();

  // Smooth playhead animation tick at 60fps using requestAnimationFrame
  useEffect(() => {
    if (!isPlaying || historyPoints.length < 2) return;

    let lastTime = performance.now();
    let frameId: number;

    const tick = (now: number) => {
      const deltaMs = now - lastTime;
      lastTime = now;

      // Complete entire track replay in 30 seconds at 1x speed
      const baseDurationSeconds = 30;
      const indexIncrement =
        (historyPoints.length / (baseDurationSeconds * 60)) *
        playbackSpeed *
        (deltaMs / 16.67);

      const nextProgress = Math.min(historyPoints.length - 1, currentProgress + indexIncrement);
      setProgress(nextProgress);

      if (nextProgress >= historyPoints.length - 1) {
        pause();
      } else {
        frameId = requestAnimationFrame(tick);
      }
    };

    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [isPlaying, historyPoints, playbackSpeed, currentProgress, setProgress, pause]);

  // Keyboard accessibility triggers
  useEffect(() => {
    if (!activeTechId) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        if (isPlaying) pause();
        else play();
      } else if (e.code === 'ArrowRight') {
        setProgress(Math.min(historyPoints.length - 1, currentProgress + 1));
      } else if (e.code === 'ArrowLeft') {
        setProgress(Math.max(0, currentProgress - 1));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTechId, isPlaying, currentProgress, historyPoints.length, play, pause, setProgress]);

  if (!activeTechId) return null;

  const handleGPXExport = () => {
    if (historyPoints.length === 0) return;
    const name = activeTechName || 'Technician';
    const gpxHeader = `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="FieldOps Commander" xmlns="http://www.topografix.com/GPX/1/1">\n  <trk>\n    <name>${name} Route History</name>\n    <trkseg>`;
    const trkpts = historyPoints
      .map(
        (p) =>
          `      <trkpt lat="${p.latitude}" lon="${p.longitude}">\n        <time>${p.timestamp}</time>\n      </trkpt>`
      )
      .join('\n');
    const gpxFooter = `    </trkseg>\n  </trk>\n</gpx>`;

    const data = `${gpxHeader}\n${trkpts}\n${gpxFooter}`;
    const blob = new Blob([data], { type: 'application/gpx+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${name.replace(/\s+/g, '_')}_route_history.gpx`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const handleKMLExport = () => {
    if (historyPoints.length === 0) return;
    const name = activeTechName || 'Technician';
    const kmlHeader = `<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n  <Document>\n    <name>${name} Route History</name>\n    <Placemark>\n      <name>Path</name>\n      <LineString>\n        <coordinates>`;
    const coords = historyPoints.map((p) => `          ${p.longitude},${p.latitude},0`).join('\n');
    const kmlFooter = `        </coordinates>\n      </LineString>\n    </Placemark>\n  </Document>\n</kml>`;

    const data = `${kmlHeader}\n${coords}\n${kmlFooter}`;
    const blob = new Blob([data], { type: 'application/vnd.google-earth.kml+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${name.replace(/\s+/g, '_')}_route_history.kml`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const currentPercent =
    historyPoints.length > 1 ? (currentProgress / (historyPoints.length - 1)) * 100 : 0;

  return (
    <div className="absolute inset-0 pointer-events-none z-[1000] flex flex-col justify-between p-4 font-sans">
      {/* Top Bar HUD: Counters (Top-Left) and Date Range + Exit Actions (Top-Right) */}
      <div className="flex flex-col md:flex-row justify-between items-start gap-4 w-full">
        {/* Distance & Elapsed Time Counters */}
        <div className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 rounded-xl p-4 text-white shadow-2xl pointer-events-auto flex items-center gap-6 min-w-[280px]">
          <div>
            <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
              Distance Travelled
            </div>
            <div className="text-2xl font-extrabold text-blue-400">
              {getDistanceTravelled()} <span className="text-sm font-medium">km</span>
            </div>
          </div>
          <div className="h-8 w-[1px] bg-slate-700/50" />
          <div>
            <div className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
              Elapsed Time
            </div>
            <div className="text-2xl font-extrabold text-green-400 font-mono">
              {getElapsedTime()}
            </div>
          </div>
        </div>

        {/* Date Filter & Control actions */}
        <div className="bg-slate-900/90 backdrop-blur-md border border-slate-700/50 rounded-xl p-3 text-white shadow-2xl pointer-events-auto flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">Start:</span>
            <input
              type="datetime-local"
              value={dateRange.start}
              onChange={(e) => setDateRange(e.target.value, dateRange.end)}
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-400">End:</span>
            <input
              type="datetime-local"
              value={dateRange.end}
              onChange={(e) => setDateRange(dateRange.start, e.target.value)}
              className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={exitPlayback}
            className="bg-red-600 hover:bg-red-700 active:bg-red-800 px-3 py-1.5 rounded-lg text-xs font-bold transition-all border border-red-500 shadow-md"
          >
            Exit Replay
          </button>
        </div>
      </div>

      {/* Main Playback HUD Panel (Bottom Center) */}
      <div className="w-full flex justify-center mt-auto">
        <div className="w-full max-w-4xl bg-slate-900/90 backdrop-blur-md border border-slate-700/50 rounded-2xl p-4 md:p-5 text-white shadow-2xl pointer-events-auto flex flex-col gap-4">
          
          {/* Header Info */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
              <h3 className="font-bold text-sm tracking-wide text-slate-200">
                Route Replay: <span className="text-blue-400 font-extrabold">{activeTechName}</span>
              </h3>
            </div>
            {historyPoints.length > 0 && (
              <span className="text-xs text-slate-400">
                Loaded {historyPoints.length} coordinates
              </span>
            )}
          </div>

          {/* Loading, Empty, and Error States */}
          {loading && (
            <div className="flex items-center justify-center py-6 gap-2">
              <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 border-t-transparent" />
              <span className="text-sm text-slate-400 font-medium">Loading routes history...</span>
            </div>
          )}

          {error && (
            <div className="flex flex-col items-center justify-center py-6 gap-2 border border-red-900/50 bg-red-950/20 rounded-xl">
              <p className="text-xs text-red-400 font-medium">{error}</p>
              <button
                onClick={loadHistory}
                className="bg-red-800 hover:bg-red-700 px-3 py-1 rounded text-xs font-bold transition"
              >
                Retry
              </button>
            </div>
          )}

          {!loading && !error && historyPoints.length === 0 && (
            <div className="flex items-center justify-center py-6 text-slate-400 text-sm font-medium">
              No route history logs found for this date range.
            </div>
          )}

          {/* Timeline and Playback Controls (Visible only when history is loaded) */}
          {historyPoints.length > 0 && !loading && !error && (
            <>
              {/* Timeline Scrubber */}
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={historyPoints.length - 1}
                  step={0.01}
                  value={currentProgress}
                  onChange={(e) => setProgress(parseFloat(e.target.value))}
                  aria-label="Route playback timeline slider scrubber"
                  className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500 hover:accent-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
              </div>

              {/* Controls bar */}
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-1">
                {/* Play / Pause / Reset Controls */}
                <div className="flex items-center gap-2">
                  {isPlaying ? (
                    <button
                      onClick={pause}
                      className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-4 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow"
                    >
                      ⏸️ Pause
                    </button>
                  ) : (
                    <button
                      onClick={play}
                      className="bg-blue-600 hover:bg-blue-500 border border-blue-500 px-4 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-md"
                    >
                      ▶️ Play
                    </button>
                  )}
                  <button
                    onClick={reset}
                    className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-4 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow"
                  >
                    🔁 Reset
                  </button>
                </div>

                {/* Speed Controls (1x, 2x, 4x) */}
                <div className="flex items-center gap-1 bg-slate-800/80 p-1 border border-slate-700/50 rounded-lg">
                  {([1, 2, 4] as const).map((speed) => (
                    <button
                      key={speed}
                      onClick={() => setPlaybackSpeed(speed)}
                      className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                        playbackSpeed === speed
                          ? 'bg-blue-600 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      {speed}x
                    </button>
                  ))}
                </div>

                {/* GPX & KML Exporters */}
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleGPXExport}
                    className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow"
                  >
                    📥 GPX
                  </button>
                  <button
                    onClick={handleKMLExport}
                    className="bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1 shadow"
                  >
                    📥 KML
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
