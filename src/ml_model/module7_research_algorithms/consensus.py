"""Evidence-grounded, non-vote-based consensus for Module 4 findings."""
from __future__ import annotations
import hashlib, json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

class ConsensusLevel(str, Enum):
    STRONG_CONSENSUS="STRONG_CONSENSUS"; CONSENSUS="CONSENSUS"; WEAK_CONSENSUS="WEAK_CONSENSUS"; DISAGREEMENT="DISAGREEMENT"; INSUFFICIENT_EVIDENCE="INSUFFICIENT_EVIDENCE"

@dataclass(frozen=True, kw_only=True)
class ConsensusResult:
    claim_key: str; level: ConsensusLevel; score: float; evidence_id: str; evidence_ids: tuple[str, ...]; contributing_agents: tuple[str, ...]; factors: dict[str, float]; rationale: tuple[str, ...]
    def to_dict(self) -> dict[str, Any]:
        return {"claim_key":self.claim_key,"level":self.level.value,"score":self.score,"evidence_id":self.evidence_id,"evidence_ids":list(self.evidence_ids),"contributing_agents":list(self.contributing_agents),"factors":self.factors,"rationale":list(self.rationale),"source":"MODULE7_CONSENSUS","confidence":self.score}

class ConsensusEngine:
    """Groups findings by resource/rule; duplicate evidence never increases support."""
    DEFAULT_WEIGHTS={"agreement":.30,"evidence":.30,"confidence":.25,"diversity":.15}
    def __init__(self, weights: Mapping[str,float]|None=None) -> None: self.weights=dict(self.DEFAULT_WEIGHTS)|dict(weights or {})
    def analyze(self, agent_results: Iterable[Any], evidence_records: Iterable[Mapping[str,Any]]=()) -> tuple[ConsensusResult,...]:
        explicit={str(x.get("evidence_id")):x for x in evidence_records if isinstance(x,Mapping) and x.get("evidence_id")}
        groups: dict[str,list[dict[str,Any]]]={}
        for result in agent_results:
            agent=getattr(getattr(result,"agent_type",None),"value",None) or (result.get("agent_type") if isinstance(result,Mapping) else "UNKNOWN")
            findings=getattr(result,"findings",None) if not isinstance(result,Mapping) else result.get("findings",())
            for f in findings or ():
                raw=f.to_dict() if hasattr(f,"to_dict") else f
                if not isinstance(raw,Mapping): continue
                key=f"{raw.get('resource_id') or 'global'}|{raw.get('rule_id') or self._claim(raw.get('message',''))}"
                groups.setdefault(key,[]).append({"agent":str(agent),**dict(raw)})
        return tuple(self._score(key,items,explicit) for key,items in sorted(groups.items()))
    def _score(self,key:str,items:list[dict[str,Any]],records:Mapping[str,Mapping[str,Any]])->ConsensusResult:
        agents=tuple(sorted({x["agent"] for x in items})); ids=tuple(sorted({str(e) for x in items for e in x.get("evidence_ids",()) if e}))
        severities={str(x.get("severity","INFO")).upper() for x in items}; contradictory=("NONE" in severities and len(severities)>1)
        coverage=min(1.,len(ids)/max(1,len(items)))
        confidence=sum(float(x.get("confidence",.5)) for x in items)/len(items)
        sources={str(records[e].get("source","")) for e in ids if e in records}
        diversity=min(1.,(len(sources)+len(agents))/4)
        agreement=0.0 if contradictory else (1.0 if len(items)>1 else .55)
        factors={"agent_agreement":agreement,"evidence_coverage":coverage,"agent_confidence":confidence,"source_diversity":diversity,"contradiction_penalty":1.0 if contradictory else 0.0}
        score=max(0.,min(1.,sum(self.weights[k]*factors[{"agreement":"agent_agreement","evidence":"evidence_coverage","confidence":"agent_confidence","diversity":"source_diversity"}[k]] for k in self.weights)))
        if contradictory: level=ConsensusLevel.DISAGREEMENT
        elif not ids: level=ConsensusLevel.INSUFFICIENT_EVIDENCE
        elif score>=.8: level=ConsensusLevel.STRONG_CONSENSUS
        elif score>=.6: level=ConsensusLevel.CONSENSUS
        else: level=ConsensusLevel.WEAK_CONSENSUS
        payload={"claim":key,"ids":ids,"agents":agents,"factors":factors,"level":level.value}
        eid="consensus:"+hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:16]
        return ConsensusResult(claim_key=key,level=level,score=round(score,6),evidence_id=eid,evidence_ids=ids,contributing_agents=agents,factors=factors,rationale=("Duplicate evidence IDs are deduplicated before scoring.",f"{len(agents)} agent source(s), {len(ids)} unique evidence item(s)."))
    @staticmethod
    def _claim(message:Any)->str: return " ".join(str(message).lower().split())[:80]
