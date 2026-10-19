import type { ButtonHTMLAttributes, InputHTMLAttributes, PropsWithChildren, ReactNode } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import styles from "./primitives.module.css";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger"; loading?: boolean };
export function Button({ tone = "primary", loading, children, className = "", disabled, ...props }: ButtonProps) {
  return <button {...props} disabled={disabled || loading} className={`${styles.button} ${styles[tone]} ${className}`}>{loading ? "处理中..." : children}</button>;
}

export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; children: ReactNode }) {
  return <button {...props} aria-label={label} title={label} className={styles.iconButton}>{children}</button>;
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) { return <input {...props} className={`${styles.input} ${props.className || ""}`} />; }
export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) { return <textarea {...props} className={`${styles.input} ${styles.textarea} ${props.className || ""}`} />; }
export function Badge({ tone = "neutral", children }: PropsWithChildren<{ tone?: "neutral" | "success" | "warning" | "danger" }>) { return <span className={`${styles.badge} ${styles[tone]}`}>{children}</span>; }
export function Card({ children, className = "" }: PropsWithChildren<{ className?: string }>) { return <section className={`${styles.card} ${className}`}>{children}</section>; }
export function Skeleton({ lines = 3 }: { lines?: number }) { return <div className={styles.skeleton} aria-label="内容加载中" role="status">{Array.from({ length: lines }, (_, index) => <span key={index} />)}</div>; }
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) { return <section className={styles.state}><strong>{title}</strong><p>{description}</p>{action}</section>; }
export function ErrorState({ title = "无法加载内容", description, retry }: { title?: string; description: string; retry?: () => void }) { return <section className={styles.state} role="alert"><strong>{title}</strong><p>{description}</p>{retry && <Button tone="secondary" onClick={retry}>重试</Button>}</section>; }
export function PermissionState() { return <EmptyState title="无访问权限" description="当前角色没有执行此操作的权限，请联系组织管理员。" />; }

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel = "确认", onConfirm }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description: string; confirmLabel?: string; onConfirm: () => void }) {
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}><DialogPrimitive.Portal><DialogPrimitive.Overlay className={styles.overlay} /><DialogPrimitive.Content className={styles.dialog}><DialogPrimitive.Title>{title}</DialogPrimitive.Title><DialogPrimitive.Description>{description}</DialogPrimitive.Description><div className={styles.actions}><Button tone="secondary" onClick={() => onOpenChange(false)}>取消</Button><Button tone="danger" onClick={onConfirm}>{confirmLabel}</Button></div></DialogPrimitive.Content></DialogPrimitive.Portal></DialogPrimitive.Root>;
}

export function Tooltip({ label, children }: PropsWithChildren<{ label: string }>) { return <TooltipPrimitive.Provider><TooltipPrimitive.Root><TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger><TooltipPrimitive.Portal><TooltipPrimitive.Content className={styles.tooltip} sideOffset={6}>{label}</TooltipPrimitive.Content></TooltipPrimitive.Portal></TooltipPrimitive.Root></TooltipPrimitive.Provider>; }
