import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Lock, Unlock } from "lucide-react";

/** T084: Toggle for locking/unlocking a preference's source text.
 *
 * When locked, the original text cannot be modified by the agent.
 * When unlocked, the agent can evolve the preference freely.
 */
export interface LockToggleProps {
  preferenceId: string;
  isActive: boolean;
  onToggle: (locked: boolean) => void;
  disabled?: boolean;
}

export function LockToggle({
  isActive,
  onToggle,
  disabled = false,
}: LockToggleProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [pendingAction, setPendingAction] = useState<boolean | null>(null);

  const handleClick = () => {
    const newState = !isActive;
    setPendingAction(newState);
    setShowConfirm(true);
  };

  const handleConfirm = () => {
    if (pendingAction !== null) {
      onToggle(pendingAction);
    }
    setShowConfirm(false);
    setPendingAction(null);
  };

  const handleCancel = () => {
    setShowConfirm(false);
    setPendingAction(null);
  };

  return (
    <>
      <Button
        variant={isActive ? "default" : "outline"}
        size="sm"
        onClick={handleClick}
        disabled={disabled}
        className="gap-1.5"
      >
        {isActive ? (
          <>
            <Lock className="h-3.5 w-3.5" />
            <span>已锁定</span>
          </>
        ) : (
          <>
            <Unlock className="h-3.5 w-3.5" />
            <span>未锁定</span>
          </>
        )}
      </Button>

      <Dialog open={showConfirm} onOpenChange={setShowConfirm}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {pendingAction ? "锁定偏好" : "解锁偏好"}
            </DialogTitle>
            <DialogDescription>
              {pendingAction
                ? "锁定后，Agent 将不再修改此偏好的原始文本。您可以随时解锁。"
                : "解锁后，Agent 可以根据新的交互自动更新此偏好规则。"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={handleCancel}>
              取消
            </Button>
            <Button onClick={handleConfirm}>
              {pendingAction ? "确认锁定" : "确认解锁"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
