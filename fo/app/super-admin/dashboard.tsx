import StaffShell from "../../src/super-admin/components/StaffShell";
import { AuthProvider } from "../../src/super-admin/auth/AuthContext";
export default function SuperAdminDashboard() { return <AuthProvider><StaffShell /></AuthProvider>; }
