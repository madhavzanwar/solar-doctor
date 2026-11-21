import { PageHeader } from "@/components/ui/states";
import MapView from "@/components/map/MapView";

export const metadata = { title: "GIS Map & Drone Orthomosaics — SolarDoctor" };

export default function MapPage() {
  return (
    <>
      <PageHeader
        eyebrow="Site GIS & Aerial Remote Sensing"
        title="Gigawatt-Scale Orthomosaic GIS Viewer"
        sub="Sub-centimeter drone orthomosaic mapping, radiometric thermal IR, and real-time inverter station string telemetry."
      />
      <MapView />
    </>
  );
}
