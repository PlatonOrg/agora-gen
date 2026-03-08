import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  importProvidersFrom
} from '@angular/core';

import { provideRouter } from '@angular/router';
import { routes } from './app.routes';

import {
  provideClientHydration,
  withEventReplay
} from '@angular/platform-browser';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';

import { NGX_MONACO_EDITOR_CONFIG } from 'ngx-monaco-editor-v2';
import { MarkdownModule } from 'ngx-markdown';
import { provideHighlightOptions } from 'ngx-highlightjs';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideClientHydration(withEventReplay()),
    provideAnimationsAsync(),

    {
      provide: NGX_MONACO_EDITOR_CONFIG,
      useValue: {
        baseUrl: 'monaco/vs'
      }
    },

    importProvidersFrom(
      MarkdownModule.forRoot()
    ),

    provideHighlightOptions({
      coreLibraryLoader: () => import('highlight.js/lib/core'),
      languages: {
        python: () => import('highlight.js/lib/languages/python'),
        javascript: () => import('highlight.js/lib/languages/javascript'),
        typescript: () => import('highlight.js/lib/languages/typescript'),
        java: () => import('highlight.js/lib/languages/java'),
        c: () => import('highlight.js/lib/languages/c'),
        cpp: () => import('highlight.js/lib/languages/cpp'),
        csharp: () => import('highlight.js/lib/languages/csharp'),
        css: () => import('highlight.js/lib/languages/css'),
        html: () => import('highlight.js/lib/languages/xml'),
        xml: () => import('highlight.js/lib/languages/xml'),
        json: () => import('highlight.js/lib/languages/json'),
        sql: () => import('highlight.js/lib/languages/sql'),
        bash: () => import('highlight.js/lib/languages/bash'),
        shell: () => import('highlight.js/lib/languages/shell'),
        plaintext: () => import('highlight.js/lib/languages/plaintext'),
      }
    })
  ]
};
