import { useEffect } from 'react';
import { useMapLayersStore } from '../store/mapLayersStore';

export const useMapLayers = () => {
  const store = useMapLayersStore();

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Don't trigger shortcuts if user is typing in an input, textarea, or contentEditable element
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }

      const key = event.key.toLowerCase();

      if (key === 't') {
        event.preventDefault();
        store.toggleTraffic();
      } else if (key === 's') {
        event.preventDefault();
        store.setMapType('satellite');
      } else if (key === 'r') {
        event.preventDefault();
        store.setMapType('roadmap');
      } else if (event.key === 'Escape') {
        if (store.isMobileSheetOpen) {
          event.preventDefault();
          store.setMobileSheetOpen(false);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [store]);

  return store;
};
