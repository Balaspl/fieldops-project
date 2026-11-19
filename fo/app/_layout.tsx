
import { useCallback, useState } from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { StyleSheet, View } from "react-native";

import { AnimatedLaunchScreen } from "../src/components/AnimatedLaunchScreen";

export default function RootLayout() {
  const [splashVisible, setSplashVisible] = useState(true);

  const handleSplashExit = useCallback(() => {
    setSplashVisible(false);
  }, []);

  return (
    <View style={styles.container}>
      <StatusBar style={splashVisible ? "light" : "dark"} />

      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: {
            backgroundColor: "#F4F8F6",
          },
        }}
      />

      {splashVisible && (
        <View style={styles.splashOverlay}>
          <AnimatedLaunchScreen
            readyToExit={true}
            onExitComplete={handleSplashExit}
          />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  splashOverlay: {
    ...StyleSheet.absoluteFill,
    zIndex: 999,
    elevation: 999,
  },
});
