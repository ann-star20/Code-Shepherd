interface DashboardLayoutProps {
  header?: React.ReactNode;
  sidebar: React.ReactNode;
  main: React.ReactNode;
  inspector: React.ReactNode;
}

export function DashboardLayout({ header, sidebar, main, inspector }: DashboardLayoutProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#0b0b18] text-gray-100">
      {header && (
        <header className="shrink-0 border-b border-gray-800 bg-[#10101f] px-5 py-2.5">
          {header}
        </header>
      )}
      <div className="flex flex-1 overflow-hidden">
        <aside className="w-72 shrink-0 overflow-y-auto border-r border-gray-800 bg-[#10101f]">
          {sidebar}
        </aside>
        <main className="flex flex-1 flex-col overflow-hidden">
          {main}
        </main>
        <aside className="w-80 shrink-0 overflow-y-auto border-l border-gray-800 bg-[#10101f]">
          {inspector}
        </aside>
      </div>
    </div>
  );
}
