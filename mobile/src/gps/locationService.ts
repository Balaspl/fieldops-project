
import * as Location from "expo-location";

export interface TechnicianLocation {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  capturedAt: string;
}

export async function requestLocationPermission(): Promise<boolean> {
  const permission = await Location.requestForegroundPermissionsAsync();
  return permission.status === "granted";
}

export async function getCurrentTechnicianLocation(): Promise<TechnicianLocation> {
  const hasPermission = await requestLocationPermission();

  if (!hasPermission) {
    throw new Error(
      "Location permission was denied. Enable location access in your device settings."
    );
  }

  const location = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.Balanced
  });

  return {
    latitude: location.coords.latitude,
    longitude: location.coords.longitude,
    accuracy: location.coords.accuracy,
    capturedAt: new Date(location.timestamp).toISOString()
  };
}
