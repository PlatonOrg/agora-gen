import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class FileValidationService {
  isExtensionAccepted(filename: string, acceptedExtensions: string[]): boolean {
    if (acceptedExtensions.length === 0) return true;
    const dot = filename.lastIndexOf('.');
    if (dot === -1) return false;
    const ext = filename.slice(dot).toLowerCase();
    return acceptedExtensions.includes(ext);
  }

  buildAcceptAttribute(acceptedExtensions: string[]): string {
    if (acceptedExtensions.length === 0) return '';
    return acceptedExtensions.join(',');
  }

  filterFiles(files: File[], acceptedExtensions: string[]): { accepted: File[]; rejected: File[] } {
    const accepted: File[] = [];
    const rejected: File[] = [];
    for (const file of files) {
      if (this.isExtensionAccepted(file.name, acceptedExtensions)) {
        accepted.push(file);
      } else {
        rejected.push(file);
      }
    }
    return { accepted, rejected };
  }
}

