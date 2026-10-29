import { useLocalSearchParams } from "expo-router";
import ServiceRequestForm from "../../../src/components/ServiceRequestForm";
export default function EditServiceRequestRoute() {
  const params = useLocalSearchParams<{ requestId: string }>();
  const id = Number(params.requestId);
  if (!Number.isSafeInteger(id) || id <= 0) return <ServiceRequestForm />;
  return <ServiceRequestForm requestId={id} />;
}
