import type { ReactNode } from "react";
import { PermissionState } from "../design-system/primitives";

export function AccessGuard({ allowed, children }: { allowed: boolean; children: ReactNode }) { return allowed ? <>{children}</> : <PermissionState />; }
