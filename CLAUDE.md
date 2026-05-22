# Agora-Gen — Instructions pour Claude Code

## Projet

Pipeline de génération d'exercices PLaTon via LLM + RAG.
- **Backend** : Python 3.12, FastAPI, asyncio, LlamaIndex, SQLAlchemy async, Redis
- **Frontend** : Angular 20, TypeScript 5.8, SSR (Angular Universal)
- **Infrastructure** : Docker Compose, PostgreSQL + pgvector, Redis

---

## Principes généraux (toujours applicables)

- Ne jamais ajouter de code non demandé (abstractions prématurées, gestion d'erreurs inutile, feature flags)
- Ne pas écrire de commentaires qui expliquent CE QUE le code fait — seulement POURQUOI si c'est non-évident
- Préférer modifier un fichier existant plutôt qu'en créer un nouveau
- Pas d'emojis dans le code ni les fichiers sauf demande explicite

---

## SOLID — Application concrète dans ce projet

### S — Single Responsibility
Chaque classe/service a une seule raison de changer.
- `retrieval_service.py` : uniquement le retrieval RAG, pas la logique métier
- `generation_service.py` : uniquement les appels LLM, pas l'orchestration
- `workflow.py` : uniquement l'orchestration, pas la génération directe
- Un composant Angular gère un seul domaine fonctionnel (pas de composants "god")

### O — Open/Closed
Ouvert à l'extension, fermé à la modification.
- Les providers LLM héritent de `LLMProvider` — ajouter un provider = créer une classe, pas modifier les existantes
- Les composants PLaTon sont configurés dans `prompts_config_v3.json` — ajouter un composant = ajouter une entrée JSON

### L — Liskov Substitution
Tout `LLMProvider` concret doit être interchangeable sans casser le code appelant.
- Les providers (`Groq`, `Ragustave`, `Anthropic`, `Ollama`) doivent tous implémenter `chat_with_llm` et `wrap_json_schema` avec la même interface

### I — Interface Segregation
Ne pas forcer une classe à implémenter des méthodes qu'elle n'utilise pas.
- Séparer les interfaces de retrieval (`retrieve_templates` vs `retrieve_examples`) plutôt qu'une seule méthode générique

### D — Dependency Inversion
Dépendre des abstractions, pas des implémentations.
- Injecter `LLMProviderRegistry` plutôt qu'instancier directement un provider
- Angular : utiliser `inject()` plutôt que le constructeur pour les dépendances

---

## Python — Bonnes pratiques

### Typage
```python
# ✅ Toujours typer les signatures
async def retrieve_templates(query: str, limit: int = 5) -> list[NodeWithScore]:
    ...

# ✅ Utiliser les types modernes Python 3.10+
def process(items: list[str] | None = None) -> dict[str, Any]:
    ...

# ❌ Éviter
def process(items=None):
    ...
```

### Async
```python
# ✅ Paralléliser les appels indépendants
results = await asyncio.gather(
    retrieve_templates(enriched_query),
    retrieve_examples(simple_query),
    select_components(user_request),
)

# ❌ Séquentiel inutile
templates = await retrieve_templates(enriched_query)
examples = await retrieve_examples(simple_query)
components = await select_components(user_request)
```

### Dataclasses / Pydantic
```python
# ✅ Pydantic pour les modèles API (validation automatique)
class GenerationRequest(BaseModel):
    user_request: str
    niveaux: list[str] = []
    domaines: list[str] = []

# ✅ dataclass pour les objets internes simples
@dataclass
class RetrievalResult:
    node_id: str
    score: float
    kind: str
```

### Gestion d'erreurs
```python
# ✅ Lever des exceptions métier précises à la frontière système
# ✅ Logger avec contexte suffisant pour diagnostiquer
logger.error("Template retrieval failed: query=%s, error=%s", query, exc, exc_info=True)

# ❌ Attraper Exception trop large et ignorer
try:
    ...
except Exception:
    pass
```

### Structure fichiers backend
```
back/src/
  api/v1/          # Routeurs FastAPI (pas de logique métier ici)
  services/        # Logique métier (generation, retrieval, sandbox...)
  infra/           # Détails techniques (LLM, DB, vector store, cache)
  workflows/       # Orchestration inter-services
  core/            # Config, constantes, DI
```

### Règles spécifiques à ce projet
- **Les attributs PLaTon sont en anglais** : `title`, `statement`, `form`, `builder`, `grader`, `solution`
- Le LLM doit toujours générer des noms anglais — `_GENERATED_KEY_TO_ATTRIBUTE` fait le mapping
- `form`, `builder`, `grader`, `sandbox` partagent des bindings de variables → toujours générés par un seul appel LLM
- `prompts_config_v3.json` est indexé par tag de composant (`wc-checkbox-group`), pas par nom (`CheckboxGroup`)

---

## Angular 20 — Bonnes pratiques

### Signals (obligatoire pour tout nouveau code)

```typescript
// ✅ Signal pour l'état local
export class ExerciseListComponent {
  exercises = signal<Exercise[]>([]);
  isLoading = signal(false);
  
  // ✅ computed() pour les dérivations — jamais de getter impure
  filteredExercises = computed(() =>
    this.exercises().filter(e => e.status === 'active')
  );
  
  // ✅ effect() pour les side effects réactifs
  constructor() {
    effect(() => {
      document.title = `${this.exercises().length} exercices`;
    });
  }
}

// ❌ Éviter les propriétés mutables classiques pour l'état
exercises: Exercise[] = [];
```

### inject() — obligatoire pour les nouvelles dépendances

```typescript
// ✅ inject() en propriété de classe
export class GenerationService {
  private http = inject(HttpClient);
  private router = inject(Router);
  private authService = inject(AuthService);
}

// ❌ Constructeur à éviter pour les nouvelles classes
constructor(private http: HttpClient, private router: Router) {}
```

### Inputs/Outputs modernes (Angular 17.1+)

```typescript
// ✅ input() et output() — signal-based
export class ExerciseCardComponent {
  exercise = input.required<Exercise>();
  isSelected = input(false);
  
  selected = output<Exercise>();
  deleted = output<string>(); // id
  
  // ✅ model() pour le two-way binding
  value = model<string>('');
}

// ❌ @Input() / @Output() à ne plus utiliser pour le nouveau code
@Input() exercise!: Exercise;
@Output() selected = new EventEmitter<Exercise>();
```

### Nouvelle syntaxe de template (obligatoire)

```html
<!-- ✅ @if / @else -->
@if (isLoading()) {
  <app-spinner />
} @else if (exercises().length === 0) {
  <p>Aucun exercice</p>
} @else {
  <app-exercise-list [exercises]="exercises()" />
}

<!-- ✅ @for avec track obligatoire -->
@for (exercise of exercises(); track exercise.id) {
  <app-exercise-card [exercise]="exercise" />
}

<!-- ✅ @switch -->
@switch (status()) {
  @case ('loading') { <app-spinner /> }
  @case ('error') { <app-error [message]="error()" /> }
  @default { <app-content /> }
}

<!-- ❌ *ngIf, *ngFor, *ngSwitch obsolètes -->
<div *ngIf="isLoading">...</div>
```

### Services avec state réactif

```typescript
// ✅ Service avec signals exposés en lecture seule
@Injectable({ providedIn: 'root' })
export class ExerciseStore {
  private _exercises = signal<Exercise[]>([]);
  private _isLoading = signal(false);
  
  // Exposition en lecture seule
  readonly exercises = this._exercises.asReadonly();
  readonly isLoading = this._isLoading.asReadonly();
  readonly count = computed(() => this._exercises().length);
  
  async loadExercises(): Promise<void> {
    this._isLoading.set(true);
    try {
      const data = await firstValueFrom(this.http.get<Exercise[]>('/api/v1/exercises'));
      this._exercises.set(data);
    } finally {
      this._isLoading.set(false);
    }
  }
}
```

### HTTP et async

```typescript
// ✅ toSignal() pour convertir Observable → Signal
export class ExerciseListComponent {
  private exerciseService = inject(ExerciseService);
  
  exercises = toSignal(this.exerciseService.getExercises(), {
    initialValue: [],
  });
}

// ✅ resource() pour les données chargées (Angular 19+)
export class ExerciseDetailComponent {
  id = input.required<string>();
  
  exerciseResource = resource({
    request: () => ({ id: this.id() }),
    loader: ({ request }) => fetch(`/api/v1/exercises/${request.id}`).then(r => r.json()),
  });
}
```

### Routing

```typescript
// ✅ Routes avec lazy loading et resolve
export const routes: Routes = [
  {
    path: 'exercises',
    loadComponent: () => import('./features/workspace/workspace.component'),
    resolve: {
      exercises: () => inject(ExerciseStore).loadExercises(),
    },
  },
];
```

### Structure fichiers frontend

```
front/src/app/
  features/          # Domaines fonctionnels (workspace, auth, admin...)
    workspace/
      components/    # Composants de présentation
      pages/         # Smart components / pages
      services/      # Services locaux au feature
  core/              # Services singleton (auth, api, logging)
    api/             # Clients HTTP typés
    auth/            # Authentification
  shared/            # Composants/pipes/directives réutilisables
    ui/              # Composants UI génériques
    pipes/           # Pipes purs
```

### Règles de composants
- Composant = `standalone: true` (obligatoire, plus de NgModules)
- Utiliser `ChangeDetectionStrategy.OnPush` pour tous les nouveaux composants
- Un composant ne fait pas d'appels HTTP directement — il passe par un service
- Pas de logique métier dans les templates — utiliser `computed()`

---

## Git

- Commits en anglais, format `type: description` (`feat:`, `fix:`, `refactor:`, `chore:`)
- Pas de `--no-verify`
- PR vers `develop`, pas directement vers `main`

---

## Docker

- Le backend tourne dans le container `agora_backend`
- Les logs de debug sont dans `/tmp/agora_steps/` à l'intérieur du container
- Accès : `docker exec agora_backend cat /tmp/agora_steps/<fichier>`
- Rebuild du container après modification des dépendances Python
