export type MapTypeId = 'roadmap' | 'satellite' | 'terrain';

export interface MapTypeOption {
  id: MapTypeId;
  label: string;
  shortcut: string;
  ariaLabel: string;
  tooltip: string;
}

export interface OverlayOption {
  id: 'traffic' | 'transit' | 'bicycling';
  label: string;
  ariaLabel: string;
  tooltip: string;
  shortcut?: string;
}

export const MAP_TYPES: MapTypeOption[] = [
  {
    id: 'roadmap',
    label: 'Roadmap',
    shortcut: 'R',
    ariaLabel: 'Switch to Roadmap view',
    tooltip: 'Show standard street map (Press R)',
  },
  {
    id: 'satellite',
    label: 'Satellite',
    shortcut: 'S',
    ariaLabel: 'Switch to Satellite view',
    tooltip: 'Show satellite imagery (Press S)',
  },
  {
    id: 'terrain',
    label: 'Terrain',
    shortcut: '',
    ariaLabel: 'Switch to Terrain view',
    tooltip: 'Show street map with terrain',
  },
];

export const OVERLAYS: OverlayOption[] = [
  {
    id: 'traffic',
    label: 'Traffic',
    shortcut: 'T',
    ariaLabel: 'Toggle traffic layer',
    tooltip: 'Show real-time traffic conditions (Press T)',
  },
  {
    id: 'transit',
    label: 'Transit',
    ariaLabel: 'Toggle public transit layer',
    tooltip: 'Show public transit routes',
  },
  {
    id: 'bicycling',
    label: 'Bicycling',
    ariaLabel: 'Toggle bicycling trails',
    tooltip: 'Show bicycle paths and lanes',
  },
];
