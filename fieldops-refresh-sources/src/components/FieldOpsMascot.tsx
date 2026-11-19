import { useEffect, useRef } from "react";
import {
  Animated,
  Easing,
  StyleSheet,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

export default function FieldOpsMascot() {
  const float = useRef(new Animated.Value(0)).current;
  const wave = useRef(new Animated.Value(0)).current;
  const feet = useRef(new Animated.Value(0)).current;
  const antenna = useRef(new Animated.Value(1)).current;
  const sway = useRef(new Animated.Value(0)).current;

  useEffect(() => {

    const swayAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(sway, {
          toValue: 1,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(sway, {
          toValue: -1,
          duration: 700,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );

    const floatingAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(float, {
          toValue: -4,
          duration: 850,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(float, {
          toValue: 2,
          duration: 850,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );

    const wavingAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(wave, {
          toValue: 1,
          duration: 380,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(wave, {
          toValue: -0.2,
          duration: 380,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.delay(250),
      ]),
    );

    const feetAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(feet, {
          toValue: 1,
          duration: 420,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
        Animated.timing(feet, {
          toValue: 0,
          duration: 420,
          easing: Easing.inOut(Easing.sin),
          useNativeDriver: true,
        }),
      ]),
    );

    const antennaAnimation = Animated.loop(
      Animated.sequence([
        Animated.timing(antenna, {
          toValue: 1.3,
          duration: 650,
          useNativeDriver: true,
        }),
        Animated.timing(antenna, {
          toValue: 1,
          duration: 650,
          useNativeDriver: true,
        }),
      ]),
    );


    swayAnimation.start();
    floatingAnimation.start();
    wavingAnimation.start();
    feetAnimation.start();
    antennaAnimation.start();

    return () => {
      swayAnimation.stop();
      floatingAnimation.stop();
      wavingAnimation.stop();
      feetAnimation.stop();
      antennaAnimation.stop();
    };
  }, [float, wave, feet, antenna, sway]);


  const swayRotation = sway.interpolate({
    inputRange: [-1, 1],
    outputRange: ["-4deg", "4deg"],
  });

  const wavingRotation = wave.interpolate({
    inputRange: [-0.2, 1],
    outputRange: ["-12deg", "-58deg"],
  });

  const leftLegRotation = feet.interpolate({
    inputRange: [0, 1],
    outputRange: ["-10deg", "12deg"],
  });

  const rightLegRotation = feet.interpolate({
    inputRange: [0, 1],
    outputRange: ["12deg", "-10deg"],
  });

  return (

    <Animated.View
      accessible
      accessibilityLabel="Animated FieldOps support robot"
      style={[
        styles.robot,
        {
          transform: [
            { translateY: float },
            { rotate: swayRotation },
          ],
        },
      ]}
    >

      {/* Antenna */}
      <View style={styles.antennaStem} />
      <Animated.View
        style={[
          styles.antennaBall,
          { transform: [{ scale: antenna }] },
        ]}
      />

      {/* Raised waving arm — pivots from the shoulder */}
        <Animated.View
        style={[
            styles.rightArmPivot,
            { transform: [{ rotate: wavingRotation }] },
        ]}
        >
        <View style={styles.rightArmSegment} />
        <View style={styles.rightHand} />
        </Animated.View>

      {/* Other arm */}
      <View style={styles.leftArm}>
        <View style={styles.hand} />
      </View>

      {/* Head */}
      <View style={styles.head}>
        <View style={styles.headShine} />
        <View style={styles.leftEar} />
        <View style={styles.rightEar} />

        <View style={styles.face}>
          <View style={styles.eyes}>
            <View style={styles.eye} />
            <View style={styles.eye} />
          </View>
          <View style={styles.smile} />
        </View>
      </View>

      {/* Body and gear emblem */}
      <View style={styles.body}>
        <View style={styles.chestScreen}>
          <Ionicons
            name="settings"
            size={16}
            color="#147568"
          />
        </View>
      </View>

      {/* Animated legs */}
      <Animated.View
        style={[
          styles.leftLeg,
          { transform: [{ rotate: leftLegRotation }] },
        ]}
      >
        <View style={styles.shoe} />
      </Animated.View>

      <Animated.View
        style={[
          styles.rightLeg,
          { transform: [{ rotate: rightLegRotation }] },
        ]}
      >
        <View style={styles.shoe} />
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  robot: {
    width: 64,
    height: 76,
    alignItems: "center",
    justifyContent: "flex-start",
  },

  antennaStem: {
    position: "absolute",
    top: 3,
    width: 3,
    height: 9,
    borderRadius: 2,
    backgroundColor: "#C9FFF4",
  },

  antennaBall: {
    position: "absolute",
    top: 0,
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: "#FFD36E",
    borderWidth: 1.5,
    borderColor: "#FFFFFF",
    zIndex: 5,
  },

  head: {
    position: "absolute",
    top: 11,
    width: 43,
    height: 32,
    borderRadius: 12,
    backgroundColor: "#8FE4BE",
    borderWidth: 1.5,
    borderColor: "#D0FFE9",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 3,
    elevation: 3,
  },

  headShine: {
    position: "absolute",
    top: 3,
    width: 24,
    height: 5,
    borderRadius: 4,
    backgroundColor: "#C8F6DF",
  },

  face: {
    width: 29,
    height: 16,
    marginTop: 5,
    borderRadius: 7,
    backgroundColor: "#145B53",
    alignItems: "center",
    justifyContent: "center",
  },

  eyes: {
    flexDirection: "row",
    gap: 9,
    alignItems: "center",
  },

  eye: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: "#94FFF0",
  },

  smile: {
    position: "absolute",
    bottom: 2,
    width: 8,
    height: 3,
    borderBottomWidth: 1.5,
    borderColor: "#6DDAC0",
    borderRadius: 5,
  },

  leftEar: {
    position: "absolute",
    left: -5,
    top: 10,
    width: 5,
    height: 12,
    borderRadius: 3,
    backgroundColor: "#66C8B6",
  },

  rightEar: {
    position: "absolute",
    right: -5,
    top: 10,
    width: 5,
    height: 12,
    borderRadius: 3,
    backgroundColor: "#66C8B6",
  },

  body: {
    position: "absolute",
    top: 43,
    width: 29,
    height: 24,
    borderRadius: 9,
    backgroundColor: "#55C594",
    borderWidth: 1.5,
    borderColor: "#D0FFE9",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 2,
  },

  chestScreen: {
    width: 20,
    height: 19,
    borderRadius: 7,
    backgroundColor: "#E8FFF5",
    borderWidth: 1.5,
    borderColor: "#B6F1D7",
    alignItems: "center",
    justifyContent: "center",
  },

  leftArm: {
    position: "absolute",
    left: 7,
    top: 42,
    width: 8,
    height: 17,
    borderRadius: 5,
    backgroundColor: "#55C594",
    transform: [{ rotate: "32deg" }],
    zIndex: 1,
  },

rightArmPivot: {
  position: "absolute",
  right: 10,
  top: 33,
  width: 7,
  height: 22,
  alignItems: "center",
  zIndex: 4,
},

rightArmSegment: {
  position: "absolute",
  top: 0,
  width: 7,
  height: 17,
  borderRadius: 5,
  backgroundColor: "#55C594",
},

rightHand: {
  position: "absolute",
  top: -5,
  right: -3,
  width: 10,
  height: 10,
  borderRadius: 5,
  backgroundColor: "#A8F0CE",
  borderWidth: 1,
  borderColor: "#D0FFE9",
},

  hand: {
    position: "absolute",
    bottom: -3,
    left: -2,
    width: 10,
    height: 10,
    borderRadius: 5,
    backgroundColor: "#A8F0CE",
    borderWidth: 1,
    borderColor: "#D0FFE9",
    },

  leftLeg: {
    position: "absolute",
    top: 63,
    left: 23,
    width: 6,
    height: 10,
    borderRadius: 4,
    backgroundColor: "#55C594",
    zIndex: 1,
  },

  rightLeg: {
    position: "absolute",
    top: 63,
    right: 23,
    width: 6,
    height: 10,
    borderRadius: 4,
    backgroundColor: "#55C594",
    zIndex: 1,
  },

  shoe: {
    position: "absolute",
    bottom: -1,
    left: -4,
    width: 13,
    height: 6,
    borderRadius: 5,
    backgroundColor: "#49B985",
  },
});
