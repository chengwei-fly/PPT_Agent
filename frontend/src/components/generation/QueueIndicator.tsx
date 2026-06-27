import { Card, CardContent } from "@/components/ui/card";

interface Props {
  position: number;
}

/** Persistent queue position indicator (FR-029 / SC-014). */
export function QueueIndicator({ position }: Props) {
  return (
    <Card className="border-yellow-200 bg-yellow-50 dark:border-yellow-800 dark:bg-yellow-950">
      <CardContent className="flex items-center gap-3 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-yellow-200 dark:bg-yellow-800">
          <span className="text-sm font-bold text-yellow-800 dark:text-yellow-200">
            {position}
          </span>
        </div>
        <div>
          <div className="text-sm font-medium">排队等待中</div>
          <div className="text-xs text-muted-foreground">
            您在队列第 {position} 位，预计等待 {Math.max(1, position * 3)} 分钟
          </div>
        </div>
        <div className="ml-auto">
          <div className="h-2 w-32 rounded-full bg-yellow-200 dark:bg-yellow-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-yellow-500 transition-all duration-1000"
              style={{ width: `${Math.max(10, 100 - position * 15)}%` }}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
