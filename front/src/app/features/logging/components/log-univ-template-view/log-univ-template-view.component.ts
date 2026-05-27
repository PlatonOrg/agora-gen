import { Component, OnInit, signal, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ContextService } from '../../../workspace/services/context.service';
import { LogStatusViewComponent, LoadingState } from '../log-status-view/log-status-view.component';

interface TemplateCard {
  filename: string;
  content: string;
}

@Component({
  selector: 'app-log-univ-template-view',
  standalone: true,
  imports: [CommonModule, LogStatusViewComponent],
  templateUrl: './log-univ-template-view.component.html',
  styleUrl: './log-univ-template-view.component.scss',
})
export class LogUnivTemplateViewComponent implements OnInit {
  private readonly contextService = inject(ContextService);

  protected readonly templates = signal<TemplateCard[]>([]);
  protected readonly state = signal<LoadingState>('loading');
  protected readonly errorMessage = signal<string | null>(null);
  protected readonly expandedFilename = signal<string | null>(null);

  async ngOnInit(): Promise<void> {
    try {
      // Get list of template filenames
      const filenames = await this.contextService.getUnivTemplateList();
      
      if (filenames.length === 0) {
        this.state.set('success');
        return;
      }

      // Load content for each template
      const templateCards: TemplateCard[] = [];
      for (const filename of filenames) {
        try {
          const content = await this.contextService.getUnivTemplateContent(filename);
          templateCards.push({ filename, content });
        } catch (err) {
          console.error(`[LogUnivTemplateView] Failed to load template ${filename}:`, err);
          // Continue loading other templates
        }
      }

      this.templates.set(templateCards);
      this.state.set('success');
    } catch (err: unknown) {
      console.error('[LogUnivTemplateView] Error loading templates:', err);
      this.state.set('error');
      this.errorMessage.set(err instanceof Error ? err.message : 'Erreur inconnue');
    }
  }

  protected toggleExpand(filename: string): void {
    this.expandedFilename.set(this.expandedFilename() === filename ? null : filename);
  }

  protected getDisplayName(filename: string): string {
    // Remove .md extension and replace underscores with spaces
    return filename.replace(/\.md$/, '').replace(/_/g, ' ');
  }
}
