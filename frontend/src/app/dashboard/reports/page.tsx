import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "Reports — SolarDoctor" };

export default function ReportsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Exports"
        title="Reports"
        sub="Generated PDF, Excel and GeoJSON reports for plants and inspections."
      />
      <EmptyState icon="report" title="No reports generated yet">
        Reports you generate for a plant and period are listed here with their type, size and creation time.
      </EmptyState>
    </>
  );
}
