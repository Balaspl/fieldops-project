import { superAdminApi } from "../../src/api/roleApis";
import { RoleList } from "../../src/components/RoleHome";
export default function Organizations() { return <RoleList title="Organizations" subtitle="Organizations available to platform administration" load={superAdminApi.organizations} />; }
