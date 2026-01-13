// Conversion factors to base unit (meters)
const DISTANCE_TO_METERS = {
  m: 1,
  km: 1000,
  mi: 1609.344,
  ft: 0.3048,
  yd: 0.9144,
  in: 0.0254,
  cm: 0.01,
  mm: 0.001
};

export function convertDistance(value, from, to) {
  // Validate input
  if (typeof value !== 'number' || isNaN(value)) {
    throw new Error('Value must be a valid number');
  }

  // Handle same unit conversion
  if (from === to) {
    return value;
  }

  // Check if units are supported
  if (!DISTANCE_TO_METERS[from]) {
    throw new Error(`Unsupported distance unit: ${from}`);
  }
  if (!DISTANCE_TO_METERS[to]) {
    throw new Error(`Unsupported distance unit: ${to}`);
  }

  // Convert: from -> meters -> to
  const valueInMeters = value * DISTANCE_TO_METERS[from];
  return valueInMeters / DISTANCE_TO_METERS[to];
}
