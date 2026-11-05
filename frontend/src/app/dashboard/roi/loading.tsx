import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Decisions in rupees" title="ROI" />
      <LoadingState label="Loading roi…" />
    </>
  );
}
