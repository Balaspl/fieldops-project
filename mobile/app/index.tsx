
import { useEffect, useState } from "react";
import { ImageBackground } from "react-native";
import { StatusBar } from "expo-status-bar";
import { Redirect } from "expo-router";
import { useAuthStore } from "../src/auth/authStore";

export default function IndexScreen() {
  const [isReady, setIsReady] = useState(false);

  const restoreSession = useAuthStore(
    (state) => state.restoreSession
  );
  const isAuthenticated = useAuthStore(
    (state) => state.isAuthenticated
  );
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    let mounted = true;
    let sessionRestored = false;
    let minimumSplashElapsed = false;

    const finishIfReady = () => {
      if (
        mounted &&
        sessionRestored &&
        minimumSplashElapsed
      ) {
        setIsReady(true);
      }
    };

    const splashTimer = setTimeout(() => {
      minimumSplashElapsed = true;
      finishIfReady();
    }, 1500);

    void restoreSession()
      .catch(() => undefined)
      .finally(() => {
        sessionRestored = true;
        finishIfReady();
      });

    return () => {
      mounted = false;
      clearTimeout(splashTimer);
    };
  }, [restoreSession]);

  if (!isReady) {
    return (
      <ImageBackground
        source={require("../assets/images/fieldops-splash.png")}
        resizeMode="cover"
        style={{
          flex: 1,
          backgroundColor: "#002A20",
        }}
        accessible
        accessibilityLabel="FieldOps Commander splash screen"
      >
        <StatusBar style="light" />
      </ImageBackground>
    );
  }

  if (
    isAuthenticated &&
    user?.role.toLowerCase() === "technician"
  ) {
    return <Redirect href="/(app)/dashboard" />;
  }

  return <Redirect href="/(auth)/login" />;
}
