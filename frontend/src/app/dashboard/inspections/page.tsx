import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "Inspections — SolarDoctor" };

export default function InspectionsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Photo diagnosis"
        title="Inspections"
        sub="Upload a panel photo to classify the soiling or damage, see the evidence behind the call, and cross-check it against telemetry."
      />
      <EmptyState icon="panel" title="No inspections yet">
        Photo inspections will appear here once a drone or phone image has been analysed. Each result lists the predicted class, confidence, severity and the alert it is linked to.
      </EmptyState>
    </>
  );
}
