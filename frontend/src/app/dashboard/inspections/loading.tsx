import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Photo diagnosis" title="Inspections" />
      <LoadingState label="Loading inspections…" />
    </>
  );
}
