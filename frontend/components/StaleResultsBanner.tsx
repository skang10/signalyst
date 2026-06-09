import Link from "next/link";

type Props = { sessionId: string; isStale: boolean };

export function StaleResultsBanner({ sessionId, isStale }: Props) {
  if (!isStale) return null;
  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs flex-shrink-0">
      <span className="text-amber-600">⚠</span>
      <span className="text-amber-700">Results from prior run — timeframe or sources have changed.</span>
      <Link
        href={`/sessions/${sessionId}/config`}
        className="text-amber-600 underline underline-offset-2 ml-1"
      >
        Go to Config →
      </Link>
    </div>
  );
}
