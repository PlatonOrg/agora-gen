import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DiscussionGenerationDetail } from '../../models/log.model';
import { LogSectionComponent } from '../shared/log-section/log-section.component';
import { LogKvComponent } from '../shared/log-kv/log-kv.component';
import { LOG_ICONS } from '../../utils/log-icons';
import { fmtDateTime } from '../../utils/log-format.utils';

@Component({
  selector: 'app-discussion-generation-detail',
  standalone: true,
  imports: [CommonModule, LogSectionComponent, LogKvComponent],
  templateUrl: './discussion-generation-detail.component.html',
  styleUrls: ['../../logging.shared.scss', './discussion-generation-detail.component.scss'],
})
export class DiscussionGenerationDetailComponent {
  gen = input.required<DiscussionGenerationDetail>();
  protected readonly icons = LOG_ICONS;
  protected fmt(iso: string | null | undefined): string { return fmtDateTime(iso); }
}
