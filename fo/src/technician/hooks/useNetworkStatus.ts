import { useEffect, useState } from "react";
import * as Network from "expo-network";

type ExpoNetworkState = Awaited<
  ReturnType<typeof Network.getNetworkStateAsync>
>;

export interface NetworkStatus {
  isConnected: boolean | null;
  isInternetReachable: boolean | null;
  isOffline: boolean;
  isLoading: boolean;
  type: string | null;
}

const INITIAL_NETWORK_STATUS: NetworkStatus = {
  isConnected: null,
  isInternetReachable: null,
  isOffline: false,
  isLoading: true,
  type: null
};

function toNetworkStatus(
  networkState: ExpoNetworkState
): NetworkStatus {
  const isConnected = networkState.isConnected ?? null;
  const isInternetReachable =
    networkState.isInternetReachable ?? null;

  return {
    isConnected,
    isInternetReachable,
    isOffline:
      isConnected === false ||
      isInternetReachable === false,
    isLoading: false,
    type: networkState.type ?? null
  };
}

export function useNetworkStatus(): NetworkStatus {
  const [status, setStatus] = useState<NetworkStatus>(
    INITIAL_NETWORK_STATUS
  );

  useEffect(() => {
    let isMounted = true;
    let hasReceivedNetworkEvent = false;

    const subscription = Network.addNetworkStateListener(
      (networkState) => {
        hasReceivedNetworkEvent = true;

        if (!isMounted) {
          return;
        }

        setStatus(toNetworkStatus(networkState));
      }
    );

    void Network.getNetworkStateAsync()
      .then((networkState) => {
        if (!isMounted || hasReceivedNetworkEvent) {
          return;
        }

        setStatus(toNetworkStatus(networkState));
      })
      .catch(() => {
        if (!isMounted || hasReceivedNetworkEvent) {
          return;
        }

        setStatus({
          ...INITIAL_NETWORK_STATUS,
          isLoading: false
        });
      });

    return () => {
      isMounted = false;
      subscription.remove();
    };
  }, []);

  return status;
}