import { Component } from '@angular/core';
@Component({
  selector: 'app-agora-logo',
  standalone: true,
  template: `
    <div class="logo-container">
      <img
        src="/agora_logo-removebg.png"
        alt="Agora Logo"
        class="logo-image"
      />
      <span class="logo-text">Agora</span>
    </div>
  `,
  styles: [`
    .logo-container {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-image {
      width: 56px;
      height: 56px;
      object-fit: contain;
    }
    .logo-text {
      font-size: 1.5rem;
      color: #171c8f;
      font-weight: 500;
    }
  `]
})
export class AgoraLogoComponent {}
