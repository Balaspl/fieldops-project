import { superAdminApi } from "../../src/api/roleApis";
import { RoleList } from "../../src/components/RoleHome";
export default function Users() { return <RoleList title="Technicians" subtitle="Staff records available to your account" load={superAdminApi.users} />; }
