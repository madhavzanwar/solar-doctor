import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "ROI — SolarDoctor" };

export default function RoiPage() {
  return (
    <>
      <PageHeader
        eyebrow="Decisions in rupees"
        title="ROI"
        sub="Clean now, wait, field check or replace, with the recoverable kWh and rupees behind each call."
      />
      <EmptyState icon="droplet" title="No decisions to show yet">
        Once a plant has a measured deficit and a tariff, each string gets a recoverable kWh and rupee estimate and a recommended action.
      </EmptyState>
    </>
  );
}
