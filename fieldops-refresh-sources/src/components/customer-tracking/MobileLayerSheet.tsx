import React from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { MapTypeId, MAP_TYPES, OVERLAYS } from '../../constants/mapLayers';
import { LayerButton } from './LayerButton';
import * as Icons from 'lucide-react';

interface MobileLayerSheetProps {
  isOpen: boolean;
  onClose: () => void;
  mapType: MapTypeId;
  traffic: boolean;
  transit: boolean;
  bicycling: boolean;
  setMapType: (type: MapTypeId) => void;
  toggleTraffic: () => void;
  toggleTransit: () => void;
  toggleBicycling: () => void;
}

export const MobileLayerSheet: React.FC<MobileLayerSheetProps> = ({
  isOpen,
  onClose,
  mapType,
  traffic,
  transit,
  bicycling,
  setMapType,
  toggleTraffic,
  toggleTransit,
  toggleBicycling,
}) => {
  // Map icon names from string to Lucide components
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
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[9999] md:hidden">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="absolute inset-0 bg-black"
          />

          {/* Bottom Sheet */}
          <motion.div
            initial={{ y: '100%' }}
            animate={{ y: 0 }}
            exit={{ y: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 220 }}
            drag="y"
            dragConstraints={{ top: 0 }}
            dragElastic={0.2}
            onDragEnd={(_, info) => {
              // If dragged down enough, close it
              if (info.velocity.y > 300 || info.offset.y > 100) {
                onClose();
              }
            }}
            className="absolute bottom-0 left-0 right-0 bg-white rounded-t-2xl shadow-2xl p-6 pb-8 border-t border-slate-150 select-none touch-pan-y"
          >
            {/* Drag Handle */}
            <div className="w-12 h-1.5 bg-slate-200 rounded-full mx-auto mb-6" />

            <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 text-center">
              Map Settings & Layers
            </h3>

            {/* 2x3 Grid of Buttons */}
            <div className="grid grid-cols-2 gap-4 max-w-sm mx-auto justify-items-center">
              {/* Map Types */}
              {MAP_TYPES.map((type) => (
                <LayerButton
                  key={type.id}
                  active={mapType === type.id}
                  onClick={() => setMapType(type.id)}
                  icon={getIcon(type.id)}
                  label={type.label}
                  ariaLabel={type.ariaLabel}
                  tooltip={type.tooltip}
                />
              ))}

              {/* Overlays */}
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
                  />
                );
              })}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
