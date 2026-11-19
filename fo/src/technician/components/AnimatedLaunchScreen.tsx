import { useEffect, useRef, useState } from "react";
import {
  AccessibilityInfo,
  Animated,
  Easing,
  Image,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,

} from "react-native";
import { StatusBar } from "expo-status-bar";

interface AnimatedLaunchScreenProps {
  readyToExit: boolean;
  onExitComplete: () => void;
}

const COLORS = {
  background: "#003C30",
  secondary: "#087D51",
  lime: "#80F04B",
  white: "#F5FFF8"
};

export function AnimatedLaunchScreen({
  readyToExit,
  onExitComplete
}: AnimatedLaunchScreenProps) {
  const { width } = useWindowDimensions();
  const [reduceMotion, setReduceMotion] = useState(false);
  const [entranceComplete, setEntranceComplete] = useState(false);
  const glowOpacity = useRef(new Animated.Value(0)).current;
  const logoOpacity = useRef(new Animated.Value(0)).current;
  const logoScale = useRef(new Animated.Value(0.88)).current;
  const sweepOpacity = useRef(new Animated.Value(0)).current;
  const sweepX = useRef(new Animated.Value(-190)).current;
  const orbitOpacity = useRef(new Animated.Value(0)).current;
  const orbitRotation = useRef(new Animated.Value(0)).current;
  const wordmarkOpacity = useRef(new Animated.Value(0)).current;
  const wordmarkY = useRef(new Animated.Value(14)).current;
  const screenOpacity = useRef(new Animated.Value(1)).current;
  const exitStarted = useRef(false);
  const completionCalled = useRef(false);
  const logoFrame = Math.min(154, Math.max(128, width * 0.42));
  const orbitSize = logoFrame + 92;
  const orbitTurn = orbitRotation.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "360deg"]
  });

  useEffect(() => {
    let active = true;
    void AccessibilityInfo.isReduceMotionEnabled()
      .then((enabled) => {
        if (active) setReduceMotion(enabled);
      })
      .catch(() => undefined);

    const subscription = AccessibilityInfo.addEventListener(
      "reduceMotionChanged",
      setReduceMotion
    );
    return () => {
      active = false;
      subscription.remove();
    };
  }, []);

  useEffect(() => {
    let active = true;
    let orbitLoop: Animated.CompositeAnimation | undefined;

    if (reduceMotion) {
      glowOpacity.setValue(1);
      logoOpacity.setValue(1);
      logoScale.setValue(1);
      orbitOpacity.setValue(0.9);
      wordmarkOpacity.setValue(1);
      wordmarkY.setValue(0);
      setEntranceComplete(true);
      return () => {
        active = false;
      };
    }

    const sweep = Animated.sequence([
      Animated.timing(sweepOpacity, {
        toValue: 0.5,
        duration: 120,
        useNativeDriver: true
      }),
      Animated.timing(sweepX, {
        toValue: 190,
        duration: 620,
        easing: Easing.inOut(Easing.cubic),
        useNativeDriver: true
      }),
      Animated.timing(sweepOpacity, {
        toValue: 0,
        duration: 180,
        useNativeDriver: true
      })
    ]);

    const entrance = Animated.sequence([
      // Background glow reveal.
      Animated.timing(glowOpacity, {
        toValue: 1,
        duration: 760,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true
      }),
      // Logo reveal and a single restrained light pass.
      Animated.delay(140),
      Animated.parallel([
        Animated.timing(logoOpacity, {
          toValue: 1,
          duration: 760,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true
        }),
        Animated.timing(logoScale, {
          toValue: 1,
          duration: 820,
          easing: Easing.out(Easing.back(1.12)),
          useNativeDriver: true
        }),
        sweep
      ]),
      // Orbit enters after the logo has settled.
      Animated.delay(220),
      Animated.timing(orbitOpacity, {
        toValue: 1,
        duration: 500,
        easing: Easing.out(Easing.quad),
        useNativeDriver: true
      }),
      // Wordmark and descriptor reveal.
      Animated.delay(240),
      Animated.parallel([
        Animated.timing(wordmarkOpacity, {
          toValue: 1,
          duration: 650,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true
        }),
        Animated.timing(wordmarkY, {
          toValue: 0,
          duration: 650,
          easing: Easing.out(Easing.cubic),
          useNativeDriver: true
        })
      ]),
      Animated.delay(420)
    ]);

    orbitLoop = Animated.loop(
      Animated.timing(orbitRotation, {
        toValue: 1,
        duration: 2600,
        easing: Easing.linear,
        useNativeDriver: true
      })
    );

    const orbitTimer = setTimeout(() => {
      if (active) orbitLoop?.start();
    }, 1650);

    entrance.start(({ finished }) => {
      if (active && finished) setEntranceComplete(true);
    });

    return () => {
      active = false;
      clearTimeout(orbitTimer);
      entrance.stop();
      sweep.stop();
      orbitLoop?.stop();
    };
  }, [
    reduceMotion,
    glowOpacity,
    logoOpacity,
    logoScale,
    sweepOpacity,
    sweepX,
    orbitOpacity,
    orbitRotation,
    wordmarkOpacity,
    wordmarkY
  ]);

  useEffect(() => {
    if (!readyToExit || !entranceComplete || exitStarted.current) return;
    exitStarted.current = true;
    const exit = Animated.timing(screenOpacity, {
      toValue: 0,
      duration: reduceMotion ? 140 : 380,
      easing: Easing.inOut(Easing.quad),
      useNativeDriver: true
    });
    exit.start(({ finished }) => {
      if (finished && !completionCalled.current) {
        completionCalled.current = true;
        onExitComplete();
      }
    });
    return () => exit.stop();
  }, [
    readyToExit,
    entranceComplete,
    reduceMotion,
    screenOpacity,
    onExitComplete
  ]);

  return (
    <Animated.View
      onLayout={() => undefined}
      style={[styles.screen, { opacity: screenOpacity }]}
      accessible
      accessibilityRole="text"
      accessibilityLabel="FieldOps. Field service operations."
    >
      <StatusBar style="light" />

      <View pointerEvents="none" style={styles.glowField}>
        <Animated.View
          style={[
            styles.glowOuter,
            { opacity: Animated.multiply(glowOpacity, 0.045) }
          ]}
        />
        <Animated.View
          style={[
            styles.glowMiddle,
            { opacity: Animated.multiply(glowOpacity, 0.075) }
          ]}
        />
        <Animated.View
          style={[
            styles.glowInner,
            { opacity: Animated.multiply(glowOpacity, 0.1) }
          ]}
        />
      </View>

      <View style={styles.brandBlock}>
        <View
          style={[
            styles.logoStage,
            { width: orbitSize, height: orbitSize }
          ]}
        >
          <Animated.View
            pointerEvents="none"
            style={[
              styles.orbit,
              {
                width: orbitSize,
                height: orbitSize,
                borderRadius: orbitSize / 2,
                opacity: orbitOpacity,
                transform: [{ rotate: orbitTurn }]
              }
            ]}
          >
            <View style={styles.orbitPointHalo} />
            <View style={styles.orbitPoint} />
          </Animated.View>

          <Animated.View
            style={[
              styles.logoWindow,
              {
                width: logoFrame,
                height: logoFrame,
                opacity: logoOpacity,
                transform: [{ scale: logoScale }]
              }
            ]}
          >
            <Image
              source={require("../../assets/images/fieldops-logo.png")}
              resizeMode="stretch"
              style={[
                styles.logoCropImage,
                {
                  width: logoFrame * 2.985,
                  height: logoFrame,
                  left: -logoFrame * 0.22,
                  top: -logoFrame * 0.02
                }
              ]}
              accessible={false}
            />
            <Animated.View
              pointerEvents="none"
              style={[
                styles.lightSweep,
                {
                  opacity: sweepOpacity,
                  transform: [
                    { translateX: sweepX },
                    { rotate: "-24deg" }
                  ]
                }
              ]}
            />
          </Animated.View>
        </View>

        <Animated.View
          style={[
            styles.wordmarkBlock,
            {
              opacity: wordmarkOpacity,
              transform: [{ translateY: wordmarkY }]
            }
          ]}
        >
          <Text style={styles.wordmark}>
            <Text style={styles.wordmarkField}>Field</Text>
            <Text style={styles.wordmarkOps}>Ops</Text>
          </Text>
          <Text style={styles.tagline}>FIELD SERVICE OPERATIONS</Text>
          <View style={styles.taglineRule} />
        </Animated.View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerLabel}>SERVICE, IN MOTION</Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: COLORS.background,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden"
  },
  glowField: {
    ...StyleSheet.absoluteFill,
    alignItems: "center",
    justifyContent: "center",
    transform: [{ translateY: -28 }]
  },
  glowOuter: {
    position: "absolute",
    width: 430,
    height: 430,
    borderRadius: 215,
    backgroundColor: COLORS.lime
  },
  glowMiddle: {
    position: "absolute",
    width: 330,
    height: 330,
    borderRadius: 165,
    backgroundColor: COLORS.secondary
  },
  glowInner: {
    position: "absolute",
    width: 230,
    height: 230,
    borderRadius: 115,
    backgroundColor: COLORS.secondary
  },
  brandBlock: {
    alignItems: "center",
    justifyContent: "center",
    transform: [{ translateY: -18 }]
  },
  logoStage: {
    alignItems: "center",
    justifyContent: "center"
  },
  orbit: {
    position: "absolute",
    borderWidth: 1,
    borderColor: "rgba(128, 240, 75, 0.4)"
  },
  orbitPointHalo: {
    position: "absolute",
    width: 16,
    height: 16,
    borderRadius: 8,
    top: -8,
    left: "50%",
    marginLeft: -8,
    backgroundColor: "rgba(128, 240, 75, 0.22)"
  },
  orbitPoint: {
    position: "absolute",
    width: 6,
    height: 6,
    borderRadius: 3,
    top: -3,
    left: "50%",
    marginLeft: -3,
    backgroundColor: COLORS.lime,
    shadowColor: COLORS.lime,
    shadowOpacity: 0.8,
    shadowRadius: 8,
    elevation: 5
  },
  logoWindow: {
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center"
  },
  logoCropImage: {
    position: "absolute"
  },
  lightSweep: {
    position: "absolute",
    width: 42,
    height: "145%",
    top: "-22%",
    left: "50%",
    marginLeft: -21,
    backgroundColor: "rgba(245, 255, 248, 0.26)"
  },
  wordmarkBlock: {
    alignItems: "center",
    marginTop: 4
  },
  wordmark: {
    fontSize: 44,
    lineHeight: 52,
    letterSpacing: -1.8,
    fontWeight: "800"
  },
  wordmarkField: {
    color: COLORS.white
  },
  wordmarkOps: {
    color: COLORS.lime
  },
  tagline: {
    marginTop: 8,
    color: "rgba(245, 255, 248, 0.78)",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 3.2
  },
  taglineRule: {
    marginTop: 19,
    width: 38,
    height: 2,
    borderRadius: 1,
    backgroundColor: COLORS.lime
  },
  footer: {
    position: "absolute",
    bottom: 44,
    alignItems: "center"
  },
  footerLabel: {
    color: "rgba(245, 255, 248, 0.42)",
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 2.4
  }
});
