/**
 * Safe mapping of backend/ML payloads into view models.
 *
 * The ML pipeline returns rich, optionally-shaped objects. Every accessor here
 * is defensive: a missing field yields `null`/`[]` rather than a crash, and
 * pages render explicit empty states instead of fabricated data.
 */

export function asArray(value) {
  if (Array.isArray(value)) return value.filter(Boolean);
  if (value == null) return [];
  return [value];
}

export function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
}

export function numberOf(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

/** `POST /validate` response -> { meta, validation } */
export function mapValidateResponse(payload) {
  if (!asObject(payload)) return null;
  return {
    uploadId: payload.upload_id ?? null,
    reportId: payload.report_id ?? null,
    filename: payload.filename ?? 'unknown',
    fileType: payload.file_type ?? 'unknown',
    success: payload.success === true,
    validation: mapValidation(payload.validation),
  };
}

/** Stored `GET /reports/{id}` payload -> view model (subset of full validation). */
export function mapStoredReport(payload) {
  if (!asObject(payload)) return null;
  return {
    reportId: payload.report_id ?? null,
    uploadId: payload.upload_id ?? null,
    filename: payload.filename ?? 'unknown',
    fileType: payload.file_type ?? 'unknown',
    status: payload.status ?? null,
    securityScore: numberOf(payload.security_score),
    driftScore: numberOf(payload.drift_score),
    confidence: numberOf(payload.confidence),
    createdAt: payload.created_at ?? null,
    errorDetail: payload.error_detail ?? null,
    findings: mapFindings(payload.findings),
    recommendations: mapRecommendations(payload.recommendations),
    // The stored report intentionally carries no agent/evidence/drift/blast
    // payloads; tabs for those render only when a full validation payload is
    // available (i.e. right after POST /validate).
    hasExtendedData: false,
  };
}

/** Full `validation` object from POST /validate -> view model. */
export function mapValidation(validation) {
  const v = asObject(validation);
  if (!v) return null;

  const assurance = asObject(v.assurance_report);
  const readiness = asObject(assurance?.deployment_readiness);
  const assuranceSecurity = asObject(assurance?.security);
  const runtime = asObject(assurance?.runtime);

  return {
    status: v.status ?? null,
    error: v.error ?? null,
    source: v.source ?? null,
    securityScore: numberOf(v.security_score),
    driftScore: numberOf(v.drift_score),
    confidence: numberOf(v.confidence),
    provider: v.provider ?? assurance?.provider ?? null,

    findings: mapFindings(v.findings),
    recommendations: mapRecommendations(v.recommendations),

    agents: mapAgents(v.agent_results),
    evidence: mapEvidence(v.evidence),
    drift: mapDriftAssessments(v.drift_assessments),
    consensus: mapConsensus(v.consensus),
    blastRadius: mapBlastRadius(v.blast_radius_assessments),
    remediation: mapRemediation(v.remediation_proposals, v.remediation_rankings),
    uir: mapUir(v.uir, v.graph),
    stages: asArray(v.metadata?.stages),
    warnings: asArray(v.warnings),
    errors: asArray(v.errors),

    assurance: assurance
      ? {
          readinessScore: numberOf(readiness?.score),
          readinessComponents: readiness?.components ?? null,
          securityBreakdown: assuranceSecurity,
          runtimeDriftCount: numberOf(runtime?.drift_count),
          runtimeCategories: asArray(runtime?.categories),
          costOptimizationCount: numberOf(asObject(assurance?.cost)?.optimization_count),
          limitations: asArray(assurance?.limitations),
        }
      : null,

    hasExtendedData: true,
  };
}

export function mapFindings(findings) {
  return asArray(findings).map((f, index) => {
    const o = asObject(f) ?? {};
    return {
      id: o.rule_id ? `${o.rule_id}:${o.resource_id ?? index}` : `finding-${index}`,
      severity: o.severity ?? null,
      category: o.agent_type ?? o.category ?? null,
      resource: o.resource_id ?? null,
      message: o.message ?? o.description ?? null,
      ruleId: o.rule_id ?? null,
      confidence: numberOf(o.confidence),
      evidenceIds: asArray(o.evidence_ids),
    };
  });
}

export function mapRecommendations(recommendations) {
  return asArray(recommendations).map((r, index) => {
    // The backend's mock-mode payload emits recommendations as plain strings;
    // normalize them into the object shape used by the rest of the mapper.
    const o = typeof r === 'string' ? { title: r, description: r } : asObject(r) ?? {};
    const explanation = asObject(o.explanation);
    return {
      id: o.recommendation_id ?? `recommendation-${index}`,
      title: o.title ?? null,
      description: o.description ?? null,
      action: o.action ?? explanation?.recommended_action ?? null,
      category: o.category ?? null,
      priority: o.priority ?? o.severity ?? null,
      severity: o.severity ?? null,
      resource: o.resource_id ?? null,
      confidence: numberOf(o.confidence),
      evidenceGrounded: o.evidence_grounded === true,
      sourceModules: asArray(o.source_modules),
      problem: explanation?.problem ?? null,
      limitations: explanation?.limitations ?? null,
      blastRadiusScore: numberOf(o.blast_radius?.blast_radius_score),
      consensusLevel: asObject(o.consensus)?.level ?? null,
      consensusScore: numberOf(asObject(o.consensus)?.score),
      decision: o.module7_decision ?? null,
    };
  });
}

export function mapAgents(agentResults) {
  return asArray(agentResults).map((a, index) => {
    const o = asObject(a) ?? {};
    return {
      id: o.agent_type ?? `agent-${index}`,
      agentType: o.agent_type ?? null,
      status: o.status ?? null,
      message: o.message ?? null,
      confidence: numberOf(o.confidence),
      findings: mapFindings(o.findings),
      evidenceIds: asArray(o.evidence_ids),
      metadata: asObject(o.metadata),
    };
  });
}

export function mapEvidence(evidence) {
  return asArray(evidence).map((e, index) => {
    const o = asObject(e) ?? {};
    return {
      id: o.evidence_id ?? `evidence-${index}`,
      evidenceId: o.evidence_id ?? null,
      source: o.source ?? null,
      status: o.status ?? null,
      resource: o.resource_id ?? null,
      ruleId: o.rule_id ?? null,
      severity: o.severity ?? null,
      message: o.message ?? null,
      confidence: numberOf(o.confidence),
    };
  });
}

export function mapDriftAssessments(drift) {
  return asArray(drift).map((d, index) => {
    const o = asObject(d) ?? {};
    const desired = asObject(o.desired);
    const observed = asObject(o.observed);
    return {
      id: o.evidence_id ?? `drift-${index}`,
      resource: o.resource_id ?? desired?.id ?? null,
      category: o.category ?? null,
      score: numberOf(o.score),
      severity: o.severity ?? null,
      confidence: numberOf(o.confidence),
      factors: asObject(o.factors),
      rationale: asArray(o.rationale),
      desired: desired
        ? { type: desired.type ?? null, name: desired.name ?? null, properties: desired.properties ?? null }
        : null,
      observed, // null when the runtime state was not observed
      telemetryEvidenceIds: asArray(o.telemetry_evidence_ids),
    };
  });
}

export function mapConsensus(consensus) {
  return asArray(consensus).map((c, index) => {
    const o = asObject(c) ?? {};
    return {
      id: o.evidence_id ?? `consensus-${index}`,
      claimKey: o.claim_key ?? null,
      level: o.level ?? null,
      score: numberOf(o.score),
      confidence: numberOf(o.confidence),
      contributingAgents: asArray(o.contributing_agents),
      factors: asObject(o.factors),
      rationale: asArray(o.rationale),
      evidenceIds: asArray(o.evidence_ids),
    };
  });
}

export function mapBlastRadius(blast) {
  return asArray(blast).map((b, index) => {
    const o = asObject(b) ?? {};
    return {
      id: o.evidence_id ?? `blast-${index}`,
      resource: o.resource_id ?? null,
      directDependents: asArray(o.direct_dependents),
      transitiveDependents: asArray(o.transitive_dependents),
      affectedCount: numberOf(o.affected_resource_count) ?? 0,
      blastRadiusScore: numberOf(o.blast_radius_score),
      targetCriticality: numberOf(o.target_criticality),
      dependentCriticality: numberOf(o.dependent_criticality),
      evidenceId: o.evidence_id ?? null,
      source: o.source ?? null,
    };
  });
}

export function mapRemediation(proposals, rankings) {
  const rankingByResource = new Map(
    asArray(rankings)
      .map((r) => [asObject(r)?.resource_id, asObject(r)])
      .filter(([key]) => Boolean(key))
  );

  return asArray(proposals).map((p, index) => {
    const o = asObject(p) ?? {};
    const ranking = rankingByResource.get(o.resource_id) ?? null;
    return {
      id: o.evidence_id ?? `remediation-${index}`,
      resource: o.resource_id ?? ranking?.resource_id ?? null,
      decision: o.decision ?? null,
      rationale: asArray(o.rationale),
      proposedChange: asObject(o.proposed_change),
      confidence: numberOf(o.confidence),
      dryRun: o.dry_run === true,
      evidenceIds: asArray(o.evidence_ids),
      blastRadiusScore: numberOf(o.blast_radius?.blast_radius_score),
      ranking: ranking
        ? {
            security: numberOf(ranking.security),
            reliability: numberOf(ranking.reliability),
            cost: numberOf(ranking.cost),
            risk: numberOf(ranking.risk),
            blast: numberOf(ranking.blast),
          }
        : null,
    };
  });
}

function mapUir(uir, graph) {
  const u = asObject(uir);
  const g = asObject(graph) ?? asObject(u?.graph);
  const nodes = asArray(g?.nodes).map((n, i) => {
    const o = asObject(n) ?? {};
    return {
      id: o.id ?? o.resource_id ?? `node-${i}`,
      type: o.type ?? o.canonical_type ?? null,
      name: o.name ?? null,
    };
  });
  const edges = asArray(g?.edges).map((e, i) => {
    const o = asObject(e) ?? {};
    return {
      id: `edge-${i}`,
      from: o.from ?? o.source ?? null,
      to: o.to ?? o.target ?? null,
      kind: o.kind ?? o.type ?? null,
    };
  });
  if (!u && nodes.length === 0 && edges.length === 0) return null;
  return {
    provider: u?.provider ?? null,
    resourceCount: asArray(u?.resources).length || nodes.length,
    dependencyCount: asArray(u?.dependencies).length || edges.length,
    nodes,
    edges,
  };
}

/** History/dashboard row -> table view model. */
export function mapReportSummary(row) {
  const o = asObject(row) ?? {};
  return {
    reportId: o.report_id ?? null,
    uploadId: o.upload_id ?? null,
    filename: o.filename ?? 'unknown',
    fileType: o.file_type ?? 'unknown',
    status: o.status ?? null,
    securityScore: numberOf(o.security_score),
    driftScore: numberOf(o.drift_score),
    confidence: numberOf(o.confidence),
    createdAt: o.created_at ?? null,
  };
}
