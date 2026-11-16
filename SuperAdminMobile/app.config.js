const base = require('./app.json').expo;

module.exports = ({ config }) => {
  const googleMapsKey = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || '';
  const plugins = [
    'expo-secure-store',
    ['react-native-maps', { androidGoogleMapsApiKey: googleMapsKey }],
  ];

  return {
    ...base,
    ...config,
    name: 'FieldOps Staff',
    slug: 'fieldops-staff',
    plugins,
    android: {
      ...base.android,
      ...config.android,
      config: { ...(base.android?.config || {}), ...(config.android?.config || {}), googleMaps: { apiKey: googleMapsKey } },
    },
    extra: { ...(base.extra || {}), ...(config.extra || {}) },
  };
};
