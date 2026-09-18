/** Human labels for backend file_type values. */
export function formatFileType(type) {
  const map = { terraform: 'Terraform', cloudformation: 'CloudFormation' };
  return map[String(type || '').toLowerCase()] ?? String(type ?? 'Unknown');
}
