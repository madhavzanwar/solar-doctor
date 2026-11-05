import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Exports" title="Reports" />
      <LoadingState label="Loading reports…" />
    </>
  );
}
