import { EmptyState, PageHeader } from "@/components/ui/states";

export const metadata = { title: "Work orders — SolarDoctor" };

export default function WorkOrdersPage() {
  return (
    <>
      <PageHeader
        eyebrow="Field operations"
        title="Work orders"
        sub="Track cleaning and repair jobs from dispatch to a yield-verified fix."
      />
      <EmptyState icon="wrench" title="No work orders yet">
        Work orders created from an alert or an inspection will be listed here with priority, assignee and due date, and verified against the yield recovered after the job.
      </EmptyState>
    </>
  );
}
