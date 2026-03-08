import { Component, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';

export type LogTab = 'conversations' | 'config';

interface NavItem { tab: LogTab; label: string; icon: string; }

@Component({
  selector: 'app-log-sidebar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './log-sidebar.component.html',
  styleUrl: './log-sidebar.component.scss',
})
export class LogSidebarComponent {
  activeTab = input.required<LogTab>();
  tabSelected = output<LogTab>();

  protected readonly navItems: NavItem[] = [
    {
      tab: 'conversations',
      label: 'Conversations',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>`,
    },
    {
      tab: 'config',
      label: 'Configuration',
      icon: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>`,
    },
  ];
}

