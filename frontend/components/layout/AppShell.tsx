"use client";

import React, { useState } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { ChatAssistant } from "@/components/chat/ChatAssistant";
import { ConnectionState, useTelemetryStream } from "@/lib/useTelemetryStream";

interface AppShellProps {
  children: React.ReactNode;
  openAlertsCount?: number;
  connectionState?: ConnectionState;
}

export function AppShell({
  children,
  openAlertsCount = 0,
  connectionState,
}: AppShellProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const telemetry = useTelemetryStream();

  return (
    <div className="flex min-h-screen w-full bg-transparent">
      {/* Sidebar Navigation */}
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0 overflow-x-hidden">
        <TopBar
          onMenuToggle={() => setSidebarOpen((prev) => !prev)}
          openAlertsCount={openAlertsCount}
          connectionState={connectionState ?? telemetry.connectionState}
        />
        <main className="flex-1 p-4 sm:p-10 lg:p-12 max-w-[112rem] w-full mx-auto animate-in-reveal">
          {children}
        </main>
      </div>

      {/* Persistent Floating AI Chat Assistant */}
      <ChatAssistant />
    </div>
  );
}
