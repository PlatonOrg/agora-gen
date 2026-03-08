export interface FilterTemplatesRequest {
  cercle: string; // circle ID
  sujets: string[]; // topic IDs
  niveaux: string[]; // level IDs
  composants?: string[]; // component tags
  search?: string; // search query
}

export interface TemplateResponse {
  id: string;
  name: string;
  description: string;
  config_variables: any;
  compil_variables: any;
  components: string[];
  component_instances?: any[];
  levels?: string[];
  topics?: string[];
}

export interface TemplatePreviewRequest {
  template_id: string;
  variables: { [key: string]: any };
}

export interface TemplatePreviewResponse {
  preview_url: string;
}

