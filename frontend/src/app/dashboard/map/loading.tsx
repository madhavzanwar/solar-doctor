import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Site view" title="Map" />
      <LoadingState label="Loading map…" />
    </>
  );
}
