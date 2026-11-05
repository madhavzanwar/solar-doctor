import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Field operations" title="Work orders" />
      <LoadingState label="Loading work orders…" />
    </>
  );
}
