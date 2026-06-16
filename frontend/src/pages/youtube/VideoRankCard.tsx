import type { VideoResult } from "../../lib/m5Api";

type Props = {
  video: VideoResult;
  animationDelay?: number;
};

const RANK_EMOJI: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

function rankEmoji(rank: number): string {
  return RANK_EMOJI[rank] ?? "🏅";
}

export default function VideoRankCard({ video, animationDelay = 0 }: Props) {
  const queryKeywords = video.query_used
    .split(/\s+/)
    .filter(Boolean)
    .join("+");

  return (
    <a
      href={video.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex gap-3 p-3 rounded-lg border border-notion-border items-center bg-white hover:bg-notion-bg-secondary transition-colors"
      style={{ animation: `fadeSlideIn 0.4s ease both`, animationDelay: `${animationDelay}ms` }}
    >
      {video.thumbnail ? (
        <img
          src={video.thumbnail}
          alt=""
          className="w-28 h-16 object-cover rounded flex-shrink-0 bg-notion-bg-secondary"
        />
      ) : (
        <div className="w-28 h-16 flex-shrink-0 rounded bg-notion-bg-secondary items-center flex items-center justify-center text-2xl">
          ▶️
        </div>
      )}

      <div className="flex flex-col gap-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-base leading-none">{rankEmoji(video.rank)}</span>
          <span className="text-xs font-medium text-notion-text-secondary px-1.5 py-0.5 rounded bg-notion-bg-secondary">
            {video.recommendation_type}
          </span>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-notion-text-secondary/50 truncate max-w-[250px]">
            {queryKeywords}
          </span>
        </div>
        <p className="text-sm font-medium text-notion-text leading-snug line-clamp-2">
          {video.title}
        </p>
        {video.channel_title && (
          <p className="text-xs text-notion-text-secondary truncate">{video.channel_title}</p>
        )}
      </div>
    </a>
  );
}
