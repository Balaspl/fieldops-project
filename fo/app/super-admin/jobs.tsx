import { superAdminApi } from "../../src/api/roleApis";
import { RoleList } from "../../src/components/RoleHome";
export default function Jobs() { return <RoleList title="Operations jobs" subtitle="Recent jobs across your organization" load={superAdminApi.jobs} />; }
