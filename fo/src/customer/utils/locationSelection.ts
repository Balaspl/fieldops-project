export type PickedServiceLocation = {
  address: string;
  latitude: number;
  longitude: number;
};

export type PickedRegistrationLocation = {
  address: string;
  latitude: number;
  longitude: number;
};

let pickedServiceLocation: PickedServiceLocation | null = null;
let pickedRegistrationLocation: PickedRegistrationLocation | null = null;

/** Store a map selection until the service-request form regains focus. */
export function setPickedServiceLocation(location: PickedServiceLocation): void {
  pickedServiceLocation = location;
}

/** Read and clear the pending service selection so it is only applied once. */
export function consumePickedServiceLocation(): PickedServiceLocation | null {
  const selection = pickedServiceLocation;
  pickedServiceLocation = null;
  return selection;
}

/** Store a map selection until the customer registration screen regains focus. */
export function setPickedRegistrationLocation(
  location: PickedRegistrationLocation,
): void {
  pickedRegistrationLocation = location;
}

/** Read and clear the pending registration selection so it is only applied once. */
export function consumePickedRegistrationLocation(): PickedRegistrationLocation | null {
  const selection = pickedRegistrationLocation;
  pickedRegistrationLocation = null;
  return selection;
}
