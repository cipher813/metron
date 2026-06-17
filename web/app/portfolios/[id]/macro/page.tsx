import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

// The standalone Macro page was retired (metron-ops#64) — macro indicators now live at the
// top of the Overview dashboard. Kept as a redirect so old links/bookmarks still resolve.
export default function MacroRedirect({ params }: { params: { id: string } }) {
  redirect(`/portfolios/${params.id}`);
}
