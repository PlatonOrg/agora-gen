import { Component, input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Message } from '../discussion.models';
import { AttachmentBadgesComponent } from '../attachment-badges/attachment-badges.component';
import { GenerationStepsComponent } from '../generation-steps/generation-steps.component';

@Component({
  selector: 'app-message-bubble',
  standalone: true,
  imports: [CommonModule, AttachmentBadgesComponent, GenerationStepsComponent],
  templateUrl: './message-bubble.component.html',
  styleUrl: './message-bubble.component.scss',
})
export class MessageBubbleComponent {
  message = input.required<Message>();
}


