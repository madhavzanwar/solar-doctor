import { LoadingState, PageHeader } from "@/components/ui/states";

export default function Loading() {
  return (
    <>
      <PageHeader eyebrow="Configuration" title="Settings" />
      <LoadingState label="Loading settings…" />
    </>
  );
}
