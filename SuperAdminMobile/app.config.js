const base = require('./app.json').expo;

module.exports = ({ config }) => {
  return {
    ...base,
    ...config,
    name: 'FieldOps Staff',
    slug: 'fieldops-staff',
    plugins: ['expo-secure-store'],
    extra: { ...(base.extra || {}), ...(config.extra || {}) },
  };
};
