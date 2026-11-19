
import { useEffect, useRef } from "react";
import {
  View,
  Pressable,
  StyleSheet,
  PanResponder,
  Animated,
  useWindowDimensions,
  BackHandler,
  Platform,
  ToastAndroid,
} from "react-native";
import { Tabs, router, usePathname } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuthStore } from "../../../src/customer/auth/authStore";
import { colors } from "../../../src/customer/theme";
import FieldOpsMascot from "../../../src/customer/components/FieldOpsMascot";

const BUTTON_WIDTH = 76;
const BUTTON_HEIGHT = 82;
const TAB_BAR_CONTENT_HEIGHT = 65;
const CHATBOT_GAP = 12;
const CHATBOT_SIDE_MARGIN = 12;

export default function CustomerTabsLayout() {
  const { initialized, user } = useAuthStore();
  const pathname = usePathname();

  const { width: screenWidth, height: screenHeight } =
    useWindowDimensions();

  const insets = useSafeAreaInsets();

  // Include Android/iOS system safe areas.
  const tabBarHeight = TAB_BAR_CONTENT_HEIGHT + insets.bottom;

  const dragPosition = useRef(
    new Animated.ValueXY({ x: 0, y: 0 }),
  ).current;

  const lastPosition = useRef({ x: 0, y: 0 });
  const isDragging = useRef(false);

  const dimensions = useRef({
    screenWidth,
    screenHeight,
    top: insets.top,
    bottom: insets.bottom,
    left: insets.left,
    right: insets.right,
    tabBarHeight,
  });

  dimensions.current = {
    screenWidth,
    screenHeight,
    top: insets.top,
    bottom: insets.bottom,
    left: insets.left,
    right: insets.right,
    tabBarHeight,
  };

  const getAllowedCorners = () => {
    const {
      screenWidth: width,
      screenHeight: height,
      top,
      left,
      right,
      tabBarHeight: currentTabBarHeight,
    } = dimensions.current;

    const sideMargin = CHATBOT_SIDE_MARGIN + right;

    const leftPosition = -(
      width -
      BUTTON_WIDTH -
      sideMargin -
      CHATBOT_SIDE_MARGIN -
      left
    );

    const bottomPosition =
      currentTabBarHeight + CHATBOT_GAP;

    const topPosition = -Math.max(
      0,
      height -
        BUTTON_HEIGHT -
        top -
        CHATBOT_GAP -
        bottomPosition,
    );

    return [
      { x: 0, y: 0 },
      { x: leftPosition, y: 0 },
      { x: 0, y: topPosition },
      { x: leftPosition, y: topPosition },
    ];
  };

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,

      onMoveShouldSetPanResponder: (_, gesture) =>
        Math.abs(gesture.dx) > 5 ||
        Math.abs(gesture.dy) > 5,

      onPanResponderGrant: () => {
        isDragging.current = false;
        dragPosition.setOffset(lastPosition.current);
        dragPosition.setValue({ x: 0, y: 0 });
      },

      onPanResponderMove: (_, gesture) => {
        if (
          Math.abs(gesture.dx) > 5 ||
          Math.abs(gesture.dy) > 5
        ) {
          isDragging.current = true;
        }

        dragPosition.setValue({
          x: gesture.dx,
          y: gesture.dy,
        });
      },

      onPanResponderRelease: (_, gesture) => {
        const currentX =
          lastPosition.current.x + gesture.dx;

        const currentY =
          lastPosition.current.y + gesture.dy;

        const corners = getAllowedCorners();

        const nearestCorner = corners.reduce(
          (nearest, corner) => {
            const distance = Math.hypot(
              currentX - corner.x,
              currentY - corner.y,
            );

            const nearestDistance = Math.hypot(
              currentX - nearest.x,
              currentY - nearest.y,
            );

            return distance < nearestDistance
              ? corner
              : nearest;
          },
        );

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
      router.replace("/login");
    }
  }, [initialized, user]);

  // Android hardware back handling.
  useEffect(() => {
    if (
      !user ||
      Platform.OS !== "android" ||
      pathname !== "/"
    ) {
      return;
    }

    let lastBackPress = 0;

    const subscription = BackHandler.addEventListener(
      "hardwareBackPress",
      () => {
        if (router.canGoBack()) return false;

        const now = Date.now();

        if (now - lastBackPress < 2000) {
          BackHandler.exitApp();
        } else {
          lastBackPress = now;
          ToastAndroid.show(
            "Press back again to exit",
            ToastAndroid.SHORT,
          );
        }

        return true;
      },
    );

    return () => subscription.remove();
  }, [user, pathname]);

  // Keep the chatbot inside the visible area after rotation
  // or a screen-size change.
  useEffect(() => {
    const corners = getAllowedCorners();

    const current = lastPosition.current;

    const nearestCorner = corners.reduce(
      (nearest, corner) => {
        const distance = Math.hypot(
          current.x - corner.x,
          current.y - corner.y,
        );

        const nearestDistance = Math.hypot(
          current.x - nearest.x,
          current.y - nearest.y,
        );

        return distance < nearestDistance
          ? corner
          : nearest;
      },
    );

    lastPosition.current = nearestCorner;
    dragPosition.setValue(nearestCorner);
  }, [
    screenWidth,
    screenHeight,
    insets.top,
    insets.bottom,
    insets.left,
    insets.right,
  ]);

  return (
    <View style={styles.container}>
      <Tabs
        backBehavior="fullHistory"
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
            height: tabBarHeight,
            paddingTop: 8,
            paddingBottom: insets.bottom,
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
              right: CHATBOT_SIDE_MARGIN + insets.right,
              bottom: tabBarHeight + CHATBOT_GAP,
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
              if (isDragging.current) {
                isDragging.current = false;
                return;
              }

              router.push("/customer/chatbot");
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
    width: BUTTON_WIDTH,
    height: BUTTON_HEIGHT,
    alignItems: "center",
    justifyContent: "center",
    zIndex: 100,
    elevation: 8,
    shadowColor: "#064E3B",
    shadowOffset: {
      width: 0,
      height: 3,
    },
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
