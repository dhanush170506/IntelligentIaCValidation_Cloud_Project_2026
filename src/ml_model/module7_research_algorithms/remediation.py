"""Explainable blast radius and dry-run-only remediation selection."""
from __future__ import annotations
import hashlib,json
from dataclasses import dataclass
from enum import Enum
from typing import Any,Mapping,Iterable
from src.ml_model.module2_uir.graph_builder import GraphBuilder

class GateDecision(str,Enum): AUTONOMOUSLY_ELIGIBLE="AUTONOMOUSLY_ELIGIBLE"; REQUIRES_APPROVAL="REQUIRES_APPROVAL"; BLOCKED="BLOCKED"; INSUFFICIENT_EVIDENCE="INSUFFICIENT_EVIDENCE"
@dataclass(frozen=True,kw_only=True)
class BlastRadiusAssessment:
 resource_id:str; direct_dependents:tuple[str,...]; transitive_dependents:tuple[str,...]; affected_resource_count:int; criticality_weight:float; blast_radius_score:float; evidence_id:str; explanation:tuple[str,...]; target_criticality:float=0.; dependent_criticality:float=0.; direct_dependency_reach:float=0.; transitive_dependency_reach:float=0.
 def to_dict(self): return {"resource_id":self.resource_id,"direct_dependents":list(self.direct_dependents),"transitive_dependents":list(self.transitive_dependents),"affected_resource_count":self.affected_resource_count,"criticality_weight":self.criticality_weight,"target_criticality":self.target_criticality,"dependent_criticality":self.dependent_criticality,"direct_dependency_reach":self.direct_dependency_reach,"transitive_dependency_reach":self.transitive_dependency_reach,"blast_radius_score":self.blast_radius_score,"evidence_id":self.evidence_id,"source":"MODULE7_BLAST_RADIUS"}
@dataclass(frozen=True,kw_only=True)
class RemediationProposal:
 resource_id:str; proposed_change:dict[str,Any]; decision:GateDecision; rationale:tuple[str,...]; evidence_ids:tuple[str,...]; blast_radius:BlastRadiusAssessment; confidence:float; evidence_id:str; dry_run:bool=True
 def __post_init__(self): object.__setattr__(self,"dry_run",True)
 def to_dict(self): return {"resource_id":self.resource_id,"proposed_change":self.proposed_change,"decision":self.decision.value,"rationale":list(self.rationale),"evidence_ids":list(self.evidence_ids),"blast_radius":self.blast_radius.to_dict(),"confidence":self.confidence,"evidence_id":self.evidence_id,"source":"MODULE7_REMEDIATION_GATE","dry_run":self.dry_run}

class BlastRadiusEngine:
 """Uses Module 2 parent links as downstream dependents; never mutates a graph."""
 def __init__(self,criticality:Mapping[str,float]|None=None): self.criticality=dict(criticality or {})
 def assess(self,uir:Mapping[str,Any],resource_id:str)->BlastRadiusAssessment:
  graph=GraphBuilder().build(dict(uir))
  if not graph.has_node(resource_id): return self._result(resource_id,(),(),0.,0.,0.,0.,"Target resource does not exist in the Module 2 ResourceGraph.")
  # Module 2 edges: dependent(source) -> dependency(target), so parents are downstream dependents.
  seen={resource_id}; frontier=[resource_id]; direct=tuple(sorted(x.id for x in graph.get_parents(resource_id)))
  while frontier:
   current=frontier.pop(0)
   for node in graph.get_parents(current):
    if node.id not in seen: seen.add(node.id); frontier.append(node.id)
  seen.discard(resource_id); trans=tuple(sorted(seen)); target=self._criticality(resource_id); dependent=max((self._criticality(x) for x in trans),default=0.)
  direct_reach=len(direct)/(len(direct)+1) if direct else 0.; extra=max(0,len(trans)-len(direct)); trans_reach=extra/(extra+1) if extra else 0.
  return self._result(resource_id,direct,trans,target,dependent,direct_reach,trans_reach,"Module 2 get_parents() is interpreted as downstream dependents.")
 def _result(self,resource_id,direct,trans,target,dependent,direct_reach,trans_reach,note):
  count=len(trans)/(len(trans)+3) if trans else 0.; score=min(1.,.20*target+.25*dependent+.20*direct_reach+.20*trans_reach+.15*count)
  payload={"resource":resource_id,"direct":direct,"transitive":trans,"target_criticality":target,"dependent_criticality":dependent,"direct_reach":direct_reach,"transitive_reach":trans_reach}; eid="blast-radius:"+hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
  explanation=(note,f"Score combines target criticality ({target:.2f}), dependent criticality ({dependent:.2f}), direct reach ({direct_reach:.2f}), transitive reach ({trans_reach:.2f}), and affected count ({len(trans)}).")
  return BlastRadiusAssessment(resource_id=resource_id,direct_dependents=direct,transitive_dependents=trans,affected_resource_count=len(trans),criticality_weight=dependent,blast_radius_score=round(score,6),evidence_id=eid,explanation=explanation,target_criticality=target,dependent_criticality=dependent,direct_dependency_reach=round(direct_reach,6),transitive_dependency_reach=round(trans_reach,6))
 def _criticality(self,resource_id):
  try:return max(0.,min(1.,float(self.criticality.get(resource_id,.5))))
  except (TypeError,ValueError):return .5

class RemediationGate:
 DEFAULT={"min_confidence":.75,"min_consensus":.70,"max_blast":.30,"max_risk":.30}
 def __init__(self,thresholds:Mapping[str,float]|None=None):self.thresholds=dict(self.DEFAULT)|dict(thresholds or {})
 def propose(self,*,resource_id:str,proposed_change:Mapping[str,Any],blast_radius:BlastRadiusAssessment,consensus:Any,confidence:float,risk:float,evidence_ids:Iterable[str]=())->RemediationProposal:
  level=str(getattr(getattr(consensus,"level",None),"value",getattr(consensus,"level",""))); score=float(getattr(consensus,"score",0)); ids=tuple(sorted(set(evidence_ids)|set(getattr(consensus,"evidence_ids",())))); reasons=[]
  if not ids or level=="INSUFFICIENT_EVIDENCE": decision=GateDecision.INSUFFICIENT_EVIDENCE; reasons.append("Required evidence is unavailable.")
  elif level=="DISAGREEMENT" or risk>self.thresholds["max_risk"]: decision=GateDecision.BLOCKED; reasons.append("Contradiction or remediation risk exceeds policy.")
  elif confidence<self.thresholds["min_confidence"] or score<self.thresholds["min_consensus"] or blast_radius.blast_radius_score>self.thresholds["max_blast"]: decision=GateDecision.REQUIRES_APPROVAL; reasons.append("Confidence, consensus, or blast radius requires human approval.")
  else: decision=GateDecision.AUTONOMOUSLY_ELIGIBLE; reasons.append("Eligible only as a dry-run proposal; no infrastructure action is executed.")
  payload={"resource":resource_id,"change":dict(proposed_change),"decision":decision.value,"ids":ids}; return RemediationProposal(resource_id=resource_id,proposed_change=dict(proposed_change),decision=decision,rationale=tuple(reasons),evidence_ids=ids,blast_radius=blast_radius,confidence=max(0,min(1,confidence)),evidence_id="remediation-gate:"+hashlib.sha256(json.dumps(payload,sort_keys=True,default=str).encode()).hexdigest()[:16])

class RemediationRanker:
 """Ranks normalized objectives; cost/cost_efficiency 1.0 means best cost outcome."""
 DEFAULT={"security":.25,"reliability":.25,"cost_efficiency":.15,"risk":.15,"blast":.10,"confidence":.10}
 def __init__(self,weights:Mapping[str,float]|None=None):
  supplied=dict(weights or {}); supplied["cost_efficiency"]=supplied.pop("cost",supplied.get("cost_efficiency",self.DEFAULT["cost_efficiency"])); self.weights=dict(self.DEFAULT)|supplied
 def rank(self,options:Iterable[Mapping[str,Any]])->tuple[dict[str,Any],...]:
  rows=[]
  for raw in options:
   o=dict(raw); vals={k:self._objective(o.get(k,0)) for k in ("security","reliability","risk","blast","confidence")}; vals["cost_efficiency"]=self._objective(o.get("cost_efficiency",o.get("cost",0))); vals["cost"]=vals["cost_efficiency"]
   score=self.weights["security"]*vals["security"]+self.weights["reliability"]*vals["reliability"]+self.weights["cost_efficiency"]*vals["cost_efficiency"]-self.weights["risk"]*vals["risk"]-self.weights["blast"]*vals["blast"]+self.weights["confidence"]*vals["confidence"]; o.update({"objectives":vals,"ranking_score":round(max(0,min(1,score)),6)}); rows.append(o)
  for o in rows:
   v=o["objectives"]; keys=("security","reliability","cost_efficiency","confidence","risk","blast"); dominated=any(all(x["objectives"][k]>=v[k] for k in keys[:4]) and all(x["objectives"][k]<=v[k] for k in keys[4:]) and any(x["objectives"][k]!=v[k] for k in keys) for x in rows if x is not o); o["pareto_optimal"]=not dominated; o["dominated"]=dominated
  return tuple({**o,"rank":i+1,"evidence_id":"remediation-ranking:"+hashlib.sha256(json.dumps(o,sort_keys=True,default=str).encode()).hexdigest()[:16]} for i,o in enumerate(sorted(rows,key=lambda x:(-x["ranking_score"],str(x.get("option_id",""))))) )
 @staticmethod
 def _objective(value):
  try:return max(0.,min(1.,float(value)))
  except (TypeError,ValueError):return 0.
