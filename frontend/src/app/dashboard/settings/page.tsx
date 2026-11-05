import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "Settings — SolarDoctor" };

export default function SettingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        sub="Tariffs, cleaning cost, alert thresholds and users."
      />
      <EmptyState icon="gear" title="Nothing to configure yet">
        Tariff, cleaning-cost and threshold settings will be editable here for each plant.
      </EmptyState>
    </>
  );
}
