import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "Map — SolarDoctor" };

export default function MapPage() {
  return (
    <>
      <PageHeader
        eyebrow="Site view"
        title="Map"
        sub="Plants, strings and panels coloured by their worst open issue."
      />
      <EmptyState icon="map" title="No mapped plants yet">
        Register a plant with coordinates to see it here. Panel-level faults appear once an inspection has been localised.
      </EmptyState>
    </>
  );
}
