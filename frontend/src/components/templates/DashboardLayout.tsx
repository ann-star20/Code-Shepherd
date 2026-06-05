interface DashboardLayoutProps {
  sidebar: React.ReactNode;
  main: React.ReactNode;
  inspector: React.ReactNode;
}

export function DashboardLayout({ sidebar, main, inspector }: DashboardLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <aside className="w-60 shrink-0 overflow-y-auto border-r bg-white">
        {sidebar}
      </aside>
      <main className="flex flex-1 flex-col overflow-y-auto p-4">
        {main}
      </main>
      <aside className="w-80 shrink-0 overflow-y-auto border-l bg-white">
        {inspector}
      </aside>
    </div>
  );
}
