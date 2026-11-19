import { useEffect, useRef } from "react";
import {
  View,
  Pressable,
  StyleSheet,
  PanResponder,
  Animated,
  useWindowDimensions,
} from "react-native";
import { Tabs, router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuthStore } from "../../src/auth/authStore";
import { colors } from "../../src/theme";
import FieldOpsMascot from "../../src/components/FieldOpsMascot";

const BUTTON_WIDTH = 76;
const BUTTON_HEIGHT = 82;
const BOTTOM_SAFE_SPACE = 100;

export default function CustomerTabsLayout() {
  const { initialized, user } = useAuthStore();
  const { width: screenWidth, height: screenHeight } =
    useWindowDimensions();

  const dragPosition = useRef(new Animated.ValueXY({ x: 0, y: 0 })).current;
  const lastPosition = useRef({ x: 0, y: 0 });
  const isDragging = useRef(false);

  // Keep current screen dimensions available to the gesture callbacks.
  const dimensions = useRef({ screenWidth, screenHeight });
  dimensions.current = { screenWidth, screenHeight };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,

      onMoveShouldSetPanResponder: (_, gesture) =>
        Math.abs(gesture.dx) > 5 || Math.abs(gesture.dy) > 5,

      onPanResponderGrant: () => {
        isDragging.current = false;
        dragPosition.setOffset(lastPosition.current);
        dragPosition.setValue({ x: 0, y: 0 });
      },

      onPanResponderMove: (_, gesture) => {
        if (Math.abs(gesture.dx) > 5 || Math.abs(gesture.dy) > 5) {
          isDragging.current = true;
        }

        dragPosition.setValue({
          x: gesture.dx,
          y: gesture.dy,
        });
      },

      onPanResponderRelease: (_, gesture) => {
        const { screenWidth: width, screenHeight: height } =
          dimensions.current;

        const currentX = lastPosition.current.x + gesture.dx;
        const currentY = lastPosition.current.y + gesture.dy;

        const corners = [
          {
            x: 0,
            y: 0,
          },
          {
            x: -(width - BUTTON_WIDTH - 24),
            y: 0,
          },
          {
            x: 0,
            y: -(height - BUTTON_HEIGHT - BOTTOM_SAFE_SPACE),
          },
          {
            x: -(width - BUTTON_WIDTH - 24),
            y: -(height - BUTTON_HEIGHT - BOTTOM_SAFE_SPACE),
          },
        ];

        const nearestCorner = corners.reduce((nearest, corner) => {
          const distance = Math.hypot(
            currentX - corner.x,
            currentY - corner.y,
          );

          const nearestDistance = Math.hypot(
            currentX - nearest.x,
            currentY - nearest.y,
          );

          return distance < nearestDistance ? corner : nearest;
        });

        lastPosition.current = nearestCorner;

        dragPosition.flattenOffset();
        dragPosition.setValue(nearestCorner);
      },

      onPanResponderTerminate: () => {
        dragPosition.flattenOffset();
        dragPosition.setValue(lastPosition.current);
      },
    }),
  ).current;

  useEffect(() => {
    if (initialized && !user) {
      router.replace("/(auth)/login");
    }
  }, [initialized, user]);

  return (
    <View style={styles.container}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.brand,
          tabBarInactiveTintColor: "#87938B",
          tabBarLabelStyle: {
            fontSize: 10,
            fontWeight: "700",
            marginBottom: 4,
          },
          tabBarStyle: {
            height: 65,
            paddingTop: 8,
            borderTopColor: colors.border,
            backgroundColor: "#FFFFFF",
          },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "Home",
            tabBarIcon: ({ color, size }) => (
              <Ionicons
                name="home-outline"
                color={color}
                size={size}
              />
            ),
          }}
        />

        <Tabs.Screen
          name="requests"
          options={{
            title: "Requests",
            tabBarIcon: ({ color, size }) => (
              <Ionicons
                name="clipboard-outline"
                color={color}
                size={size}
              />
            ),
          }}
        />

        <Tabs.Screen
          name="tracking"
          options={{ href: null }}
        />

        <Tabs.Screen
          name="account"
          options={{
            title: "Account",
            tabBarIcon: ({ color, size }) => (
              <Ionicons
                name="person-circle-outline"
                color={color}
                size={size}
              />
            ),
          }}
        />
      </Tabs>

      {initialized && user && (
        <Animated.View
          pointerEvents="box-none"
          style={[
            styles.chatbotButton,
            {
              transform: [
                { translateX: dragPosition.x },
                { translateY: dragPosition.y },
              ],
            },
          ]}
          {...panResponder.panHandlers}
        >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Open FieldOps Support chatbot"
            onPress={() => {
              console.log("FieldOps robot tapped");

              if (isDragging.current) {
                isDragging.current = false;
                return;
              }

              router.push({
                pathname: "/chatbot",
              });
            }}
            style={({ pressed }) => [
              styles.chatbotTouchable,
              pressed && styles.chatbotPressed,
            ]}
          >
            <FieldOpsMascot />
            <View style={styles.onlineDot} />
          </Pressable>
        </Animated.View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F5FAF7",
  },

  chatbotButton: {
    position: "absolute",
    right: 12,
    bottom: 78,
    width: BUTTON_WIDTH,
    height: BUTTON_HEIGHT,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
    elevation: 8,
    shadowColor: "#064E3B",
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.22,
    shadowRadius: 5,
  },

  chatbotTouchable: {
    width: "100%",
    height: "100%",
    alignItems: "center",
    justifyContent: "center",
  },

  onlineDot: {
    position: "absolute",
    top: 3,
    right: 6,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: "#22C55E",
    borderWidth: 2,
    borderColor: "#FFFFFF",
  },

  chatbotPressed: {
    opacity: 0.85,
  },
});


