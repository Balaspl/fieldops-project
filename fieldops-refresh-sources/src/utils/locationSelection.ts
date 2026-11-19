export type PickedServiceLocation = {
  address: string;
  latitude: number;
  longitude: number;
};

let pickedServiceLocation: PickedServiceLocation | null = null;

/** Store a map selection until the service-request form regains focus. */
export function setPickedServiceLocation(location: PickedServiceLocation): void {
  pickedServiceLocation = location;
}

/** Read and clear the pending map selection so it is only applied once. */
export function consumePickedServiceLocation(): PickedServiceLocation | null {
  const selection = pickedServiceLocation;
  pickedServiceLocation = null;
  return selection;
}
