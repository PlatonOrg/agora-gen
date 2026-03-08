export type ExerciseStatus = 'DRAFT' | 'READY' | 'BUGGED' | 'NOT_TESTED';

export interface PublishFile {
  path: string;
  content: string;
}

export interface PublishExerciseRequest {
  name: string;
  parentId: string;
  templateId?: string | null;
  templateVersion?: string | null;
  code?: string | null;
  desc: string;
  type: 'EXERCISE';
  status: ExerciseStatus;
  levels: string[];
  topics: string[];
  files: PublishFile[];
}

export interface PublishExerciseResponse {
  id: string;
}

