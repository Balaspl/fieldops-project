import React from 'react';
import { useMapLayers } from '../../hooks/useMapLayers';
import { MAP_TYPES, OVERLAYS } from '../../constants/mapLayers';
import { LayerButton } from './LayerButton';
import { MobileLayerSheet } from './MobileLayerSheet';
import * as Icons from 'lucide-react';

export const MapLayerControls: React.FC = () => {
  const {
    mapType,
    traffic,
    transit,
    bicycling,
    isMobileSheetOpen,
    setMapType,
    toggleTraffic,
    toggleTransit,
    toggleBicycling,
    setMobileSheetOpen,
  } = useMapLayers();

  const getIcon = (id: string) => {
    switch (id) {
      case 'roadmap':
        return Icons.Map;
      case 'satellite':
        return Icons.Globe;
      case 'terrain':
        return Icons.Mountain;
      case 'traffic':
        return Icons.Activity;
      case 'transit':
        return Icons.Navigation;
      case 'bicycling':
        return Icons.Bike;
      default:
        return Icons.Layers;
    }
  };

  return (
    <>
      {/* Desktop Layout - Horizontal Toolbar */}
      <div className="hidden xl:flex items-center gap-2 bg-white/95 backdrop-blur-md border border-slate-200/80 shadow-xl rounded-xl p-2 select-none">
        {/* Map Type Group */}
        <div className="flex items-center gap-1.5 px-1">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mr-2 pointer-events-none">
            Map Mode
          </span>
          {MAP_TYPES.map((type) => (
            <LayerButton
              key={type.id}
              active={mapType === type.id}
              onClick={() => setMapType(type.id)}
              icon={getIcon(type.id)}
              label={type.label}
              ariaLabel={type.ariaLabel}
              tooltip={type.tooltip}
              shortcutHint={type.shortcut}
            />
          ))}
        </div>

        {/* Vertical Divider */}
        <div className="h-6 w-px bg-slate-200 mx-1" />

        {/* Overlay Group */}
        <div className="flex items-center gap-1.5 px-1">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mr-2 pointer-events-none">
            Overlays
          </span>
          {OVERLAYS.map((overlay) => {
            const isActive =
              overlay.id === 'traffic'
                ? traffic
                : overlay.id === 'transit'
                ? transit
                : bicycling;

            const toggleFn =
              overlay.id === 'traffic'
                ? toggleTraffic
                : overlay.id === 'transit'
                ? toggleTransit
                : toggleBicycling;

            return (
              <LayerButton
                key={overlay.id}
                active={isActive}
                onClick={toggleFn}
                icon={getIcon(overlay.id)}
                label={overlay.label}
                ariaLabel={overlay.ariaLabel}
                tooltip={overlay.tooltip}
                shortcutHint={overlay.shortcut}
              />
            );
          })}
        </div>
      </div>

      {/* Mobile Layout - Floating Action Button & Bottom Sheet */}
      <div className="xl:hidden">
        <button
          onClick={() => setMobileSheetOpen(true)}
          aria-label="Map layers and settings"
          className="flex items-center justify-center bg-white text-slate-700 hover:bg-slate-50 border border-slate-200 shadow-lg rounded-full w-10 h-10 transition-all duration-200 active:scale-95 cursor-pointer"
        >
          <Icons.Layers className="w-5 h-5 text-slate-600" />
        </button>

        {/* Mobile bottom sheet */}
        <MobileLayerSheet
          isOpen={isMobileSheetOpen}
          onClose={() => setMobileSheetOpen(false)}
          mapType={mapType}
          traffic={traffic}
          transit={transit}
          bicycling={bicycling}
          setMapType={setMapType}
          toggleTraffic={toggleTraffic}
          toggleTransit={toggleTransit}
          toggleBicycling={toggleBicycling}
        />
      </div>
    </>
  );
};
export default MapLayerControls;
