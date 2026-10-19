import type { ComponentProps } from "react";
import { DataView } from "../../components/DataView";
import { OrganizationCenter } from "./OrganizationCenter";

type Props = ComponentProps<typeof OrganizationCenter>;
export function OrganizationAuditPage(props: Props) {
  return <DataView kicker="ORG / ACCESS CONTROL" title="组织与审计" copy="成员、邀请、配额和审计都在同一个清晰的组织控制中心。"><OrganizationCenter {...props} /></DataView>;
}
