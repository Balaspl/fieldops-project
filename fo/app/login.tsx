
import { Redirect } from "expo-router";
import LoginScreen from "../src/auth/screens/LoginScreen";
import { useAuthStore } from "../src/auth/authStore";

export default function Login() {
  const user = useAuthStore((state) => state.user);

  if (user) {
    return <Redirect href="/" />;
  }

  return <LoginScreen />;
}
