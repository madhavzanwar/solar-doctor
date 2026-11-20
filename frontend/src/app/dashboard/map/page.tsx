import { PageHeader } from "@/components/ui/states";
import MapView from "@/components/map/MapView";

export const metadata = { title: "Map — SolarDoctor" };

export default function MapPage() {
  return (
    <>
      <PageHeader
        eyebrow="Site view"
        title="Map"
        sub="Plants coloured by their worst open alert; open a plant for its panels and tracked faults."
      />
      <MapView />
    </>
  );
}
