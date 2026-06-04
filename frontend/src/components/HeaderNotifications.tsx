/**
 * 헤더 팀 초대 알림 — pending 초대 수락/거절.
 */

import { useState, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { invitationsApi } from "../lib/api";

interface Invitation {
  id: string;
  team_id: string;
  team_name: string;
  invited_by_login: string;
  invited_by_name: string;
  status: string;
  created_at: string;
}

export default function HeaderNotifications() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const { data: invitations = [] } = useQuery<Invitation[]>({
    queryKey: ["invitations"],
    queryFn: () => invitationsApi.listMine().then((r) => r.data),
    refetchInterval: 60_000,
  });

  const accept = useMutation({
    mutationFn: (id: string) => invitationsApi.accept(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["invitations"] });
      void queryClient.invalidateQueries({ queryKey: ["teams"] });
      void queryClient.invalidateQueries({ queryKey: ["team-members"] });
    },
  });

  const decline = useMutation({
    mutationFn: (id: string) => invitationsApi.decline(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
  });

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const count = invitations.length;

  return (
    <div className="relative" ref={panelRef} data-testid="header-notifications">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded hover:bg-sidebar-hover text-notion-text-secondary"
        aria-label="팀 초대 알림"
      >
        <Bell size={18} />
        {count > 0 && (
          <span className="absolute top-0.5 right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center text-[10px] font-medium bg-red-500 text-white rounded-full">
            {count}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-80 bg-white border border-notion-border rounded-lg shadow-lg z-50">
          <div className="px-3 py-2 border-b border-notion-border text-sm font-medium text-notion-text">
            팀 초대
          </div>
          {invitations.length === 0 ? (
            <p className="px-3 py-4 text-sm text-notion-text-secondary text-center">
              새 초대가 없습니다
            </p>
          ) : (
            <ul className="max-h-64 overflow-y-auto">
              {invitations.map((inv) => (
                <li
                  key={inv.id}
                  className="px-3 py-3 border-b border-notion-border last:border-0"
                  data-testid={`notification-item-${inv.id}`}
                >
                  <p className="text-sm text-notion-text font-medium">{inv.team_name}</p>
                  <p className="text-xs text-notion-text-secondary mt-0.5">
                    {inv.invited_by_name || inv.invited_by_login}님이 초대했습니다
                  </p>
                  <div className="flex gap-2 mt-2">
                    <button
                      type="button"
                      onClick={() => accept.mutate(inv.id)}
                      disabled={accept.isPending}
                      className="flex-1 text-xs py-1.5 rounded bg-notion-text text-white hover:opacity-90 disabled:opacity-50"
                      data-testid={`accept-invite-${inv.id}`}
                    >
                      수락
                    </button>
                    <button
                      type="button"
                      onClick={() => decline.mutate(inv.id)}
                      disabled={decline.isPending}
                      className="flex-1 text-xs py-1.5 rounded border border-notion-border hover:bg-sidebar-hover disabled:opacity-50"
                      data-testid={`decline-invite-${inv.id}`}
                    >
                      거절
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
