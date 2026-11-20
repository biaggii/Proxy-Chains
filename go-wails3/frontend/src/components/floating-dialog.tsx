import { useEffect, useRef, useState } from "react";
import { Grip, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";

type Point = { x: number; y: number };
type Size = { width: number; height: number | null };
type Gesture = {
  kind: "move" | "resize";
  pointerId: number;
  startX: number;
  startY: number;
  origin: Point;
  size: { width: number; height: number };
};

interface FloatingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  className?: string;
  initialWidth: number;
  minWidth: number;
  minHeight?: number;
  children: React.ReactNode;
}

export function FloatingDialog({ open, onOpenChange, title, description, className, initialWidth, minWidth, minHeight = 360, children }: FloatingDialogProps) {
  const popupRef = useRef<HTMLDivElement>(null);
  const gestureRef = useRef<Gesture | null>(null);
  const [position, setPosition] = useState<Point>({ x: 0, y: 0 });
  const [size, setSize] = useState<Size>({ width: initialWidth, height: null });

  useEffect(() => {
    if (!open) return;
    const viewportWidth = Math.max(280, window.innerWidth - 40);
    setPosition({ x: 0, y: 0 });
    setSize({ width: Math.min(initialWidth, viewportWidth), height: null });
    gestureRef.current = null;
    requestAnimationFrame(() => {
      if (popupRef.current) {
        popupRef.current.scrollTop = 0;
        const body = popupRef.current.querySelector<HTMLElement>(".floating-dialog-body");
        if (body) body.scrollTop = 0;
      }
    });
  }, [open, initialWidth]);

  useEffect(() => {
    if (!open) return;
    const move = (event: PointerEvent) => {
      const gesture = gestureRef.current;
      const popup = popupRef.current;
      if (!gesture || !popup || gesture.pointerId !== event.pointerId) return;
      const width = popup.offsetWidth;
      const height = popup.offsetHeight;
      if (gesture.kind === "move") {
        const baseX = (window.innerWidth - width) / 2;
        const baseY = (window.innerHeight - height) / 2;
        const minX = 20 - baseX;
        const maxX = window.innerWidth - width - 20 - baseX;
        const minY = 20 - baseY;
        const maxY = window.innerHeight - height - 20 - baseY;
        setPosition({
          x: Math.max(minX, Math.min(maxX, gesture.origin.x + event.clientX - gesture.startX)),
          y: Math.max(minY, Math.min(maxY, gesture.origin.y + event.clientY - gesture.startY)),
        });
      } else {
        const maxWidth = Math.max(280, window.innerWidth - 40);
        const maxHeight = Math.max(240, window.innerHeight - 40);
        const nextWidth = Math.max(Math.min(minWidth, maxWidth), Math.min(maxWidth, gesture.size.width + event.clientX - gesture.startX));
        const nextHeight = Math.max(Math.min(minHeight, maxHeight), Math.min(maxHeight, gesture.size.height + event.clientY - gesture.startY));
        setSize({ width: nextWidth, height: nextHeight });
        const baseX = (window.innerWidth - nextWidth) / 2;
        const baseY = (window.innerHeight - nextHeight) / 2;
        setPosition((current) => ({
          x: Math.max(20 - baseX, Math.min(window.innerWidth - nextWidth - 20 - baseX, current.x)),
          y: Math.max(20 - baseY, Math.min(window.innerHeight - nextHeight - 20 - baseY, current.y)),
        }));
      }
    };
    const stop = (event: PointerEvent) => {
      if (gestureRef.current?.pointerId === event.pointerId) gestureRef.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [open, minWidth, minHeight]);

  const beginGesture = (kind: Gesture["kind"]) => (event: React.PointerEvent<HTMLElement>) => {
    if (kind === "move" && (event.target as HTMLElement).closest("button")) return;
    const popup = popupRef.current;
    if (!popup) return;
    event.preventDefault();
    gestureRef.current = {
      kind,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origin: position,
      size: { width: popup.offsetWidth, height: popup.offsetHeight },
    };
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        ref={popupRef}
        className={`floating-dialog ${className ?? ""}`}
        showCloseButton={false}
        style={{
          width: size.width,
          height: size.height ?? "auto",
          minWidth: Math.min(minWidth, Math.max(280, window.innerWidth - 40)),
          minHeight: size.height === null ? undefined : Math.min(minHeight, Math.max(240, window.innerHeight - 40)),
          maxWidth: "calc(100vw - 40px)",
          maxHeight: "calc(100dvh - 40px)",
          transform: `translate(${position.x}px, ${position.y}px)`,
        }}
      >
        <div className="floating-dialog-header" onPointerDown={beginGesture("move")}>
          <div className="floating-dialog-heading">
            <DialogTitle>{title}</DialogTitle>
            {description && <DialogDescription>{description}</DialogDescription>}
          </div>
          <div className="floating-dialog-controls">
            <Grip className="floating-dialog-drag-icon" size={16} aria-hidden="true" />
            <DialogClose render={<Button type="button" variant="ghost" size="icon" aria-label="Close dialog" />}><X size={17} /></DialogClose>
          </div>
        </div>
        <div className="floating-dialog-body">{children}</div>
        <button type="button" className="floating-dialog-resize" onPointerDown={beginGesture("resize")} aria-label="Resize dialog" title="Drag to resize"><Grip size={14} /></button>
      </DialogContent>
    </Dialog>
  );
}
