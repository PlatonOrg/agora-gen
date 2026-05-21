import { Component, computed, input, output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ExerciseVariant } from '../../../models/exercise.model';

@Component({
  selector: 'app-exercise-variants-picker',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './exercise-variants-picker.component.html',
  styleUrls: ['./exercise-variants-picker.component.scss'],
})
export class ExerciseVariantsPickerComponent {
  variants = input<ExerciseVariant[]>([]);

  variantSelected = output<ExerciseVariant>();
  variantPreviewed = output<string>();

  successfulVariants = computed(() => this.variants().filter(v => !v.error));
  failedVariants = computed(() => this.variants().filter(v => !!v.error));

  select(variant: ExerciseVariant): void {
    this.variantSelected.emit(variant);
  }

  preview(variant: ExerciseVariant): void {
    if (variant.url) {
      this.variantPreviewed.emit(variant.url);
      window.open(variant.url, '_blank');
    }
  }

  failedNames = computed(() => this.failedVariants().map(v => v.component_name).join(', '));

  truncate(text: string | undefined, max = 110): string {
    if (!text) return '';
    return text.length > max ? text.slice(0, max) + '…' : text;
  }
}
