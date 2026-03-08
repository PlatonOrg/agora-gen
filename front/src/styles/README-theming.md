# Système de Theming Agora

Ce projet utilise un système de variables CSS centralisé basé sur les conventions de theming de **PLaTon**.

## Architecture

### 1. Variables CSS centrales (`src/styles/_css-variables.scss`)

Définit toutes les variables CSS avec support automatique des thèmes clair (`.light-theme`) et sombre (`.dark-theme`).

### 2. Styles globaux (`src/styles.scss`)

- Importe les variables CSS
- Applique les styles de base (reset, scrollbars, etc.)
- Configure les transitions de thème

### 3. Overrides (`src/styles/_overrides.scss`)

- Override des composants Material Design
- Override des composants ng-zorro (si utilisés)
- Styles communs réutilisables

## Variables principales

| Variable                        | Usage                                   |
| ------------------------------- | --------------------------------------- |
| `--brand-color-primary`         | Couleur principale de la marque         |
| `--brand-color-secondary`       | Couleur secondaire (boutons, liens)     |
| `--brand-color-tertiary`        | Couleur tertiaire (gradients)           |
| `--brand-background-components` | Arrière-plan des composants/cartes      |
| `--brand-background-primary`    | Arrière-plan principal de la page       |
| `--brand-background-secondary`  | Arrière-plan secondaire (headers, etc.) |
| `--brand-background-hover`      | État hover                              |
| `--brand-background-card`       | Arrière-plan des cartes                 |
| `--brand-background-dialog`     | Arrière-plan des modales                |
| `--brand-text-primary`          | Texte principal                         |
| `--brand-text-secondary`        | Texte secondaire                        |
| `--brand-text-tertiary`         | Texte tertiaire (placeholder, hints)    |
| `--brand-text-disabled`         | Texte désactivé                         |
| `--brand-border-color`          | Couleur des bordures                    |
| `--brand-font`                  | Police de caractères                    |

### Variables de statut

| Variable            | Usage                    |
| ------------------- | ------------------------ |
| `--brand-success`   | Couleur de succès        |
| `--brand-warning`   | Couleur d'avertissement  |
| `--brand-error`     | Couleur d'erreur         |
| `--brand-info`      | Couleur d'information    |

### Variables d'ombre

| Variable            | Usage                    |
| ------------------- | ------------------------ |
| `--brand-shadow-sm` | Ombre légère             |
| `--brand-shadow-md` | Ombre moyenne            |
| `--brand-shadow-lg` | Ombre prononcée          |
| `--brand-shadow-xl` | Ombre très prononcée     |

## Utilisation du thème

### Dans les composants Angular

```scss
.mon-composant {
  background-color: var(--brand-background-components);
  color: var(--brand-text-primary);
  border: 1px solid var(--brand-border-color);
}

.mon-bouton {
  background: linear-gradient(135deg, var(--brand-color-secondary) 0%, var(--brand-color-tertiary) 100%);
  color: var(--brand-color-secondary-contrast);
  box-shadow: var(--brand-shadow-sm);
}
```

### Changer de thème

Le `ThemeService` gère le changement de thème :

```typescript
import { ThemeService } from './services/theme.service';

// Basculer le thème
themeService.toggleTheme();

// Définir un thème spécifique
themeService.setTheme('dark');
themeService.setTheme('light');

// Vérifier le thème actuel
const isDark = themeService.isDarkMode();
```

### Classes CSS de thème

Le système applique automatiquement les classes sur `<html>` :

- `.light-theme` : Thème clair (par défaut)
- `.dark-theme` : Thème sombre

## Comment modifier une couleur

1. Ouvrir `src/styles/_css-variables.scss`
2. Modifier la variable dans `.light-theme` et/ou `.dark-theme`
3. Modifier également dans `:root` si nécessaire
4. La couleur sera automatiquement appliquée partout

## Avantages

✅ **Une seule source de vérité** : Toutes les couleurs dans `_css-variables.scss`
✅ **Thèmes automatiques** : Switch clair/sombre via classe CSS
✅ **Cohérence avec PLaTon** : Mêmes conventions de nommage
✅ **Transitions fluides** : Changement de thème animé
✅ **Maintenance facile** : Changer une couleur dans un seul endroit

## Compatibilité avec PLaTon

Ce système est conçu pour être compatible avec le système de theming de PLaTon, permettant une intégration future transparente.

