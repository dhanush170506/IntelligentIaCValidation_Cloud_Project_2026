import { api } from "./api.js";

export async function getDatasetEvaluations() {
  const payload = await api.get("/dataset-evaluations");
  return payload || { success: true, runs: [], available_datasets: [] };
}

export async function getDatasetEvaluation(runId) {
  const payload = await api.get(
    `/dataset-evaluations/${encodeURIComponent(runId)}`,
  );
  return payload || { success: false, run: null };
}

export async function getDatasetEvaluationResults(runId) {
  const payload = await api.get(
    `/dataset-evaluations/${encodeURIComponent(runId)}/results`,
  );
  return payload || { success: true, results: [] };
}

export async function startDatasetEvaluation(payload) {
  const response = await api.post("/dataset-evaluations", payload || {});
  return response;
}
