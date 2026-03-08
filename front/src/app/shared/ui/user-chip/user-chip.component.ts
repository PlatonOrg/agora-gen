import { Component, input, computed } from '@angular/core';
import { PlatonUser } from '../../../core/auth/user.model';

@Component({
  selector: 'app-user-chip',
  standalone: true,
  templateUrl: './user-chip.component.html',
  styleUrl: './user-chip.component.scss',
})
export class UserChipComponent {
  readonly profile = input.required<PlatonUser>();

  protected readonly initials = computed<string>(() => {
    const p = this.profile();
    const f = (p.firstName ?? '').trim();
    const l = (p.lastName ?? '').trim();
    if (f && l) return (f[0] + l[0]).toUpperCase();
    if (f) return f.substring(0, 2).toUpperCase();
    return p.username.substring(0, 2).toUpperCase();
  });

  protected readonly displayName = computed<string>(() => {
    const p = this.profile();
    const f = (p.firstName ?? '').trim();
    const l = (p.lastName ?? '').trim();
    return [f, l].filter(Boolean).join(' ') || p.username;
  });
}

